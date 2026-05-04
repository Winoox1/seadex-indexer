import logging
import re
from typing import Optional

import httpx

from .config import settings

logger = logging.getLogger(__name__)


async def query_seadex(anilist_ids: list[int]) -> list[dict]:
    """
    Query SeaDex for entries matching one or more AniList IDs.
    Returns the list of entry records with expanded torrent records.
    """
    if not anilist_ids:
        return []

    # Build PocketBase OR filter
    filter_str = "||".join(f"alID={al_id}" for al_id in anilist_ids)
    logger.debug(f"SeaDex filter: {filter_str}")

    params = {
        "filter": filter_str,
        "expand": "trs",  # trs = torrent records relation
        "perPage": "50",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.seadex_timeout) as client:
            resp = await client.get(
                f"{settings.seadex_base_url}/collections/entries/records",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            logger.debug(f"SeaDex returned {len(items)} entries")
            return items
    except httpx.HTTPStatusError as e:
        logger.error(f"SeaDex HTTP error: {e.response.status_code} - {e.response.text[:200]}")
        return []
    except Exception as e:
        logger.error(f"SeaDex request failed: {e}")
        return []


def extract_nyaa_torrents(entries: list[dict]) -> list[dict]:
    """
    Extract Nyaa torrent metadata from SeaDex entries.
    Returns a flat list of torrent dicts with nyaaId, viewUrl, best, tags.
    """
    torrents = []
    skipped = 0
    for entry in entries:
        trs = entry.get("expand", {}).get("trs", []) or []
        for torrent in trs:
            url = torrent.get("url", "")
            if "nyaa.si/view/" not in url:
                logger.debug(f"Skipping non-Nyaa torrent: tracker={torrent.get('tracker')} url={url!r}")
                skipped += 1
                continue

            m = re.search(r"nyaa\.si/view/(\d+)", url)
            if not m:
                continue

            torrents.append({
                "nyaaId": m.group(1),
                "viewUrl": f"https://nyaa.si/view/{m.group(1)}",
                "best": torrent.get("isBest") is True,
                "tags": torrent.get("tags") or [],
                "releaseGroup": torrent.get("releaseGroup", ""),
            })

    logger.debug(f"Extracted {len(torrents)} Nyaa torrents ({skipped} non-Nyaa skipped)")
    return torrents
