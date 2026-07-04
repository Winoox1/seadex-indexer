import time
from typing import Optional

_cache: dict[str, tuple[str, float]] = {}  # key -> (value, expiry_time)


def cache_get(key: str) -> Optional[str]:
    entry = _cache.get(key)
    if entry is None:
        return None
    value, expiry = entry
    if time.monotonic() > expiry:
        del _cache[key]
        return None
    return value


def cache_set(key: str, value: str, ttl: int) -> None:
    _cache[key] = (value, time.monotonic() + ttl)


def cache_delete(key: str) -> None:
    _cache.pop(key, None)


def cache_clear() -> int:
    count = len(_cache)
    _cache.clear()
    return count


def cache_purge_expired() -> int:
    now = time.monotonic()
    expired = [key for key, (_, expiry) in _cache.items() if now > expiry]
    for key in expired:
        del _cache[key]
    return len(expired)
