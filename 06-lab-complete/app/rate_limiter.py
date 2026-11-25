"""Atomic Redis sliding window shared by all workers and instances."""
from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r, storage_unavailable

RATE_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - 60)
local count = redis.call('ZCARD', KEYS[1])
if count >= tonumber(ARGV[1]) then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    return math.max(1, math.ceil(tonumber(oldest[2]) + 60 - now))
end
redis.call('ZADD', KEYS[1], now, ARGV[2])
redis.call('EXPIRE', KEYS[1], 60)
return 0
"""


def check_rate_limit(key: str) -> None:
    # Never store the raw credential in Redis keys or logs.
    bucket = f"agent:{settings.environment}:rate:{sha256(key.encode()).hexdigest()}"
    try:
        retry_after = int(r.eval(RATE_SCRIPT, 1, bucket, settings.rate_limit_per_minute, uuid4().hex))
    except RedisError:
        raise storage_unavailable() from None
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(settings.rate_limit_per_minute)},
        )
