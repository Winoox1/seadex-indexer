from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 3232
    log_level: str = "INFO"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Cache TTLs (seconds)
    result_cache_ttl: int = 21600       # 6 hours
    mapping_cache_ttl: int = 86400      # 24 hours
    # AniBridge mappings
    anibridge_mappings_url: str = (
        "https://github.com/anibridge/anibridge-mappings"
        "/releases/latest/download/mappings.min.json"
    )

    # Nyaa scraping
    nyaa_batch_interval: float = 1.0    # seconds between requests
    nyaa_timeout: int = 15

    # SeaDex
    seadex_base_url: str = "https://releases.moe/api"
    seadex_timeout: int = 15

settings = Settings()
