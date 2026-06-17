"""
MCP Playwright Scraper Server

A Model Context Protocol (MCP) server that provides web scraping capabilities using Playwright.

Features:
- Scrape public URLs and convert content to markdown
- Extract navigation links from webpages with hierarchical structure support
- Special handling for IBM Docs navigation with automatic expansion
- Built-in caching and resource management
- SSRF protection and security validation
- Shared browser instance for performance

Tools:
- scrape_to_markdown: Scrape a URL and convert HTML to markdown
- map_site_links: Extract all navigation links from a webpage

Configuration (via environment variables):
- MCP_PLAYWRIGHT_SCRAPER_LOG_LEVEL: Logging level (default: INFO)
- MCP_SCRAPER_TIMEOUT_MS: Navigation timeout in milliseconds (default: 30000)
- MCP_SCRAPER_MAX_CONTENT_CHARS: Maximum content size (default: 200000)
- MCP_SCRAPER_RESOURCE_TTL_SECONDS: Resource cache TTL (default: 3600)
- MCP_SCRAPER_MAX_RESOURCES: Maximum cached resources (default: 100)
- MCP_SCRAPER_CACHE_TTL_SECONDS: Scrape cache TTL (default: 300)
- MCP_SCRAPER_MAX_CACHE_ENTRIES: Maximum cache entries (default: 100)
- MCP_SCRAPER_BROWSER_IDLE_TTL_SECONDS: Browser idle timeout (default: 300)
- MCP_SCRAPER_BLOCK_PRIVATE_NETWORKS: Block private IPs (default: true)
"""

import asyncio
import logging

import mcp.server.stdio
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from .config import (
    DEFAULT_BLOCK_PRIVATE_NETWORKS,
    DEFAULT_BROWSER_IDLE_TTL_SECONDS,
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_MAX_CACHE_ENTRIES,
    DEFAULT_MAX_CONTENT_CHARS,
    DEFAULT_MAX_RESOURCES,
    DEFAULT_NAVIGATION_TIMEOUT_MS,
    DEFAULT_RESOURCE_TTL_SECONDS,
    LOG_FORMAT,
    LOG_LEVEL,
    SERVER_NAME,
    SERVER_VERSION,
)
from .core import BrowserManager, Scraper
from .handlers import MCPHandlers
from .security import UrlSafetyValidator
from .storage import ResourceManager

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)

# Initialize MCP server
server = Server(SERVER_NAME)


async def cleanup_resources(
    resource_manager: ResourceManager,
    browser_manager: BrowserManager,
) -> None:
    """Clean up all resources before server shutdown.
    
    Args:
        resource_manager: Resource manager to cleanup
        browser_manager: Browser manager to cleanup
    """
    resource_manager.cleanup()
    await browser_manager.close()


async def main() -> None:
    """Initialize and run the MCP server with proper resource management."""
    # Initialize all components
    resource_manager = ResourceManager(
        ttl_seconds=DEFAULT_RESOURCE_TTL_SECONDS,
        max_resources=DEFAULT_MAX_RESOURCES,
    )
    url_validator = UrlSafetyValidator(block_private_networks=DEFAULT_BLOCK_PRIVATE_NETWORKS)
    browser_manager = BrowserManager(idle_ttl_seconds=DEFAULT_BROWSER_IDLE_TTL_SECONDS)
    scraper = Scraper(
        browser_manager=browser_manager,
        navigation_timeout_ms=DEFAULT_NAVIGATION_TIMEOUT_MS,
        max_content_chars=DEFAULT_MAX_CONTENT_CHARS,
        cache_ttl_seconds=DEFAULT_CACHE_TTL_SECONDS,
        max_cache_entries=DEFAULT_MAX_CACHE_ENTRIES,
    )
    
    # Initialize handlers
    handlers = MCPHandlers(
        resource_manager=resource_manager,
        url_validator=url_validator,
        scraper=scraper,
    )
    
    # Register MCP handlers
    @server.list_resources()
    async def handle_list_resources():
        return await handlers.handle_list_resources()
    
    @server.read_resource()
    async def handle_read_resource(uri):
        return await handlers.handle_read_resource(uri)
    
    @server.list_prompts()
    async def handle_list_prompts():
        return await handlers.handle_list_prompts()
    
    @server.get_prompt()
    async def handle_get_prompt(name, arguments):
        return await handlers.handle_get_prompt(name, arguments)
    
    @server.list_tools()
    async def handle_list_tools():
        return await handlers.handle_list_tools()
    
    @server.call_tool()
    async def handle_call_tool(name, arguments):
        return await handlers.handle_call_tool(name, arguments)
    
    # Start server
    logger.info("%s %s starting", SERVER_NAME, SERVER_VERSION)
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=SERVER_NAME,
                    server_version=SERVER_VERSION,
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    finally:
        await cleanup_resources(resource_manager, browser_manager)
        logger.info("%s stopped", SERVER_NAME)


if __name__ == "__main__":
    asyncio.run(main())

# Made with Bob
