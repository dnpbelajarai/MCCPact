"""Data models for the MCP Playwright Scraper."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ResourceEntry:
    """Represents a scraped resource stored in memory."""
    uri: str
    url: str
    content: str
    mime_type: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class CacheEntry:
    """Represents a cached scrape result."""
    markdown: str
    mime_type: str
    created_monotonic: float


@dataclass(slots=True)
class ScrapeResult:
    """Result of a scraping operation."""
    markdown: str
    mime_type: str
    final_url: str
    from_cache: bool

# Made with Bob
