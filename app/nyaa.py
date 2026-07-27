import asyncio
import logging
import math
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

from .config import settings

logger = logging.getLogger(__name__)

_HTML_ENTITIES = {
    "&#39;": "'",
    "&amp;": "&",
    "&quot;": '"',
    "&lt;": "<",
    "&gt;": ">",
    "&#x27;": "'",
    "&#x2F;": "/",
}

_SIZE_UNITS = {
    "GiB": 1073741824,
    "MiB": 1048576,
    "KiB": 1024,
    "GB": 1000000000,
    "MB": 1000000,
    "KB": 1000,
}


def _decode_html(text: str) -> str:
    for entity, char in _HTML_ENTITIES.items():
        text = text.replace(entity, char)
    return text


def _parse_size(size_str: str) -> int:
    """Convert '83.2 GiB' -> bytes as int."""
    size_str = size_str.strip()
    for unit, multiplier in _SIZE_UNITS.items():
        if unit in size_str:
            try:
                num = float(size_str.replace(unit, "").strip())
                return math.floor(num * multiplier)
            except ValueError:
                pass
    return 0


def _scrape_html(html: str, nyaa_id: str, meta: dict) -> Optional[dict]:
    """Extract torrent metadata from a Nyaa view page."""
    # Title
    title_match = re.search(r'<h3 class="panel-title">\s*([\s\S]+?)\s*</h3>', html)
    if not title_match:
        return None
    title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
    title = _decode_html(title)

    # File size
    size_match = re.search(
        r"File size:</div>\s*<div[^>]*>([\s\S]*?)</div>", html
    )
    size_bytes = _parse_size(size_match.group(1)) if size_match else 0

    # Info hash
    hash_match = re.search(r"<kbd>([a-fA-F0-9]+)</kbd>", html)
    info_hash = hash_match.group(1).lower() if hash_match else ""

    # Seeders (green) / leechers (red)
    seeders_match = re.search(r'<span style="color: green;">(\d+)</span>', html)
    leechers_match = re.search(r'<span style="color: red;">(\d+)</span>', html)
    seeders = int(seeders_match.group(1)) if seeders_match else 0
    leechers = int(leechers_match.group(1)) if leechers_match else 0

    # Publish date from first data-timestamp attribute
    ts_match = re.search(r'data-timestamp="(\d+)"', html)
    pub_date = ""
    if ts_match:
        dt = datetime.fromtimestamp(int(ts_match.group(1)), tz=timezone.utc)
        pub_date = dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

    return {
        "title": title,
        "nyaaId": nyaa_id,
        "viewUrl": meta["viewUrl"],
        "link": f"https://nyaa.si/download/{nyaa_id}.torrent",
        "size": str(size_bytes),
        "seeders": str(seeders),
        "peers": str(seeders + leechers),
        "pubDate": pub_date,
        "hash": info_hash,
        "best": meta["best"],
        "tags": meta.get("tags", []),
        "releaseGroup": meta.get("releaseGroup", ""),
    }


async def _fetch_one(
    meta: dict,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    pacer_lock: asyncio.Lock,
    last_start: list[float],
) -> Optional[dict]:
    """Acquire rate-limit slot then fetch and parse one Nyaa page."""
    nyaa_id = meta["nyaaId"]
    url = f"https://nyaa.si/view/{nyaa_id}"

    async with sem:
        # Enforce minimum gap between request starts globally
        async with pacer_lock:
            now = asyncio.get_event_loop().time()
            wait = (last_start[0] + settings.nyaa_batch_interval) - now
            if wait > 0:
                await asyncio.sleep(wait)
            last_start[0] = asyncio.get_event_loop().time()

        logger.debug(f"Fetching Nyaa page: {url}")
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            result = _scrape_html(resp.text, nyaa_id, meta)
            if result:
                logger.debug(
                    f"Scraped nyaa/{nyaa_id}: title={result['title']!r} "
                    f"size={result['size']} seeders={result['seeders']} "
                    f"hash={result['hash'][:8] + '...' if result['hash'] else 'none'}"
                )
            return result
        except httpx.HTTPStatusError as e:
            logger.warning(f"Nyaa HTTP error for {nyaa_id}: {e.response.status_code}")
            return None
        except Exception as e:
            logger.warning(f"Nyaa fetch failed for {nyaa_id}: {e}")
            return None


async def fetch_all_torrents(metas: list[dict]) -> list[dict]:
    """
    Fetch Nyaa torrent pages with bounded concurrency and a global rate limit
    on request starts. Up to nyaa_concurrency fetches run in parallel, but
    no two requests start less than nyaa_batch_interval seconds apart.
    Failed fetches are retried once through the same pacer, so a transient
    blip doesn't leave a partial result cached without its missing releases.
    """
    sem = asyncio.Semaphore(settings.nyaa_concurrency)
    pacer_lock = asyncio.Lock()
    last_start: list[float] = [0.0]

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        tasks = [_fetch_one(meta, client, sem, pacer_lock, last_start) for meta in metas]
        raw = await asyncio.gather(*tasks)
        results = [r for r in raw if r is not None]

        failed = [meta for meta, r in zip(metas, raw) if r is None]
        if failed:
            logger.info(f"Nyaa: retrying {len(failed)} failed fetches")
            retry_tasks = [_fetch_one(meta, client, sem, pacer_lock, last_start) for meta in failed]
            retry_raw = await asyncio.gather(*retry_tasks)
            results.extend(r for r in retry_raw if r is not None)

    logger.info(f"Nyaa: fetched {len(results)}/{len(metas)} torrent pages")
    return results
