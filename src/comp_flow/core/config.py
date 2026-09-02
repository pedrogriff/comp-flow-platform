"""Application Configuration using Pydantic Settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """CompFlow Microservice Environment Configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Service Metadata
    APP_NAME: str = "CompFlow Platform"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Server Bindings
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security & JWT Auth
    SECRET_KEY: str = "comp-flow-enterprise-super-secret-key-change-in-prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    API_KEY_HEADER_NAME: str = "X-API-Key"
    MASTER_API_KEY: str = "compflow-master-service-key-2026"

    # Database Settings
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/compflow"
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis Cache Settings
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_BAND_CACHE_TTL_SECONDS: int = 3600
    REDIS_BUDGET_CACHE_TTL_SECONDS: int = 300

    # CORS Settings
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://playgriff.me",
        "https://www.playgriff.me",
        "https://compflow.10.0.0.170.nip.io",
        "https://compflow.homelab.local",
    ]


settings = Settings()
