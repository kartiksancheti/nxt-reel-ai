"""
Central application configuration.

Every setting is loaded from environment variables (see .env.example).
Nothing is ever hardcoded here — this file only defines the shape and
defaults, per the "environment variables only" development rule.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_port: int = 8000
    log_level: str = "INFO"

    database_url: str
    redis_url: str

    openai_api_key: str
    openai_director_model: str = "gpt-5"

    storage_root: str = "/data"
    uploads_dir: str = "/data/uploads"
    renders_dir: str = "/data/renders"
    assets_dir: str = "/data/assets"

    stock_footage_api_key: str | None = None
    music_library_api_key: str | None = None
    freesound_api_key: str | None = None
    jamendo_client_id: str | None = None
    browser_demo_url: str | None = None

    # Optional creator branding used by the caption/description generator.
    # Leave any of these unset and that block is simply omitted rather
    # than showing a placeholder — nothing is hardcoded to any specific
    # person's brand.
    creator_instagram_url: str | None = None
    creator_youtube_url: str | None = None
    creator_tiktok_url: str | None = None
    creator_linkedin_url: str | None = None
    creator_community_url: str | None = None
    creator_community_label: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — import this, never instantiate Settings() directly."""
    return Settings()
