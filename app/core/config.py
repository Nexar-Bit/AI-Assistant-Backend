import os
import secrets
from functools import lru_cache
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    API_V1_PREFIX: str = "/api/v1"

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production-" + secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"

    # Database
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "vehicle_ai"

    # pgvector
    PGVECTOR_ENABLED: bool = True

    # Redis (Optional - set to empty string or "none" to disable)
    REDIS_URL: str | None = None

    # PDF
    PDF_OUTPUT_DIR: str = "pdf_output"

    # OpenAI
    OPENAI_API_KEY: str | None = None
    UPLOAD_DIR: str = "uploads"
    
    # Email (for registration and notifications)
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_FROM_NAME: str = "Vehicle Diagnostics AI"
    FRONTEND_URL: str = "http://localhost:5173"
    
    # Registration settings
    AUTO_APPROVE_REGISTRATION: bool = False  # If True, users are auto-approved
    ADMIN_NOTIFICATION_EMAIL: str | None = None  # Email to notify for new registrations

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Normalize environment value."""
        return v.lower()

    @model_validator(mode="after")
    def validate_secret_key_production(self):
        """Validate SECRET_KEY is secure in production."""
        environment = self.ENVIRONMENT.lower()
        
        # In production, ensure SECRET_KEY is set and secure
        if environment in ("production", "staging"):
            if not self.SECRET_KEY or self.SECRET_KEY.startswith("dev-secret-key"):
                raise ValueError(
                    "SECRET_KEY must be set to a secure value in production. "
                    "Generate one using: python scripts/generate_secret_key.py"
                )
            if len(self.SECRET_KEY) < 32:
                raise ValueError("SECRET_KEY must be at least 32 characters long in production")
        
        return self

    @property
    def database_url(self) -> str:
        """Construct database URL from components."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


