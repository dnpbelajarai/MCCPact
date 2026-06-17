"""Browser lifecycle management for the MCP Playwright Scraper."""

import asyncio
import logging
import time
from contextlib import suppress

logger = logging.getLogger(__name__)


class BrowserManager:
    """
    Manages a shared Playwright browser instance with automatic idle cleanup.
    
    The browser is lazily initialized on first use and automatically closed
    after being idle for the configured TTL period. This reduces resource
    usage while maintaining performance for frequent scraping operations.
    """

    def __init__(self, idle_ttl_seconds: int):
        """Initialize the browser manager.
        
        Args:
            idle_ttl_seconds: Seconds of inactivity before closing the browser
        """
        self.idle_ttl_seconds = idle_ttl_seconds
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._last_used_monotonic = 0.0

    async def get_browser(self):
        """Get the shared browser instance, launching it if necessary.
        
        Returns:
            Playwright browser instance
        """
        async with self._lock:
            await self._close_if_idle_locked()
            if self._browser is None:
                from playwright.async_api import async_playwright

                logger.info("Starting shared Playwright browser (Firefox for better HTTP/2 compatibility)")
                self._playwright = await async_playwright().start()
                # Use Firefox instead of Chromium - better HTTP/2 handling
                self._browser = await self._playwright.firefox.launch(
                    headless=True,
                    firefox_user_prefs={
                        'network.http.http2.enabled': False,  # Disable HTTP/2
                        'network.http.spdy.enabled': False,
                    }
                )
            self._last_used_monotonic = time.monotonic()
            return self._browser

    async def mark_used(self) -> None:
        """Mark the browser as recently used to prevent idle timeout."""
        async with self._lock:
            self._last_used_monotonic = time.monotonic()

    async def _close_if_idle_locked(self) -> None:
        """Close the browser if it has been idle beyond the TTL."""
        if self._browser is None:
            return
        idle_for = time.monotonic() - self._last_used_monotonic
        if idle_for <= self.idle_ttl_seconds:
            return
        logger.info("Closing idle Playwright browser after %.2f seconds", idle_for)
        await self._close_locked()

    async def close(self) -> None:
        """Explicitly close the browser and cleanup resources."""
        async with self._lock:
            await self._close_locked()

    async def _close_locked(self) -> None:
        """Internal method to close browser (must be called with lock held)."""
        if self._browser is not None:
            with suppress(Exception):
                await self._browser.close()
        if self._playwright is not None:
            with suppress(Exception):
                await self._playwright.stop()
        self._browser = None
        self._playwright = None
        self._last_used_monotonic = 0.0

# Made with Bob
