import logging
from typing import Optional

import httpx

from .cache import cache_get, cache_set

logger = logging.getLogger(__name__)

_GRAPHQL_URL = "https://graphql.anilist.co"
_QUERY = """
query ($id: Int) {
  Media(id: $id, type: ANIME) {
    startDate { year }
  }
}
"""


async def fetch_year(anilist_id: int) -> Optional[int]:
    """Return the start year for an AniList entry, using Redis cache."""
    cache_key = f"seadex:year:{anilist_id}"

    cached = await cache_get(cache_key)
    if cached:
        return int(cached) if cached != "null" else None

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

    # Cache for 30 days — year data never changes
    await cache_set(cache_key, str(year) if year else "null", 86400 * 30)
    logger.debug(f"AniList year for {anilist_id}: {year}")
    return year
