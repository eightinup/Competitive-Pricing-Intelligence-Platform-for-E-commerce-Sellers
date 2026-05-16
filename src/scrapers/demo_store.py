"""Demo scraper that extracts product data from local e-commerce mock pages."""

from __future__ import annotations

import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from loguru import logger
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page

from src.config import get_settings
from src.schemas.product_snapshot import ProductSnapshot
from src.scrapers.base import BaseScraper, ScraperResult
from src.scrapers.playwright_client import AsyncPlaywrightClient, PlaywrightClientConfig


class DemoStoreScraper(BaseScraper):
    """Scrapes local mock HTML pages with Playwright-compatible selectors."""

    source = "demo_store"

    def __init__(
        self,
        *,
        mock_pages_dir: Path | None = None,
        selectors_path: Path | None = None,
        prefer_playwright: bool = True,
    ) -> None:
        settings = get_settings()
        self.mock_pages_dir = mock_pages_dir or settings.mock_pages_dir
        self.selectors_path = selectors_path or settings.selectors_path
        self.prefer_playwright = prefer_playwright
        self.config = PlaywrightClientConfig(
            user_agent=settings.scraper_user_agent,
            timeout_ms=settings.scrape_timeout_ms,
            delay_seconds=settings.scrape_delay_seconds,
        )
        self.retry_count = settings.scrape_retry_count
        self.selectors = self._load_selectors()

    def scrape_all(self) -> ScraperResult:
        snapshots: list[ProductSnapshot] = []
        errors: list[str] = []
        files = sorted(self.mock_pages_dir.glob("*.html"))
        if not files:
            return ScraperResult(self.source, snapshots, [f"No mock HTML files found in {self.mock_pages_dir}"])

        for path in files:
            try:
                snapshots.extend(self.scrape_file(path))
            except Exception as exc:  # pragma: no cover - defensive logging boundary
                message = f"{path.name}: {exc}"
                logger.exception("Failed to scrape {}", path)
                errors.append(message)
        logger.info("Demo scraper extracted {} snapshots with {} errors", len(snapshots), len(errors))
        return ScraperResult(self.source, snapshots, errors)

    def scrape_file(self, path: Path) -> list[ProductSnapshot]:
        if self.prefer_playwright:
            try:
                return self._run_playwright_in_worker(path)
            except PlaywrightError as exc:
                logger.warning("Playwright unavailable for {}. Falling back to static parser: {}", path.name, exc)
            except Exception as exc:
                logger.warning("Playwright scrape failed for {}. Falling back to static parser: {}", path.name, exc)
        return self._scrape_file_static(path)

    def _run_playwright_in_worker(self, path: Path) -> list[ProductSnapshot]:
        """Run Playwright away from hosts that already own an event loop."""
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(self._scrape_file_with_playwright, path).result()

    def _scrape_file_with_playwright(self, path: Path) -> list[ProductSnapshot]:
        return asyncio.run(self._scrape_file_with_playwright_async(path))

    async def _scrape_file_with_playwright_async(self, path: Path) -> list[ProductSnapshot]:
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                async with AsyncPlaywrightClient(self.config) as client:
                    page = await client.open_file(path)
                    await page.wait_for_selector(self.selectors["product_container"])
                    snapshots = await self._extract_page(page)
                    await page.close()
                    await asyncio.sleep(self.config.delay_seconds)
                    return snapshots
            except Exception as exc:
                last_error = exc
                if attempt < self.retry_count:
                    await asyncio.sleep(self.config.delay_seconds)
        if last_error:
            raise last_error
        return []

    async def _extract_page(self, page: Page) -> list[ProductSnapshot]:
        root = page.locator(self.selectors["source_root"])
        source_name = await root.get_attribute(self.selectors["source_name_attr"]) or "DemoStore"
        marketplace = await root.get_attribute(self.selectors["marketplace_attr"]) or "Demo Marketplace"
        base_url = await root.get_attribute(self.selectors["base_url_attr"]) or "https://demo.local"
        cards = page.locator(self.selectors["product_container"])
        snapshots = []
        for index in range(await cards.count()):
            card = cards.nth(index)
            snapshots.append(await self._snapshot_from_values(card, source_name, marketplace, base_url))
        return snapshots

    async def _snapshot_from_values(
        self,
        card: Locator,
        source_name: str,
        marketplace: str,
        base_url: str,
    ) -> ProductSnapshot:
        url = await self._attribute(card, "product_url", "href")
        if url and url.startswith("/"):
            url = f"{base_url.rstrip('/')}{url}"
        values = {
            "sku": await self._text(card, "sku"),
            "product_name": await self._text(card, "product_name"),
            "category": await self._text(card, "category"),
            "current_price": parse_money(await self._text(card, "current_price")),
            "old_price": parse_money(await self._text(card, "old_price")),
            "discount_percent": parse_percent(await self._text(card, "discount_percent")),
            "in_stock": parse_stock_status(await self._text(card, "stock_status")),
            "rating": parse_decimal(await self._text(card, "rating")),
            "review_count": parse_int(await self._text(card, "review_count")),
            "seller_name": await self._text(card, "seller_name"),
            "product_url": url or base_url,
            "marketplace": marketplace,
            "source_name": source_name,
        }
        return ProductSnapshot(raw_payload=values.copy(), **values)

    async def _text(self, card: Locator, selector_key: str) -> str | None:
        selector = self.selectors[selector_key]
        locator = card.locator(selector)
        if await locator.count() == 0:
            return None
        text = (await locator.first.inner_text()).strip()
        return text or None

    async def _attribute(self, card: Locator, selector_key: str, attribute: str) -> str | None:
        selector = self.selectors[selector_key]
        locator = card.locator(selector)
        if await locator.count() == 0:
            return None
        return await locator.first.get_attribute(attribute)

    def _scrape_file_static(self, path: Path) -> list[ProductSnapshot]:
        html = path.read_text(encoding="utf-8")
        body_attrs = _extract_body_attrs(html)
        source_name = body_attrs.get("data-source", "DemoStore")
        marketplace = body_attrs.get("data-marketplace", "Demo Marketplace")
        base_url = body_attrs.get("data-base-url", "https://demo.local")
        cards = re.findall(
            r"<article[^>]+data-testid=[\"']product-card[\"'][^>]*>(.*?)</article>",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        snapshots = []
        for card_html in cards:
            url = _extract_attr_by_testid(card_html, "product-url", "href")
            if url and url.startswith("/"):
                url = f"{base_url.rstrip('/')}{url}"
            values = {
                "sku": _extract_text_by_testid(card_html, "sku"),
                "product_name": _extract_text_by_testid(card_html, "product-name"),
                "category": _extract_text_by_testid(card_html, "category"),
                "current_price": parse_money(_extract_text_by_testid(card_html, "current-price")),
                "old_price": parse_money(_extract_text_by_testid(card_html, "old-price")),
                "discount_percent": parse_percent(_extract_text_by_testid(card_html, "discount-percent")),
                "in_stock": parse_stock_status(_extract_text_by_testid(card_html, "stock-status")),
                "rating": parse_decimal(_extract_text_by_testid(card_html, "rating")),
                "review_count": parse_int(_extract_text_by_testid(card_html, "review-count")),
                "seller_name": _extract_text_by_testid(card_html, "seller-name"),
                "product_url": url or base_url,
                "marketplace": marketplace,
                "source_name": source_name,
            }
            snapshots.append(ProductSnapshot(raw_payload=values.copy(), **values))
        return snapshots

    def _load_selectors(self) -> dict[str, str]:
        with self.selectors_path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file)
        return config["demo_store"]


