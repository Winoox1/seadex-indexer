import asyncio
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import Response

from . import mapping, seadex, nyaa, torznab
from .cache import cache_get, cache_set, get_redis
from .config import settings

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

XML_CONTENT_TYPE = "application/rss+xml; charset=utf-8"
CAPS_CONTENT_TYPE = "application/xml; charset=utf-8"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load AniBridge mappings on startup, refresh periodically."""
    logger.info(f"SeaDex Indexer starting on port {settings.port}")

    try:
        await mapping.load_mappings()
    except Exception as e:
        logger.error(f"Failed to load AniBridge mappings on startup: {e}")

    # Check Redis connectivity
    try:
        r = await get_redis()
        await r.ping()  # type: ignore[misc]
        logger.info("Redis connection OK")
    except Exception as e:
        logger.warning(
            f"Redis unavailable ({e}) — caching disabled, "
            "all requests will hit SeaDex and Nyaa directly"
        )

    # Background refresh task
    async def refresh_loop():
        while True:
            await asyncio.sleep(settings.mapping_cache_ttl)
            try:
                await mapping.load_mappings(force=True)
                logger.info("AniBridge mappings refreshed")
            except Exception as e:
                logger.error(f"Mapping refresh failed: {e}")

    task = asyncio.create_task(refresh_loop())
    yield
    task.cancel()


app = FastAPI(title="SeaDex Indexer", lifespan=lifespan)


def xml_response(content: str, content_type: str = XML_CONTENT_TYPE) -> Response:
    return Response(content=content, media_type=content_type)


async def _resolve_anilist_ids_sonarr(tvdbid: int, season: int) -> list[int]:
    """Look up AniList IDs for a Sonarr request via AniBridge mapping."""
    ids = mapping.lookup_tvdb(tvdbid, season)
    return ids


async def _resolve_anilist_ids_radarr(
    tmdbid: Optional[int], imdbid: Optional[str],
) -> list[int]:
    """
    Look up AniList IDs for a Radarr request via AniBridge mapping.
    Tries TMDB → IMDB in order.
    """
    ids: list[int] = []

    if tmdbid:
        ids = mapping.lookup_tmdb_movie(tmdbid)

    if not ids and imdbid:
        ids = mapping.lookup_imdb_movie(imdbid)

    return ids


async def _search_and_build(anilist_ids: list[int], mode: str) -> str:
    """Run the full SeaDex -> Nyaa pipeline and return Torznab XML."""
    t0 = time.monotonic()

    entries = await seadex.query_seadex(anilist_ids)
    if not entries:
        logger.info(f"[{mode}] anilist={anilist_ids} — no SeaDex entries found")
        return torznab.empty_xml(mode)

    nyaa_metas = seadex.extract_nyaa_torrents(entries)
    if not nyaa_metas:
        logger.info(f"[{mode}] anilist={anilist_ids} — no Nyaa torrents in SeaDex entries")
        return torznab.empty_xml(mode)

    torrents = await nyaa.fetch_all_torrents(nyaa_metas)
    if not torrents:
        logger.info(f"[{mode}] anilist={anilist_ids} — all Nyaa fetches failed")
        return torznab.empty_xml(mode)

    best = sum(1 for t in torrents if t["best"])
    alt = len(torrents) - best
    elapsed = time.monotonic() - t0
    logger.info(
        f"[{mode}] anilist={anilist_ids} — "
        f"{len(torrents)} results ({best} best, {alt} alt) in {elapsed:.1f}s"
    )

    return torznab.build_results_xml(torrents, mode)


# ── Sonarr endpoint ────────────────────────────────────────────────────────────

@app.get("/sonarr/api")
async def sonarr_api(
    t: str = Query(default=""),
    tvdbid: Optional[int] = Query(default=None),
    season: Optional[int] = Query(default=None),
    q: Optional[str] = Query(default=None),
    cat: Optional[str] = Query(default=None),
    extended: Optional[str] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    offset: Optional[int] = Query(default=None),
    ep: Optional[int] = Query(default=None),
    apikey: Optional[str] = Query(default=None),
):
    # Caps
    if t == "caps":
        logger.info("sonarr caps request")
        return xml_response(torznab.caps_xml("sonarr"), CAPS_CONTENT_TYPE)

    # Prowlarr sends t=search with an empty q to verify the indexer is reachable
    if not tvdbid and (not q or q.strip() == ""):
        logger.info("sonarr health check")
        return xml_response(torznab.prowlarr_test_xml("sonarr"))

    # Real search — must have tvdbid + season
    if not tvdbid or season is None:
        logger.debug(f"sonarr rejected: tvdbid={tvdbid} season={season} ep={ep} q={q!r}")
        return xml_response(torznab.empty_xml("sonarr"))

    anilist_ids = await _resolve_anilist_ids_sonarr(tvdbid, season)
    if not anilist_ids:
        logger.info(f"sonarr tvdb={tvdbid} s={season} — no AniList mapping")
        return xml_response(torznab.empty_xml("sonarr"))

    cache_key = f"seadex:result:al:{anilist_ids[0]}:s{season}"
    cached = await cache_get(cache_key)
    if cached:
        logger.info(f"Cache hit: sonarr anilist={anilist_ids[0]} s={season}")
        return xml_response(cached)

    logger.info(f"sonarr tvdb={tvdbid} s={season} -> anilist={anilist_ids}")
    xml = await _search_and_build(anilist_ids, "sonarr")
    await cache_set(cache_key, xml, settings.result_cache_ttl)
    return xml_response(xml)


# ── Radarr endpoint ────────────────────────────────────────────────────────────

@app.get("/radarr/api")
async def radarr_api(
    t: str = Query(default=""),
    tmdbid: Optional[int] = Query(default=None),
    imdbid: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    cat: Optional[str] = Query(default=None),
    extended: Optional[str] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    offset: Optional[int] = Query(default=None),
    apikey: Optional[str] = Query(default=None),
):
    # Caps
    if t == "caps":
        logger.info("radarr caps request")
        return xml_response(torznab.caps_xml("radarr"), CAPS_CONTENT_TYPE)

    # Prowlarr sends t=search with an empty q to verify the indexer is reachable
    if not tmdbid and not imdbid and (not q or q.strip() == ""):
        logger.info("radarr health check")
        return xml_response(torznab.prowlarr_test_xml("radarr"))

    anilist_ids = await _resolve_anilist_ids_radarr(tmdbid, imdbid)
    if not anilist_ids:
        logger.info(f"radarr tmdb={tmdbid} imdb={imdbid} — no AniList mapping")
        return xml_response(torznab.empty_xml("radarr"))

    cache_key = f"seadex:result:radarr:al:{anilist_ids[0]}"
    cached = await cache_get(cache_key)
    if cached:
        logger.info(f"Cache hit: radarr anilist={anilist_ids[0]}")
        return xml_response(cached)

    logger.info(f"radarr tmdb={tmdbid} imdb={imdbid} -> anilist={anilist_ids}")
    xml = await _search_and_build(anilist_ids, "radarr")
    await cache_set(cache_key, xml, settings.result_cache_ttl)
    return xml_response(xml)


# ── Health check ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "mappings_loaded": mapping.is_loaded(),
    }
