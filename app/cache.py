import logging
from typing import Optional

import redis.asyncio as aioredis

from .config import settings

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def cache_get(key: str) -> Optional[str]:
    try:
        r = await get_redis()
        return await r.get(key)
    except Exception as e:
        logger.warning(f"Redis GET failed for {key}: {e}")
        return None


async def cache_set(key: str, value: str, ttl: int) -> None:
    try:
        r = await get_redis()
        await r.setex(key, ttl, value)
    except Exception as e:
        logger.warning(f"Redis SET failed for {key}: {e}")


async def cache_delete(key: str) -> None:
    try:
        r = await get_redis()
        await r.delete(key)
    except Exception as e:
        logger.warning(f"Redis DELETE failed for {key}: {e}")
