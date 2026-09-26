import json
import logging
import uuid

import redis
from fastapi import Depends, HTTPException, status

from app.config import settings
from app.models import User

log = logging.getLogger(__name__)

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def get_redis_dep() -> redis.Redis:
    return get_redis()


# --- cache for the hot read path (GET /bookings) ---

def cache_get(r: redis.Redis, key: str):
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except redis.RedisError:
        log.warning("redis unavailable for cache read, falling through to db")
        return None


def cache_set(r: redis.Redis, key: str, value, ttl: int = 60) -> None:
    try:
        r.set(key, json.dumps(value), ex=ttl)
    except redis.RedisError:
        log.warning("redis unavailable for cache write")


def invalidate_booking_cache(r: redis.Redis) -> None:
    try:
        for key in r.scan_iter("cache:bookings:*"):
            r.delete(key)
    except redis.RedisError:
        log.warning("redis unavailable for cache invalidation")


# --- rate limiting for the write endpoints ---

def rate_limit(r: redis.Redis, key: str, limit: int = 20, window_seconds: int = 60) -> None:
    try:
        count = r.incr(key)
        if count == 1:
            r.expire(key, window_seconds)
        if count > limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded")
    except redis.RedisError:
        # fail open: never block users because the limiter is down
        log.warning("redis unavailable for rate limiting, allowing request")


def booking_rate_limit(
    user: User, r: redis.Redis = Depends(get_redis_dep)
) -> None:
    rate_limit(r, f"rl:bookings:{user.id}")


# --- review summarisation job queue ---

QUEUE_KEY = "queue:summary_jobs"


def enqueue_summary_job(r: redis.Redis, provider_id: int, requested_by: int) -> str:
    job_id = uuid.uuid4().hex
    payload = {"job_id": job_id, "provider_id": provider_id, "requested_by": requested_by}
    r.rpush(QUEUE_KEY, json.dumps(payload))
    r.hset(f"job:{job_id}", mapping={"status": "queued", "provider_id": provider_id, "result": ""})
    return job_id


def get_job(r: redis.Redis, job_id: str) -> dict | None:
    try:
        data = r.hgetall(f"job:{job_id}")
        return data or None
    except redis.RedisError:
        return None
