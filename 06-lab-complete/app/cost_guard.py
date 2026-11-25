"""Global daily budget, reserved atomically before calling the mock LLM.

Money is stored as integer nano-USD to avoid floating point accumulation.
All API keys in the same ENVIRONMENT share this service budget.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r, storage_unavailable

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006
NANO_USD = 1_000_000_000
INPUT_NANOS_PER_TOKEN = 150
OUTPUT_NANOS_PER_TOKEN = 600

RESERVE_SCRIPT = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
local budget = tonumber(ARGV[1])
local reserve = tonumber(ARGV[2])
if used >= budget or used + reserve > budget then return 0 end
redis.call('INCRBY', KEYS[1], reserve)
redis.call('EXPIREAT', KEYS[1], ARGV[3])
return 1
"""


@dataclass(frozen=True)
class Reservation:
    key: str
    nanos: int


def check_budget(input_tokens: int = 0, max_output_tokens: int = 0) -> Reservation:
    now = datetime.now(timezone.utc)
    key = f"agent:{settings.environment}:budget:{now:%Y-%m-%d}"
    # Keep yesterday's key for late completions; today's date selects a fresh budget.
    expires = int((now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    nanos = input_tokens * INPUT_NANOS_PER_TOKEN + max_output_tokens * OUTPUT_NANOS_PER_TOKEN
    try:
        accepted = r.eval(RESERVE_SCRIPT, 1, key, int(settings.daily_budget_usd * NANO_USD), nanos, expires)
    except RedisError:
        raise storage_unavailable() from None
    if not accepted:
        raise HTTPException(status_code=402, detail="Daily budget exhausted or insufficient for this request")
    return Reservation(key, nanos)


def record_cost(input_tokens: int, output_tokens: int, reservation: Reservation) -> float:
    """Settle against the day on which the request reserved its budget."""
    actual = input_tokens * INPUT_NANOS_PER_TOKEN + output_tokens * OUTPUT_NANOS_PER_TOKEN
    try:
        r.incrby(reservation.key, actual - reservation.nanos)
    except RedisError:
        # Keep the reservation on storage failure rather than allowing untracked use.
        raise storage_unavailable() from None
    return actual / NANO_USD


def release_cost(reservation: Reservation) -> None:
    """Refund the reservation if the mock fails before producing an answer."""
    record_cost(0, 0, reservation)
