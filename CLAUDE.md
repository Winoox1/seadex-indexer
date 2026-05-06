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

# Start Redis for local testing (optional — app will start without it,
# but every request will hit SeaDex and Nyaa directly with no caching)
docker run -d -p 6379:6379 redis:7-alpine

# Run the server (default port 3232)
python run.py
```

## Docker

```bash
# Build and run (users are expected to provide their own Redis instance)
docker compose up --build
```

## Configuration

All settings are in [app/config.py](app/config.py) via `pydantic-settings`. Every field is overridable as an env var matching the field name in uppercase:

| Env var | Default | Description |
|---|---|---|
| `PORT` | `3232` | Uvicorn listen port |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `RESULT_CACHE_TTL` | `21600` | Search result cache (seconds) |
| `MAPPING_CACHE_TTL` | `86400` | AniBridge mapping cache (seconds) |
| `NYAA_BATCH_INTERVAL` | `1.0` | Minimum gap between Nyaa request starts (seconds) |
| `NYAA_CONCURRENCY` | `2` | Max simultaneous Nyaa fetches — start gap is enforced globally so rate never exceeds `1/NYAA_BATCH_INTERVAL` Hz |
| `LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

AniBridge mappings URL is hardcoded to the latest release and is not configurable.

## Architecture

### Request pipeline

```
Sonarr/Radarr → /sonarr/api or /radarr/api
    → mapping.py  (TVDB/TMDB/IMDB → AniList ID, in-memory indexes)
    → Redis cache check
    → seadex.py   (AniList ID → PocketBase API → entry records)
    → seadex.extract_nyaa_torrents()  (filter to nyaa.si URLs, extract IDs)
    → nyaa.py     (scrape each nyaa.si/view/<id> page sequentially)
    → torznab.py  (assemble Torznab XML with [SeaDexBest]/[SeaDexAlt] tags)
    → Redis cache set
```

### Module responsibilities

- **[app/mapping.py](app/mapping.py)** — Downloads the [AniBridge](https://github.com/anibridge/anibridge-mappings) `mappings.min.json` at startup and builds three in-memory reverse indexes: `(tvdb_id, season) → {anilist_ids}`, `tmdb_movie_id → {anilist_ids}`, `imdb_id → {anilist_ids}`. Refreshes on a background task every `MAPPING_CACHE_TTL` seconds. The mapping data is also persisted in Redis to survive restarts.
- **[app/seadex.py](app/seadex.py)** — Calls the SeaDex PocketBase REST API (`/collections/entries/records`) with an OR filter on AniList IDs and `expand=trs`. Extracts Nyaa torrent references from the expanded `trs` relation, filtering to `nyaa.si/view/` URLs only.
- **[app/nyaa.py](app/nyaa.py)** — HTML-scrapes individual `nyaa.si/view/<id>` pages to get title, size, seeders, leechers, info hash, and publish date. Requests are sequential with a configurable delay to avoid rate limiting.
- **[app/torznab.py](app/torznab.py)** — Pure XML builders. Titles are suffixed with `[SeaDexBest]` or `[SeaDexAlt]` based on the `best` flag from SeaDex. Also handles caps responses and Prowlarr health-check pings.
- **[app/cache.py](app/cache.py)** — Thin async Redis wrapper. All failures are caught and logged; the app continues without caching if Redis is unavailable.
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

- AniBridge mappings: cached in Redis under `seadex:anibridge_mappings`, also held in-memory.
- Search results: cached under `seadex:result:sonarr:al:<id>` (Sonarr) or `seadex:result:radarr:al:<id>` (Radarr) — AniList ID uniquely identifies the season.
