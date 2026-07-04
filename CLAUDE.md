# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working in this repo

Retain all existing architecture and design decisions that are already in place. When making changes, work within the established patterns — don't introduce new abstractions, restructure modules, or change how things are wired together unless explicitly asked.

## What this is

A Torznab-compatible indexer that bridges **SeaDex** (curated anime release database at releases.moe) with **Sonarr** and **Radarr** via Prowlarr. It exposes two endpoints (`/sonarr/api`, `/radarr/api`) that translate TVDB/TMDB/IMDB IDs → AniList IDs → SeaDex entries → Nyaa torrent metadata → Torznab XML.

## Running locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server (default port 3232)
python run.py
```

## Docker

```bash
docker compose up --build
```

## Configuration

All settings are in [app/config.py](app/config.py) via `pydantic-settings`. Every field is overridable as an env var matching the field name in uppercase:

| Env var | Default | Description |
|---|---|---|
| `PORT` | `3232` | Uvicorn listen port |
| `RESULT_CACHE_TTL` | `7200` | Search result cache (seconds) |
| `NEGATIVE_CACHE_TTL` | `7200` | Cache for genuinely empty results — AniList IDs with no SeaDex entry (seconds) |
| `MAPPING_REFRESH_INTERVAL` | `86400` | How often to re-download AniBridge mappings (seconds) |
| `NYAA_BATCH_INTERVAL` | `1.0` | Minimum gap between Nyaa request starts (seconds) |
| `NYAA_CONCURRENCY` | `2` | Max simultaneous Nyaa fetches — start gap is enforced globally so rate never exceeds `1/NYAA_BATCH_INTERVAL` Hz |
| `LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

AniBridge mappings URL is hardcoded to the latest release and is not configurable.

## Architecture

### Request pipeline

```
Sonarr/Radarr → /sonarr/api or /radarr/api
    → mapping.py  (TVDB/TMDB/IMDB → AniList ID, in-memory indexes)
    → cache check (in-memory)
    → seadex.py   (AniList ID → PocketBase API → entry records)
    → seadex.extract_nyaa_torrents()  (filter to nyaa.si URLs, extract IDs)
    → nyaa.py     (scrape each nyaa.si/view/<id> page sequentially)
    → torznab.py  (assemble Torznab XML with [SeaDexBest]/[SeaDexAlt] tags)
    → cache set (in-memory)
```

### Module responsibilities

