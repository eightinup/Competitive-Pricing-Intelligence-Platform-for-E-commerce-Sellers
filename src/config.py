"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    """Runtime settings for local development and production deployments."""

    database_url: str = Field(default=f"sqlite:///{(PROJECT_ROOT / 'data' / 'price_monitor.db').as_posix()}")
    currency: str = "KZT"
    price_drop_alert_percent: float = 10.0
    price_increase_alert_percent: float = 10.0
    scrape_delay_seconds: float = 0.5
    scrape_timeout_ms: int = 15_000
    scrape_retry_count: int = 2
    scraper_user_agent: str = (
        "Mozilla/5.0 (compatible; PriceMonitorBot/1.0; +https://example.local/legal)"
    )
    log_level: str = "INFO"
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    mock_pages_dir: Path = PROJECT_ROOT / "data" / "mock_pages"
    seed_dir: Path = PROJECT_ROOT / "data" / "seed"
    export_dir: Path = PROJECT_ROOT / "data" / "exports"
    log_dir: Path = PROJECT_ROOT / "logs"
    selectors_path: Path = PROJECT_ROOT / "src" / "scrapers" / "selectors.yaml"

    @field_validator("database_url")
    @classmethod
    def normalize_sqlite_url(cls, value: str) -> str:
        """Allow DATABASE_URL=sqlite:///data/file.db relative to the project root."""
        prefix = "sqlite:///"
        if value.startswith(prefix):
            raw_path = value.removeprefix(prefix)
            if raw_path in {"", ":memory:"}:
                return value
            if raw_path and not Path(raw_path).is_absolute():
                return f"{prefix}{(PROJECT_ROOT / raw_path).as_posix()}"
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        database_url=os.getenv("DATABASE_URL", Settings().database_url),
        currency=os.getenv("CURRENCY", "KZT"),
        price_drop_alert_percent=float(os.getenv("PRICE_DROP_ALERT_PERCENT", "10")),
        price_increase_alert_percent=float(os.getenv("PRICE_INCREASE_ALERT_PERCENT", "10")),
        scrape_delay_seconds=float(os.getenv("SCRAPE_DELAY_SECONDS", "0.5")),
        scrape_timeout_ms=int(os.getenv("SCRAPE_TIMEOUT_MS", "15000")),
        scrape_retry_count=int(os.getenv("SCRAPE_RETRY_COUNT", "2")),
        scraper_user_agent=os.getenv("SCRAPER_USER_AGENT", Settings().scraper_user_agent),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )


def configure_logging(settings: Settings | None = None) -> None:
    """Configure Loguru for console and rotating file logs."""
    settings = settings or get_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, colorize=True)
    logger.add(
        settings.log_dir / "price_monitor.log",
        level=settings.log_level,
        rotation="5 MB",
        retention="14 days",
        enqueue=True,
    )
