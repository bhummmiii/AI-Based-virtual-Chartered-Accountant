# ============================================================
# Application Settings (Pydantic Settings)
# ============================================================

# from pydantic_settings import BaseSettings
# from functools import lru_cache


# class Settings(BaseSettings):
#     """Application settings loaded from environment variables."""
#     
#     APP_NAME: str = "AI-Based Chartered Accountant"
#     APP_ENV: str = "development"
#     DEBUG: bool = True
#     
#     # Database
#     DATABASE_URL: str = ""
#     
#     # JWT
#     JWT_SECRET_KEY: str = ""
#     JWT_ALGORITHM: str = "HS256"
#     JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
#     
#     # Gemini
#     GEMINI_API_KEY: str = ""
#     
#     class Config:
#         env_file = ".env"


# @lru_cache
# def get_settings() -> Settings:
#     return Settings()

# TODO: Uncomment and configure settings
