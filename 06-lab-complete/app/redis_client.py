"""Lazy connections: Redis outages must not prevent liveness/startup."""
from fastapi import HTTPException
import redis

from app.config import settings

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
    retry_on_timeout=False,
)


def redis_healthy() -> bool:
    try:
        return bool(r.ping())
    except redis.RedisError:
        return False


def storage_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="Shared storage unavailable", headers={"Retry-After": "1"})