- **[app/mapping.py](app/mapping.py)** — Downloads the [AniBridge](https://github.com/anibridge/anibridge-mappings) `mappings.min.json` at startup and builds three in-memory reverse indexes: `(tvdb_id, season) → {anilist_ids}`, `tmdb_movie_id → {anilist_ids}`, `imdb_id → {anilist_ids}`. Refreshes on a background task every `MAPPING_REFRESH_INTERVAL` seconds (retries every 60 s while not yet loaded, e.g. after a failed startup fetch). The CPU-bound JSON parse + index build runs in `asyncio.to_thread` on local dicts, and the live indexes are swapped in atomically at the end — lookups keep hitting the old indexes during a rebuild, so `_build_indexes` must never mutate the globals in place.
- **[app/seadex.py](app/seadex.py)** — Calls the SeaDex PocketBase REST API (`/collections/entries/records`) with an OR filter on AniList IDs and `expand=trs`. Extracts Nyaa torrent references from the expanded `trs` relation, filtering to `nyaa.si/view/` URLs only.
- **[app/nyaa.py](app/nyaa.py)** — HTML-scrapes individual `nyaa.si/view/<id>` pages to get title, size, seeders, leechers, info hash, and publish date. Requests are sequential with a configurable delay to avoid rate limiting.
- **[app/torznab.py](app/torznab.py)** — Pure XML builders. Titles are suffixed with `[SeaDexBest]` or `[SeaDexAlt]` based on the `best` flag from SeaDex. Also handles caps responses and Prowlarr health-check pings.
- **[app/cache.py](app/cache.py)** — In-memory TTL cache backed by a plain Python dict. Synchronous. Expiry is lazy (checked on read), plus a full sweep of expired entries (`cache_purge_expired`) piggybacked on the mapping refresh loop so never-re-read keys don't accumulate. Exposes `cache_get`, `cache_set`, `cache_delete`, `cache_clear`, and `cache_purge_expired`.
- **[app/config.py](app/config.py)** — Single `Settings` instance (`settings`) imported everywhere.

### SeaDex API

SeaDex runs on PocketBase. We query:

```
GET https://releases.moe/api/collections/entries/records
    ?filter=alID=101348||alID=101349
    &expand=trs
    &perPage=50
```

The response is a paginated PocketBase envelope. Only `items` is used:

```json
{
  "items": [
    {
      "alID": 19603,
      "expand": {
        "trs": [
          {
            "isBest": true,
            "releaseGroup": "FateSucks",
            "tags": ["Deband Required"],
            "tracker": "Nyaa",
            "url": "https://nyaa.si/view/1890595",
            "infoHash": "8e41a4ebf3503dc52f2a8119a3fa58c4d6b8ca78"
          },
          {
            "isBest": true,
            "tracker": "AB",
            "url": "/torrents.php?id=22758&torrentid=1139045",
            "infoHash": "<redacted>"
          }
        ]
      },
      "trs": ["08knp4fattgxv43", "wk2icdhxklmg48i"]
    }
  ]
}
```

Key fields on each torrent record in `trs`:
- `tracker` — `"Nyaa"` or `"AB"` (AnimeBytes). Currently only Nyaa entries are used. AB entries have relative URLs and redacted infohashes, but support could be added in the future.
- `url` — full URL for Nyaa (`https://nyaa.si/view/<id>`), relative path for AB (currently filtered out).
- `isBest` — whether SeaDex considers this the best release.
- `tags` — compatibility/warning tags (e.g. `"Deband Required"`, `"YUV444P"`).

### Nyaa scraping

Each Nyaa torrent page at `https://nyaa.si/view/<id>` is HTML-scraped. The elements we extract:

| Field | HTML source |
|---|---|
| Title | `<h3 class="panel-title">` (inner text, strip child tags) |
| File size | `File size:</div>` sibling div text (e.g. `"83.2 GiB"`) |
| Info hash | `<kbd>` containing a hex string |
| Seeders | `<span style="color: green;">` |
| Leechers | `<span style="color: red;">` |
| Publish date | First `data-timestamp` attribute (Unix seconds → RFC 2822) |

Download link is constructed as `https://nyaa.si/download/<id>.torrent` — it is never present on the page itself.

### Caching strategy

All caching is in-memory (a plain Python dict with TTL expiry in `app/cache.py`). No external dependencies.

- AniBridge mappings: held in the three in-memory index dicts, re-fetched from AniBridge on startup and every `MAPPING_REFRESH_INTERVAL` seconds.
- Search results: cached under `seadex:result:sonarr:al:<id>:s<season>` (Sonarr) or `seadex:result:radarr:al:<id>` (Radarr). Season is included in the Sonarr key because some shows have multiple TVDB seasons mapped to the same AniList ID.
- Empty results are cached with a TTL that depends on *why* they are empty (`_search_and_build` in `app/main.py` returns the XML together with its TTL): a genuine miss (SeaDex has no entry, or no Nyaa torrents in the entry) gets `NEGATIVE_CACHE_TTL`; an upstream failure (SeaDex API error, or all Nyaa fetches failed) gets the hardcoded `ERROR_CACHE_TTL` (60 s, deliberately not configurable) so transient outages are retried quickly instead of being remembered for hours.
- AniList start years (used for Radarr title tagging): cached under `anilist:year:<id>` for 24 hours — long enough to skip repeat GraphQL calls, short enough that occasional year corrections on AniList propagate within a day.
- Cache can be cleared at runtime via `POST /cache/clear` without restarting.
- `GET /health` returns 503 (not 200) while mappings are not loaded, so the Docker `HEALTHCHECK` marks a container that failed its AniBridge startup fetch as unhealthy.
