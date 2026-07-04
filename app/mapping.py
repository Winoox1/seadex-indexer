"""
AniBridge mapping lookup.

The AniBridge schema uses descriptor keys in the form:
  provider:id[:scope]

e.g. tvdb_show:359274:s1, anilist:101348, tmdb_movie:1218925, imdb_movie:tt30472557

We build two reverse indexes at startup:
  - (tvdb_id, season) -> {anilist_id, ...}
  - (tmdb_movie_id | imdb_movie_id)  -> {anilist_id, ...}
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, Optional, Set, Tuple

import httpx

logger = logging.getLogger(__name__)

# In-memory indexes built from the mapping file
# tvdb_show index: (tvdb_id_str, season_int) -> set of anilist_ids
_tvdb_index: Dict[tuple, Set[int]] = {}
# tmdb movie index: tmdb_id_str -> set of anilist_ids
_tmdb_movie_index: Dict[str, Set[int]] = {}
# imdb movie index: imdb_id_str -> set of anilist_ids
_imdb_movie_index: Dict[str, Set[int]] = {}

_TVDB_RE  = re.compile(r"^tvdb_show:(\d+):s(\d+)$")
_TMDB_MOVIE_RE = re.compile(r"^tmdb_movie:(\d+)$")
_IMDB_MOVIE_RE = re.compile(r"^imdb_movie:(tt\d+)$")
_ANILIST_RE = re.compile(r"^anilist:(\d+)$")

_last_refresh: Optional[str] = None


def _build_indexes(data: dict) -> Tuple[Dict[tuple, Set[int]], Dict[str, Set[int]], Dict[str, Set[int]]]:
    """
    Parse the AniBridge JSON and return the three lookup indexes
    (tvdb, tmdb_movie, imdb_movie). Builds into local dicts so the live
    global indexes keep serving lookups until the caller swaps them in.
    """
    _tvdb_index: Dict[tuple, Set[int]] = {}
    _tmdb_movie_index: Dict[str, Set[int]] = {}
    _imdb_movie_index: Dict[str, Set[int]] = {}

    for source_key, targets in data.items():
        if not isinstance(targets, dict):
            continue

        # Collect all anilist IDs linked to this source key
        anilist_ids: Set[int] = set()
        for target_key in targets:
            m = _ANILIST_RE.match(target_key)
            if m:
                anilist_ids.add(int(m.group(1)))

        if not anilist_ids:
            # Also check if the source key itself is anilist and collect linked IDs
            # (AniBridge can have anilist as the source too)
            continue

        # Index by tvdb_show
        m = _TVDB_RE.match(source_key)
        if m:
            tvdb_id, season = m.group(1), int(m.group(2))
            key = (tvdb_id, season)
            _tvdb_index.setdefault(key, set()).update(anilist_ids)
            continue

        # Index by tmdb_movie
        m = _TMDB_MOVIE_RE.match(source_key)
        if m:
            tmdb_id = m.group(1)
            _tmdb_movie_index.setdefault(tmdb_id, set()).update(anilist_ids)
            continue

        # Index by imdb_movie
        m = _IMDB_MOVIE_RE.match(source_key)
        if m:
            imdb_id = m.group(1)
            _imdb_movie_index.setdefault(imdb_id, set()).update(anilist_ids)
            continue

    # Also do a second pass: when anilist is the source key, find tvdb/tmdb/imdb targets
    # This handles entries where the mapping is stored anilist->tvdb rather than tvdb->anilist
    for source_key, targets in data.items():
        if not isinstance(targets, dict):
            continue

        src_m = _ANILIST_RE.match(source_key)
        if not src_m:
            continue
        anilist_id = int(src_m.group(1))

        for target_key in targets:
            # tvdb_show target
            m = _TVDB_RE.match(target_key)
            if m:
                tvdb_id, season = m.group(1), int(m.group(2))
                key = (tvdb_id, season)
                _tvdb_index.setdefault(key, set()).add(anilist_id)
                continue

            # tmdb_movie target
            m = _TMDB_MOVIE_RE.match(target_key)
            if m:
                _tmdb_movie_index.setdefault(m.group(1), set()).add(anilist_id)
                continue

            # imdb_movie target
            m = _IMDB_MOVIE_RE.match(target_key)
            if m:
                _imdb_movie_index.setdefault(m.group(1), set()).add(anilist_id)
                continue

    logger.info(
        f"AniBridge index built: {len(_tvdb_index)} tvdb entries, "
        f"{len(_tmdb_movie_index)} tmdb_movie entries, "
        f"{len(_imdb_movie_index)} imdb_movie entries"
    )
    return _tvdb_index, _tmdb_movie_index, _imdb_movie_index


def _parse_and_build(raw: str) -> Tuple[Dict[tuple, Set[int]], Dict[str, Set[int]], Dict[str, Set[int]]]:
    """CPU-bound part of a refresh - runs on a worker thread via to_thread."""
    return _build_indexes(json.loads(raw))


async def load_mappings() -> None:
    """Fetch AniBridge mappings and build in-memory indexes."""
    global _tvdb_index, _tmdb_movie_index, _imdb_movie_index, _last_refresh

    url = "https://github.com/anibridge/anibridge-mappings/releases/latest/download/mappings.min.json"
    logger.info(f"Fetching AniBridge mappings from {url}")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        raw = resp.text

    # Parse + build off the event loop, then swap the live indexes atomically
    tvdb, tmdb_movie, imdb_movie = await asyncio.to_thread(_parse_and_build, raw)
    _tvdb_index = tvdb
    _tmdb_movie_index = tmdb_movie
    _imdb_movie_index = imdb_movie
    _last_refresh = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.info("AniBridge mappings fetched and built")


def lookup_tvdb(tvdb_id: int, season: int) -> list[int]:
    """Return AniList IDs for a given TVDB show ID and season number."""
    key = (str(tvdb_id), season)
    result = _tvdb_index.get(key, set())
    return sorted(result)


def lookup_tmdb_movie(tmdb_id: int) -> list[int]:
    """Return AniList IDs for a given TMDB movie ID."""
    result = _tmdb_movie_index.get(str(tmdb_id), set())
    return sorted(result)


def lookup_imdb_movie(imdb_id: str) -> list[int]:
    """Return AniList IDs for a given IMDB ID (with or without tt prefix)."""
    if not imdb_id.startswith("tt"):
        imdb_id = "tt" + imdb_id
    result = _imdb_movie_index.get(imdb_id, set())
    return sorted(result)


def is_loaded() -> bool:
    return bool(_tvdb_index or _tmdb_movie_index or _imdb_movie_index)


def stats() -> dict:
    return {
        "tvdb_entries": len(_tvdb_index),
        "tmdb_movie_entries": len(_tmdb_movie_index),
        "imdb_movie_entries": len(_imdb_movie_index),
        "last_refresh": _last_refresh,
    }
