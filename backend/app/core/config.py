"""
Application Configuration — Pydantic Settings
Loads all environment variables with sensible defaults.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # ── Application ───────────────────────────────
    APP_NAME: str = "AI-Based Chartered Accountant API"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # ── Server ────────────────────────────────────
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    # ── Database ──────────────────────────────────
    DATABASE_URL: str = "postgresql+psycopg://ca_admin:ca_secure_password@localhost:5432/ca_assistant_db"

    # ── JWT Authentication ────────────────────────
    JWT_SECRET_KEY: str = "super-secret-jwt-key-change-in-production-2026"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── CORS ──────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:5174"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    # ── Logging ───────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── File Upload ───────────────────────────────
    UPLOAD_DIR: str = "uploads"          # relative to backend/ directory
    MAX_UPLOAD_SIZE_MB: int = 20
    ALLOWED_EXTENSIONS: str = "pdf,jpg,jpeg,png,webp,csv,xlsx,xls,json,xml,zip,docx"

    @property
    def allowed_extensions_set(self) -> set:
        return {ext.strip().lower() for ext in self.ALLOWED_EXTENSIONS.split(",")}

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    """Cached singleton for application settings."""
    return Settings()
