"""Configuration and constants for the MCP Playwright Scraper."""

import os

# Server metadata
SERVER_NAME = "mcp-playwright-scraper"
SERVER_VERSION = "0.2.0"
DEFAULT_USER_AGENT = "Playwright-MCP-Scraper/0.2.0"

# Timeouts and limits
DEFAULT_NAVIGATION_TIMEOUT_MS = int(os.getenv("MCP_SCRAPER_TIMEOUT_MS", "30000"))
DEFAULT_MAX_CONTENT_CHARS = int(os.getenv("MCP_SCRAPER_MAX_CONTENT_CHARS", "200000"))
DEFAULT_RESOURCE_TTL_SECONDS = int(os.getenv("MCP_SCRAPER_RESOURCE_TTL_SECONDS", "3600"))
DEFAULT_MAX_RESOURCES = int(os.getenv("MCP_SCRAPER_MAX_RESOURCES", "100"))
DEFAULT_CACHE_TTL_SECONDS = int(os.getenv("MCP_SCRAPER_CACHE_TTL_SECONDS", "300"))
DEFAULT_MAX_CACHE_ENTRIES = int(os.getenv("MCP_SCRAPER_MAX_CACHE_ENTRIES", "100"))
DEFAULT_BROWSER_IDLE_TTL_SECONDS = int(os.getenv("MCP_SCRAPER_BROWSER_IDLE_TTL_SECONDS", "300"))
DEFAULT_BLOCK_PRIVATE_NETWORKS = os.getenv("MCP_SCRAPER_BLOCK_PRIVATE_NETWORKS", "true").lower() != "false"

# Navigation expansion constants for IBM Docs
MAX_EXPANSION_ROUNDS = 10  # Maximum attempts to expand navigation items
NO_PROGRESS_THRESHOLD = 2  # Stop expansion after N rounds with no progress
SMALL_EXPANSION_WAIT_MS = 800  # Wait time after expanding <10 items
LARGE_EXPANSION_WAIT_MS = 1200  # Wait time after expanding >=10 items
SMALL_EXPANSION_THRESHOLD = 10  # Threshold for determining small vs large expansion

# Page load wait times
INITIAL_PAGE_LOAD_WAIT_MS = 2000  # Allow dynamic content to load after navigation
CHECKBOX_TOGGLE_WAIT_MS = 1000  # Wait for navigation to expand after checkbox toggle
FALLBACK_WAIT_MS = 3000  # Wait time when falling back to domcontentloaded

# Logging
LOG_LEVEL = os.getenv("MCP_PLAYWRIGHT_SCRAPER_LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# Made with Bob
