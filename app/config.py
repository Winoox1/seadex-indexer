from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    port: int = 3232
    log_level: str = "INFO"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Cache TTLs (seconds)
    result_cache_ttl: int = 21600       # 6 hours
    negative_cache_ttl: int = 3600     # 1 hour — for AniList IDs with no SeaDex entry
    mapping_cache_ttl: int = 86400      # 24 hours

    # Nyaa scraping
    nyaa_batch_interval: float = 1.0    # minimum seconds between request starts
    nyaa_concurrency: int = 2           # max in-flight requests at once


settings = Settings()
