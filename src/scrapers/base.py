"""Base scraper contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from src.schemas.product_snapshot import ProductSnapshot


@dataclass(frozen=True)
class ScraperResult:
    """Result returned by scraper adapters."""

    source: str
    snapshots: list[ProductSnapshot]
    errors: list[str]


class BaseScraper(ABC):
    """Abstract base class for all marketplace and competitor scrapers."""

    source: str

    @abstractmethod
    def scrape_all(self) -> ScraperResult:
        """Scrape all configured product pages for this source."""

    @abstractmethod
    def scrape_file(self, path: Path) -> list[ProductSnapshot]:
        """Scrape a local demo HTML file."""
