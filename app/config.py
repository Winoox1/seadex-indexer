from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    port: int = 3232
    log_level: str = "INFO"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Cache TTLs (seconds)
    result_cache_ttl: int = 21600       # 6 hours
    mapping_cache_ttl: int = 86400      # 24 hours

    # Nyaa scraping
    nyaa_batch_interval: float = 1.0    # seconds between requests
    nyaa_timeout: int = 15


settings = Settings()
