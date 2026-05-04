# SeaDex Indexer

> [!IMPORTANT]
> **This project was built entirely with AI.** It was made for a personal need, but I decided to share it in case someone else found it useful — use at your own risk. As it wasn't written by me feel free to copy it.

A Prowlarr Torznab indexer that serves the best releases according to **[SeaDex](https://releases.moe)** to Sonarr and Radarr. Uses **[AniBridge mappings](https://github.com/anibridge/anibridge-mappings)**

## Features

- **Sonarr** (`/sonarr/api`) — TVDB ID + season → AniList → SeaDex → Nyaa
- **Radarr** (`/radarr/api`) — TMDB/IMDB ID → AniList → SeaDex → Nyaa
- **Redis caching** — 6-hour result cache, 24-hour mapping cache, must host your own instance of Redis
- **SeaDex tags** — `[SeaDexBest]`, `[SeaDexAlt]`, and all SeaDex compatibility tags
- **Season Packs only** — As SeaDex only categorises full Season Packs, this indexer will also only return full Season Packs no matter if a season or episode search is done

## Quick Start Docker Compose

```yaml
  seadex-indexer:
    container_name: seadex-indexer
    image: ghcr.io/winoox1/seadex-indexer:latest
    ports:
      - 3232:3232
    environment:
      # Point this at your existing Redis instance
      - SEADEX_REDIS_URL=redis://your-redis-host:6379
      # Optional overrides:
      # - SEADEX_PORT=3232
      # - SEADEX_RESULT_CACHE_TTL=21600
      # - SEADEX_MAPPING_CACHE_TTL=86400
      # - SEADEX_NYAA_BATCH_INTERVAL=1.0
      # - SEADEX_LOG_LEVEL=INFO
    restart: unless-stopped
```

```bash
docker compose up -d
```

## Prowlarr Setup

1. Add indexer → **Generic Torznab**
2. For Sonarr: URL = `http://seadex-indexer:3232/sonarr`
3. For Radarr: URL = `http://seadex-indexer:3232/radarr`
4. Click **Test** and **Save**

## Sonarr / Radarr Custom Formats

Create Custom Formats matching these title tags for scoring. The `[SeaDexBest]` and `[SeaDexAlt]` tags are always appended. Compatibility tags are appended when present on the SeaDex entry, you can also make Custom Formats to score these if you wish to.

### Release Quality Tags

| Tag | Meaning |
|-----|---------|
| `[SeaDexBest]` | Marked as Best on SeaDex |
| `[SeaDexAlt]` | Marked as Alt on SeaDex |

### Release Compatibility Tags

| Tag | Meaning |
|-----|---------|
| `[Broken]` | Has minor issues explained in the notes, still watchable |
| `[Deband Recommended]` | Has banding and should ideally be watched with MPV's built in deband feature, but it's still the best option even without debanding. |
| `[Deband Required]` | Has banding and must be watched with MPV's built in deband feature, if you cannot deband then the alt release will provide better quality. |
| `[Dolby Vision]` | Is Dolby Vision Profile 5 which requires a Dolby Vision supported player, device, and screen. Alternatively MPV with an HDR screen. Not meeting this criteria will result in a green/purple image. |
| `[HDR]` | Requires an HDR screen — Not meeting this criteria will result in a washed out image. Alternatively some players will tonemap, but we recommend getting the SDR release instead. |
| `[Incomplete]` | Does not contain all episodes — used when it provides better video/subtitle quality for the episodes it does include |
| `[Misplaced Special]` | Has specials at the top of the file list, often times these specials should be watched after the main series. Make sure you watch in the correct order. | 
| `[Patch Required]` | Requires you to download and run a patch in order to fix issues with the release. Generally the community will upload the pre-patched files to avoid this. |
| `[VFR]` | Has a variable framerate, which means it changes between 24, 30, and even 60fps depending on the scene. In order to display the content correctly your screen should either use VRR or be set to a multiple of 120Hz. |
| `[YUV444P]` | Is encoded with 4:4:4 chroma which has poor hardware support. Generally it will not work on anything outside of a PC, so if you're using a streaming box/stick you'll want to avoid it. |

## Configuration

All settings use the `SEADEX_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `SEADEX_PORT` | `3232` | HTTP port |
| `SEADEX_REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `SEADEX_RESULT_CACHE_TTL` | `21600` | Result cache TTL (seconds) |
| `SEADEX_MAPPING_CACHE_TTL` | `86400` | AniBridge mapping cache TTL (seconds) |
| `SEADEX_NYAA_BATCH_INTERVAL` | `1.0` | Delay between Nyaa requests (seconds) |
| `SEADEX_LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `SEADEX_ANIBRIDGE_MAPPINGS_URL` | `github.com/anibridge/anibridge-mappings/releases/latest/download/mappings.min.json` | URL to AniBridge mappings JSON |

## Health Check

​```
GET /health
​```

Returns:
​```json
{"status": "ok", "mappings_loaded": true}
​```

- `status` is always `ok` if the app is running — it does not check Redis or external services.
- `mappings_loaded` indicates whether the AniBridge ID mapping indexes are populated in memory. If `false`, the app is still starting up or the initial mapping fetch failed — all searches will return empty results until this is `true`.

