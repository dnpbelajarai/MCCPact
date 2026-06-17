# mcp-playwright-scraper-copy

Upgraded local copy of the `mcp_playwright_scraper` MCP server.

## Tree

```text
mcp-playwright-scraper-copy/
├── README.md
└── mcp_playwright_scraper/
    ├── __init__.py
    └── server.py
```

## What changed

Compared with the original installed copy, [mcp_playwright_scraper/server.py](mcp_playwright_scraper/server.py:1) now includes:

- shared Playwright browser reuse instead of launching a new browser for every request
- URL validation with SSRF-style blocking for localhost and private/reserved IP targets
- bounded in-memory resource storage with TTL and eviction
- bounded response cache with TTL
- structured logging
- deterministic Markdown fallback when Pandoc is unavailable
- cleanup for browser and resources on shutdown
- removal of unused variables and runtime Pandoc download behavior

## Main components

- [ResourceManager](mcp_playwright_scraper/server.py:57): stores scraped resources with TTL and max-capacity eviction
- [UrlSafetyValidator](mcp_playwright_scraper/server.py:154): validates public HTTP/HTTPS URLs
- [BrowserManager](mcp_playwright_scraper/server.py:201): manages a shared Playwright browser lifecycle
- [Scraper](mcp_playwright_scraper/server.py:248): fetches pages, caches results, and converts HTML to Markdown
- [handle_call_tool()](mcp_playwright_scraper/server.py:584): MCP tool entrypoint for `scrape_to_markdown`
- [main()](mcp_playwright_scraper/server.py:621): starts the MCP stdio server

## Dependencies

Runtime imports used by [mcp_playwright_scraper/server.py](mcp_playwright_scraper/server.py:1):

- `mcp`
- `pydantic`
- `playwright`
- `beautifulsoup4`
- optional: `pypandoc`

## Environment variables

Optional configuration supported by [mcp_playwright_scraper/server.py](mcp_playwright_scraper/server.py:1):

- `MCP_PLAYWRIGHT_SCRAPER_LOG_LEVEL`
- `MCP_SCRAPER_TIMEOUT_MS`
- `MCP_SCRAPER_MAX_CONTENT_CHARS`
- `MCP_SCRAPER_RESOURCE_TTL_SECONDS`
- `MCP_SCRAPER_MAX_RESOURCES`
- `MCP_SCRAPER_CACHE_TTL_SECONDS`
- `MCP_SCRAPER_MAX_CACHE_ENTRIES`
- `MCP_SCRAPER_BROWSER_IDLE_TTL_SECONDS`
- `MCP_SCRAPER_BLOCK_PRIVATE_NETWORKS`

## Run

Use the module entrypoint:

```powershell
python -m mcp_playwright_scraper.server
```

## Notes

- Subscription decorators were removed from the copied version because the MCP type stubs in this environment report a single-argument signature mismatch.
- Resources and cache are still in-memory only; they reset when the process stops.