"""Production agent: authenticated requests with shared rate and cost limits."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost, release_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import MOCK_RESPONSES, ask as llm_ask


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "event": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False)


logger = logging.getLogger("agent")
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.handlers = [handler]
logger.setLevel(logging.INFO)
logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ready = True
    logger.info("startup", extra={"fields": {"environment": settings.environment}})
    try:
        yield
    finally:
        # Uvicorn drains accepted requests before entering lifespan shutdown.
        app.state.ready = False
        r.close()
        logger.info("shutdown")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)
MAX_MOCK_OUTPUT_TOKENS = max(len(answer.split()) * 2 for answers in MOCK_RESPONSES.values() for answer in answers)


@app.middleware("http")
async def log_request(request: Request, call_next):
    started = time.monotonic()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        logger.info("request", extra={"fields": {
            "method": request.method, "path": request.url.path,
            "status": status, "ms": round((time.monotonic() - started) * 1000, 2),
        }})


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=200)


@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready():
    available = app.state.ready and redis_healthy()
    return JSONResponse(status_code=200 if available else 503, content={"ready": available})


@app.post("/ask")
def ask(body: AskRequest, key: str = Depends(verify_api_key)):
    # Sync endpoints run blocking Redis/LLM calls in FastAPI's thread pool.
    if not app.state.ready:
        raise HTTPException(status_code=503, detail="Agent is shutting down")
    check_rate_limit(key)
    input_tokens = len(body.question.split()) * 2
    reservation = check_budget(input_tokens, MAX_MOCK_OUTPUT_TOKENS)
    try:
        answer = llm_ask(body.question)
    except Exception:
        release_cost(reservation)
        logger.exception("llm_failed")
        raise HTTPException(status_code=502, detail="LLM request failed") from None
    cost = record_cost(input_tokens, len(answer.split()) * 2, reservation)
    logger.info("answer", extra={"fields": {"cost_usd": cost}})
    return {"question": body.question, "answer": answer, "usage": {"cost_usd": cost}}
