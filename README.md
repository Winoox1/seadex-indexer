# SeaDex Indexer

> [!IMPORTANT]
> **This project was built entirely with AI.** It was made for a personal need, but I decided to share it in case someone else found it useful — use at your own risk. As it wasn't written by me feel free to copy it.

A Prowlarr Torznab indexer that serves the best releases according to **[SeaDex](https://releases.moe)** to Sonarr and Radarr. Uses **[AniBridge mappings](https://github.com/anibridge/anibridge-mappings)**

## Features

- **Sonarr** (`/sonarr/api`) — TVDB ID + season → AniList → SeaDex → Nyaa
- **Radarr** (`/radarr/api`) — TMDB/IMDB ID → AniList → SeaDex → Nyaa
- **Redis caching** — 6-hour result cache, 24-hour mapping cache, must host your own instance of Redis
- **Relase Title enchancements** — Adds `[SeaDexBest]`, `[SeaDexAlt]`, and all SeaDex compatibility tags, aditionally will add the season number sent by Sonarr as SXX if its not present already, for Radarr a year will be added if not present yet by fetching it from AniList
- **Season Packs only** — As SeaDex only categorises full Season Packs, this indexer will also only return full Season Packs no matter if a season or episode search is done

> [!IMPORTANT]  
> **Specials not supported** — Sonarr does not send enough information to reliably identify a specials search, so specials searches will return no results


## Quick Start Docker Compose

```yaml
  seadex-indexer:
    container_name: seadex-indexer
    image: ghcr.io/winoox1/seadex-indexer:latest
    ports:
      - 3232:3232
    environment:
      # Point this at your existing Redis instance
      - REDIS_URL=redis://your-redis-host:6379
      # Optional overrides:
      # - PORT=3232
      # - RESULT_CACHE_TTL=21600
      # - MAPPING_CACHE_TTL=86400
      # - NYAA_BATCH_INTERVAL=1.0
      # - LOG_LEVEL=INFO
    restart: unless-stopped
```

```bash
docker compose up -d
```

## Prowlarr Setup

Add two separate indexers — one for Sonarr, one for Radarr:

1. Add indexer → **Generic Torznab**
2. For Sonarr: URL = `http://seadex-indexer:3232/sonarr`
3. For Radarr: URL = `http://seadex-indexer:3232/radarr`
4. Click **Test** and **Save**

**Optional — restricting to specific app instances via tags:**

> [!IMPORTANT]
> Tags should be used with caution, they can have unintended effects. An app with a tag will sonly sync with indexers having the same tag.

If you run multiple Sonarr or Radarr instances and want to sync each indexer only to your anime instance, assign tags in Prowlarr:

- Add tag `anime` to the Sonarr indexer → set the same tag on your anime Sonarr instance in Prowlarr → Settings → Apps
- Add tag `anime-movies` to the Radarr indexer → set the same tag on your anime Radarr instance

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

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3232` | HTTP port |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `RESULT_CACHE_TTL` | `21600` | Result cache TTL (seconds) |
| `MAPPING_CACHE_TTL` | `86400` | AniBridge mapping cache TTL (seconds) |
| `NYAA_BATCH_INTERVAL` | `1.0` | Delay between Nyaa requests (seconds) |
| `LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

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

