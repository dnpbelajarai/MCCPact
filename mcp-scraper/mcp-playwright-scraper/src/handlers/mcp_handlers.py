"""MCP protocol handlers for the Playwright Scraper server."""

import logging
from typing import Any

import mcp.types as types
from pydantic import AnyUrl

from ..core import BrowserManager, Scraper
from ..security import UrlSafetyValidator
from ..storage import ResourceManager

logger = logging.getLogger(__name__)


def build_tool_error(
    message: str,
    error_code: str | None = None,
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Build a structured error response for tool execution failures.
    
    Args:
        message: Human-readable error message
        error_code: Optional error code for categorization
        
    Returns:
        List containing error text content
    """
    error_text = f"Error: {message}"
    if error_code:
        error_text = f"Error [{error_code}]: {message}"
    return [types.TextContent(type="text", text=error_text)]


class MCPHandlers:
    """Encapsulates all MCP protocol handlers for the scraper server."""

    def __init__(
        self,
        resource_manager: ResourceManager,
        url_validator: UrlSafetyValidator,
        scraper: Scraper,
    ):
        """Initialize handlers with required dependencies.
        
        Args:
            resource_manager: Resource storage manager
            url_validator: URL security validator
            scraper: Web scraper instance
        """
        self.resource_manager = resource_manager
        self.url_validator = url_validator
        self.scraper = scraper

    async def handle_list_resources(self) -> list[types.Resource]:
        """List all available scraped resources.
        
        Returns:
            List of resource metadata
        """
        resources_list = self.resource_manager.list_resources()
        return [
            types.Resource(
                uri=AnyUrl(resource["uri"]),
                name=resource["name"],
                description=resource["description"],
                mimeType=resource["mimeType"],
            )
            for resource in resources_list
        ]

    async def handle_read_resource(self, uri: AnyUrl) -> str:
        """Read the content of a specific resource.
        
        Args:
            uri: Resource URI to read
            
        Returns:
            Resource content
            
        Raises:
            ValueError: If URI scheme is unsupported or resource not found
        """
        uri_str = str(uri)
        if not uri_str.startswith("scrape://"):
            raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

        resource = self.resource_manager.get_resource(uri_str)
        if resource is None:
            raise ValueError(f"Resource not found: {uri_str}")

        return resource.content

    async def handle_list_prompts(self) -> list[types.Prompt]:
        """List available prompts. Currently no prompts are implemented.
        
        This handler is reserved for future prompt-based interactions.
        
        Returns:
            Empty list (no prompts available)
        """
        return []

    async def handle_get_prompt(
        self, name: str, arguments: dict[str, str] | None
    ) -> types.GetPromptResult:
        """Get a specific prompt. Currently no prompts are implemented.
        
        This handler is reserved for future prompt-based interactions.
        
        Args:
            name: Prompt name
            arguments: Prompt arguments
            
        Raises:
            ValueError: Always, as no prompts are implemented
        """
        raise ValueError(f"Unknown prompt: {name}")

    async def handle_list_tools(self) -> list[types.Tool]:
        """List all available tools.
        
        Returns:
            List of tool definitions
        """
        return [
            types.Tool(
                name="scrape_to_markdown",
                description="Scrape a public HTTP/HTTPS URL and convert the content to markdown",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Public URL to scrape"},
                        "verify_ssl": {
                            "type": "boolean",
                            "description": "Whether to verify SSL certificates (default: true)",
                        },
                    },
                    "required": ["url"],
                },
            ),
            types.Tool(
                name="map_site_links",
                description="Extract navigation links from a webpage. For IBM Docs, extracts sidebar navigation links with ?topic= parameter.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Public URL to extract links from"},
                    },
                    "required": ["url"],
                },
            ),
        ]

    async def handle_call_tool(
        self, name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Handle tool execution requests with comprehensive validation and error handling.
        
        Args:
            name: Tool name to execute
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        if name == "scrape_to_markdown":
            return await self._handle_scrape_to_markdown(arguments)
        elif name == "map_site_links":
            return await self._handle_map_site_links(arguments)
        else:
            return build_tool_error(f"Unknown tool: {name}", "UNKNOWN_TOOL")

    async def _handle_scrape_to_markdown(
        self, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Handle the scrape_to_markdown tool.
        
        Args:
            arguments: Tool arguments
            
        Returns:
            Scraped content as markdown
        """
        # Validate required arguments
        if not arguments or "url" not in arguments:
            return build_tool_error("URL parameter is required", "MISSING_PARAMETER")

        raw_url = str(arguments.get("url", "")).strip()
        if not raw_url:
            return build_tool_error("URL cannot be empty", "INVALID_PARAMETER")
        
        # Validate optional arguments
        verify_ssl = arguments.get("verify_ssl", True)
        if not isinstance(verify_ssl, bool):
            return build_tool_error("verify_ssl must be a boolean", "INVALID_PARAMETER")

        try:
            safe_url = self.url_validator.validate(raw_url)
            result = await self.scraper.scrape(safe_url, verify_ssl=verify_ssl)
            self.resource_manager.add_resource(
                url=result.final_url,
                content=result.markdown,
                mime_type=result.mime_type,
            )
            return [types.TextContent(type="text", text=result.markdown)]
        except ValueError as exc:
            logger.warning("URL validation failed for url=%s: %s", raw_url, exc)
            return build_tool_error(str(exc), "VALIDATION_ERROR")
        except RuntimeError as exc:
            logger.error("Scraping failed for url=%s: %s", raw_url, exc)
            return build_tool_error(str(exc), "SCRAPING_ERROR")
        except Exception as exc:
            logger.exception("Unexpected error during scraping for url=%s", raw_url)
            return build_tool_error(f"Unexpected error: {exc}", "INTERNAL_ERROR")

    async def _handle_map_site_links(
        self, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Handle the map_site_links tool.
        
        Args:
            arguments: Tool arguments
            
        Returns:
            Extracted links as markdown
        """
        # Validate required arguments
        if not arguments or "url" not in arguments:
            return build_tool_error("URL parameter is required", "MISSING_PARAMETER")

        raw_url = str(arguments.get("url", "")).strip()
        if not raw_url:
            return build_tool_error("URL cannot be empty", "INVALID_PARAMETER")

        try:
            safe_url = self.url_validator.validate(raw_url)
            result = await self.scraper.extract_links(safe_url)
            return [types.TextContent(type="text", text=result)]
        except ValueError as exc:
            logger.warning("URL validation failed for url=%s: %s", raw_url, exc)
            return build_tool_error(str(exc), "VALIDATION_ERROR")
        except RuntimeError as exc:
            logger.error("Link extraction failed for url=%s: %s", raw_url, exc)
            return build_tool_error(str(exc), "EXTRACTION_ERROR")
        except Exception as exc:
            logger.exception("Unexpected error during link extraction for url=%s", raw_url)
            return build_tool_error(f"Unexpected error: {exc}", "INTERNAL_ERROR")

# Made with Bob
