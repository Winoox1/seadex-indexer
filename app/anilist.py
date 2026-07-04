import logging
from typing import Optional

import httpx

from .cache import cache_get, cache_set

logger = logging.getLogger(__name__)

_GRAPHQL_URL = "https://graphql.anilist.co"
# Start years rarely change (occasional corrections) - cache for 24 hours
_YEAR_CACHE_TTL = 86400
_QUERY = """
query ($id: Int) {
  Media(id: $id, type: ANIME) {
    startDate { year }
  }
}
"""


async def fetch_year(anilist_id: int) -> Optional[int]:
    """Return the start year for an AniList entry."""
    cache_key = f"anilist:year:{anilist_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        logger.debug(f"AniList year cache hit for {anilist_id}: {cached}")
        return int(cached)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _GRAPHQL_URL,
                json={"query": _QUERY, "variables": {"id": anilist_id}},
            )
            resp.raise_for_status()
            data = resp.json()
            year = data.get("data", {}).get("Media", {}).get("startDate", {}).get("year")
    except Exception as e:
        logger.warning(f"AniList year fetch failed for {anilist_id}: {e}")
        return None

    if year is not None:
        cache_set(cache_key, str(year), _YEAR_CACHE_TTL)
    logger.debug(f"AniList year for {anilist_id}: {year}")
    return year
