"""Thin Playwright client wrapper with explicit scraping settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from playwright.async_api import Browser as AsyncBrowser
from playwright.async_api import BrowserContext as AsyncBrowserContext
from playwright.async_api import Page as AsyncPage
from playwright.async_api import Playwright as AsyncPlaywright
from playwright.async_api import async_playwright
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright


@dataclass(frozen=True)
class PlaywrightClientConfig:
    """Browser scraping configuration."""

    user_agent: str
    timeout_ms: int
    delay_seconds: float
    headless: bool = True


class PlaywrightClient:
    """Context manager for a single Chromium browser session."""

    def __init__(self, config: PlaywrightClientConfig) -> None:
        self.config = config
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def __enter__(self) -> "PlaywrightClient":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.config.headless)
        self._context = self._browser.new_context(user_agent=self.config.user_agent)
        self._context.set_default_timeout(self.config.timeout_ms)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def open_file(self, path: Path) -> Page:
        """Open a local HTML page and return the Playwright page object."""
        if self._context is None:
            raise RuntimeError("PlaywrightClient must be used as a context manager.")
        page = self._context.new_page()
        page.goto(path.resolve().as_uri(), wait_until="domcontentloaded")
        return page


class AsyncPlaywrightClient:
    """Async context manager for Chromium scraping sessions."""

    def __init__(self, config: PlaywrightClientConfig) -> None:
        self.config = config
        self._playwright: AsyncPlaywright | None = None
        self._browser: AsyncBrowser | None = None
        self._context: AsyncBrowserContext | None = None

    async def __aenter__(self) -> "AsyncPlaywrightClient":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.config.headless)
        self._context = await self._browser.new_context(user_agent=self.config.user_agent)
        self._context.set_default_timeout(self.config.timeout_ms)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def open_file(self, path: Path) -> AsyncPage:
        """Open a local HTML page and return the Playwright page object."""
        if self._context is None:
            raise RuntimeError("AsyncPlaywrightClient must be used as an async context manager.")
        page = await self._context.new_page()
        await page.goto(path.resolve().as_uri(), wait_until="domcontentloaded")
        return page
