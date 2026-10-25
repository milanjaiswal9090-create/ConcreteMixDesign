"""
Application configuration using pydantic-settings.

Loads settings from environment variables and .env file.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "ConcreteMix AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./data/concretemix.db"

    # Security
    ADMIN_KEY: str = "change-me-in-production"

    # File uploads
    UPLOAD_DIR: str = "./data/documents"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10 MB

    # SEO
    BASE_URL: str = "http://localhost:8000"

    # Data directories
    DATA_DIR: str = "./data"
    EXAMPLES_DIR: str = "./data/examples"

    @property
    def upload_path(self) -> Path:
        """Return upload directory as a Path object, creating it if needed."""
        p = Path(self.UPLOAD_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def data_path(self) -> Path:
        """Return data directory as a Path object, creating it if needed."""
        p = Path(self.DATA_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p


# Singleton settings instance
settings = Settings()
