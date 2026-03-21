"""App-level Redis singleton and FastAPI dependency."""

import logging

import redis.asyncio as aioredis
from fastapi import HTTPException

logger = logging.getLogger(__name__)

redis_client: aioredis.Redis | None = None


async def init_redis(url: str) -> None:
    """Initialise the Redis connection pool and verify connectivity."""
    global redis_client
    redis_client = aioredis.from_url(url, encoding="utf-8", decode_responses=True)
    await redis_client.ping()
    logger.info("Redis connection established")


async def close_redis() -> None:
    """Gracefully close the Redis connection pool."""
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None
        logger.info("Redis connection closed")


async def get_redis() -> aioredis.Redis:
    """FastAPI dependency — returns the initialized Redis client.

    Raises HTTP 503 if the client has not been initialized (should never
    happen in a healthy app that has completed its lifespan startup).
    """
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Cache service unavailable")
    return redis_client
