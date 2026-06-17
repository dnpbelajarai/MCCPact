"""Core functionality module for MCP Playwright Scraper."""

from .browser import BrowserManager
from .models import CacheEntry, ResourceEntry, ScrapeResult
from .scraper import Scraper

__all__ = [
    "BrowserManager",
    "Scraper",
    "ResourceEntry",
    "CacheEntry",
    "ScrapeResult",
]

# Made with Bob