def parse_money(value: str | None) -> Decimal | None:
    if not value:
        return None
    cleaned = re.sub(r"[^\d.,-]", "", value).replace(" ", "")
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", "")
    return Decimal(cleaned)


def parse_percent(value: str | None) -> Decimal | None:
    if not value:
        return None
    cleaned = re.sub(r"[^\d.,-]", "", value)
    if not cleaned:
        return None
    return Decimal(cleaned.replace(",", "."))


def parse_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", value)
    if not match:
        return None
    return Decimal(match.group(0).replace(",", "."))


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def parse_stock_status(value: str | None) -> bool:
    if not value:
        return True
    lowered = value.lower()
    return not any(marker in lowered for marker in ("out", "нет", "sold"))


def _extract_body_attrs(html: str) -> dict[str, str]:
    match = re.search(r"<body([^>]*)>", html, flags=re.IGNORECASE)
    if not match:
        return {}
    attrs = re.findall(r"([\w-]+)=[\"']([^\"']*)[\"']", match.group(1))
    return dict(attrs)


def _extract_text_by_testid(html: str, testid: str) -> str | None:
    pattern = rf"<[^>]+data-testid=[\"']{re.escape(testid)}[\"'][^>]*>(.*?)</[^>]+>"
    match = re.search(pattern, html, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    text = re.sub(r"<[^>]+>", "", match.group(1))
    return " ".join(text.split()) or None


def _extract_attr_by_testid(html: str, testid: str, attr: str) -> str | None:
    pattern = rf"<[^>]+data-testid=[\"']{re.escape(testid)}[\"'][^>]*>"
    match = re.search(pattern, html, flags=re.IGNORECASE)
    if not match:
        return None
    attrs = re.findall(r"([\w-]+)=[\"']([^\"']*)[\"']", match.group(0))
    return dict(attrs).get(attr)
