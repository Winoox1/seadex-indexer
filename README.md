# SeaDex Indexer

> [!IMPORTANT]
> **This project was built entirely with AI.** It was made for a personal need, but I decided to share it in case someone else found it useful.

A Prowlarr Torznab indexer that serves the best anime releases from **[SeaDex](https://releases.moe)** to Sonarr and Radarr. Uses **[AniBridge mappings](https://github.com/anibridge/anibridge-mappings)** for ID mapping.

Huge thanks to the people maintaining **[SeaDex](https://releases.moe)** so it's easy to grab the best available releases, and to the people maintaining the **[AniBridge mappings](https://github.com/anibridge/anibridge-mappings)** project, this wouldn't be possible without all of their hard work.

## Features

- **Sonarr & Radarr support** - via `/sonarr/api` and `/radarr/api`. Flow is: Sonarr/Radarr request with TVDB ID + Season / TMDB ID or IMDB ID -> Map to AniList ID -> Query SeaDex API -> Scrape Nyaa -> Return to Sonarr/Radarr
- **Caching** - 2-hour result cache to avoid redundant SeaDex and Nyaa requests. Empty results caused by upstream failures (SeaDex/Nyaa outages) are only cached for 60 seconds, so a brief outage doesn't hide results for hours. Cache is cleared on container restart.
- **Add Title Tags** - Adds `[SeaDexBest]`, `[SeaDexAlt]`, and all SeaDex compatibility tags.
- **Add Season or Year to title** - For Sonarr requests, the season it sends will be added as `[SXX]` if it's not present already. For Radarr a year will be added if it's not present already by fetching it from AniList (This improves the chances a release will be recognised but does not guarantee it)
- **Full Seasons only** - No matter if a season or episode search is done, only full seasons will be returned.

> [!TIP]
> Setting most series to **Standard** type in Sonarr is recommended over Anime type as it results in much faster searches. Most modern anime is released in the `SxxEyy` format which makes Standard type a much better fit. Use Anime type for older shows like One Piece and Naruto as they are released in the `001` Absolute format.

> [!NOTE]
> Specials will return results when using Standard series type, but Sonarr will often struggle to recognise them.

## Docker Compose

```yaml
  seadex-indexer:
    container_name: seadex-indexer
    image: ghcr.io/winoox1/seadex-indexer:latest
    ports:
      - 3232:3232
    restart: unless-stopped
```

<details>
<summary>Advanced Configuration</summary>

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3232` | Port the server listens on inside the container |
| `RESULT_CACHE_TTL` | `7200` | Search result cache TTL (seconds) |
| `NEGATIVE_CACHE_TTL` | `7200` | Cache TTL for shows with no SeaDex entry (seconds) |
| `MAPPING_REFRESH_INTERVAL` | `86400` | How often to re-download AniBridge mappings (seconds) |
| `NYAA_BATCH_INTERVAL` | `1.0` | Minimum gap between Nyaa request starts (seconds) |
| `NYAA_CONCURRENCY` | `2` | Max simultaneous Nyaa fetches - request rate never exceeds `1 / NYAA_BATCH_INTERVAL` regardless of this value |
| `LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

</details>

## Prowlarr Setup

Add two separate indexers - one for Sonarr, one for Radarr:

1. Add indexer → **Generic Torznab**
2. Set Indexer name to whatever you like
3. For Sonarr: URL = `http://your-host-here:3232/sonarr`
4. For Radarr: URL = `http://your-host-here:3232/radarr`
5. Click **Test** and **Save**

## Sonarr / Radarr Custom Formats

Create Custom Formats matching the below tags for scoring.

### Release Quality Tags

| Tag | Meaning |
|-----|---------|
| `[SeaDexBest]` | Marked as Best on SeaDex |
| `[SeaDexAlt]` | Marked as Alt on SeaDex |

<details>
<summary>Example CFs - SeaDex Best &amp; Alt</summary>

**SeaDex Best**
```json
{
  "name": "SeaDex Best",
  "includeCustomFormatWhenRenaming": false,
  "specifications": [
    {
      "name": "SeaDex best match",
      "implementation": "ReleaseTitleSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": "\\[SeaDexBest\\]"
      }
    }
  ]
}
```

**SeaDex Alt**
```json
{
  "name": "SeaDex Alt",
  "includeCustomFormatWhenRenaming": false,
  "specifications": [
    {
      "name": "SeaDex alt match",
      "implementation": "ReleaseTitleSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": "\\[SeaDexAlt\\]"
      }
    }
  ]
}
```

</details>

### Release Compatibility Tags

| Tag | Meaning |
|-----|---------|
| `[Broken]` | Has minor issues explained in the notes, still watchable |
| `[Deband Recommended]` | Has banding and should ideally be watched with MPV's built in deband feature, but it's still the best option even without debanding. |
| `[Deband Required]` | Has banding and must be watched with MPV's built in deband feature, if you cannot deband then the alt release will provide better quality. |
| `[Dolby Vision]` | Is Dolby Vision Profile 5 which requires a Dolby Vision supported player, device, and screen. Alternatively MPV with an HDR screen. Not meeting this criteria will result in a green/purple image. |
| `[HDR]` | Requires an HDR screen - Not meeting this criteria will result in a washed out image. Alternatively some players will tonemap, but we recommend getting the SDR release instead. |
| `[Incomplete]` | Does not contain all episodes - used when it provides better video/subtitle quality for the episodes it does include |
| `[Mis-Spec]` | Has specials at the top of the file list, often these specials should be watched after the main series. Make sure you watch in the correct order. (Renamed from SeaDex's `Misplaced Special` to avoid Sonarr treating the release as a Special) | 
| `[Patch Required]` | Requires you to download and run a patch in order to fix issues with the release. Generally the community will upload the pre-patched files to avoid this. |
| `[VFR]` | Has a variable framerate, which means it changes between 24, 30, and even 60fps depending on the scene. In order to display the content correctly your screen should either use VRR or be set to a multiple of 120Hz. |
| `[YUV444P]` | Is encoded with 4:4:4 chroma which has poor hardware support. Generally it will not work on anything outside of a PC, so if you're using a streaming box/stick you'll want to avoid it. |

<details>
<summary>Example CFs - Compatibility Tags</summary>

**Broken**
```json
{
  "name": "Broken",
  "includeCustomFormatWhenRenaming": false,
  "specifications": [
    {
      "name": "Broken match",
      "implementation": "ReleaseTitleSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": "\\[Broken\\]"
      }
    }
  ]
}
```

**Deband Recommended**
```json
{
  "name": "Deband Recommended",
  "includeCustomFormatWhenRenaming": false,
  "specifications": [
    {
      "name": "Deband recommended match",
      "implementation": "ReleaseTitleSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": "\\[Deband Recommended\\]"
      }
    }
  ]
}
```

**Deband Required**
```json
{
  "name": "Deband Required",
  "includeCustomFormatWhenRenaming": false,
  "specifications": [
    {
      "name": "Deband required match",
      "implementation": "ReleaseTitleSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": "\\[Deband Required\\]"
      }
    }
  ]
}
```

**Dolby Vision**
```json
{
  "name": "Dolby Vision",
  "includeCustomFormatWhenRenaming": false,
  "specifications": [
    {
      "name": "Dolby Vision match",
      "implementation": "ReleaseTitleSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": "\\[Dolby Vision\\]"
      }
    }
  ]
}
```

**HDR**
```json
{
  "name": "HDR",
  "includeCustomFormatWhenRenaming": false,
  "specifications": [
    {
      "name": "HDR match",
      "implementation": "ReleaseTitleSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": "\\[HDR\\]"
      }
    }
  ]
}
```

**Incomplete**
```json
{
  "name": "Incomplete",
  "includeCustomFormatWhenRenaming": false,
  "specifications": [
    {
      "name": "Incomplete match",
      "implementation": "ReleaseTitleSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": "\\[Incomplete\\]"
      }
    }
  ]
}
```

**Mis-Spec**
```json
{
  "name": "Mis-Spec",
  "includeCustomFormatWhenRenaming": false,
  "specifications": [
    {
      "name": "Mis-Spec match",
      "implementation": "ReleaseTitleSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": "\\[Mis-Spec\\]"
      }
    }
  ]
}
```

**Patch Required**
```json
{
  "name": "Patch Required",
  "includeCustomFormatWhenRenaming": false,
  "specifications": [
    {
      "name": "Patch required match",
      "implementation": "ReleaseTitleSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": "\\[Patch Required\\]"
      }
    }
  ]
}
```

**VFR**
```json
{
  "name": "VFR",
  "includeCustomFormatWhenRenaming": false,
  "specifications": [
    {
      "name": "VFR match",
      "implementation": "ReleaseTitleSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": "\\[VFR\\]"
      }
    }
  ]
}
```

**YUV444P**
```json
{
  "name": "YUV444P",
  "includeCustomFormatWhenRenaming": false,
  "specifications": [
    {
      "name": "YUV444P match",
      "implementation": "ReleaseTitleSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": "\\[YUV444P\\]"
      }
    }
  ]
}
```

</details>

## Endpoints

### Health check

```
GET /health
```

Returns `{"status": "ok", "mappings_loaded": true}` with HTTP 200 once mappings are loaded.

- While mappings are not loaded (still starting up, or the initial AniBridge fetch failed) it returns HTTP **503** with `{"status": "unavailable", "mappings_loaded": false}` — searches would return empty results in this state, and the Docker healthcheck reports the container as unhealthy.

- If the initial mapping fetch failed, the app retries every 60 seconds until it succeeds, so this state normally resolves itself.

### Debug

```
GET /debug
GET /debug?tvdb=357492&season=1
GET /debug?tmdb=283984
GET /debug?imdb=tt4054952
```

Returns mapping index counts and last refresh time. Pass `tvdb`+`season`, `tmdb`, or `imdb` to see what AniList IDs a given ID resolves to.

### Clear cache

```
POST /cache/clear
```

Clears all in-memory cached results.
