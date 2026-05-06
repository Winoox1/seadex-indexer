import logging
from typing import Optional

import httpx

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
    """Return the start year for an AniList entry."""
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

    logger.debug(f"AniList year for {anilist_id}: {year}")
    return year
