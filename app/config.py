from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    port: int = 3232
    log_level: str = "INFO"

    # Cache TTLs (seconds)
    result_cache_ttl: int = 7200         # 2 hours
    negative_cache_ttl: int = 7200       # 2 hours — for AniList IDs with no SeaDex entry

    # AniBridge mapping refresh interval (seconds)
    mapping_refresh_interval: int = 86400  # 24 hours

    # Nyaa scraping
    nyaa_batch_interval: float = 1.0    # minimum seconds between request starts
    nyaa_concurrency: int = 2           # max in-flight requests at once


settings = Settings()
