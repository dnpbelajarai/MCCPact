# MCP Playwright Scraper - Architecture Guide

## Overview

The MCP Playwright Scraper is a **Model Context Protocol (MCP) server** that provides web scraping capabilities to AI assistants like Claude. It allows AI to scrape websites, extract content, and analyze navigation structures through a standardized protocol.

## What is MCP?

**Model Context Protocol (MCP)** is a standard protocol that allows AI models to interact with external tools and data sources. Think of it as a bridge between AI assistants and external services.

- **MCP Server**: Provides tools/capabilities (like our scraper)
- **MCP Client**: AI assistant (like Claude) that uses these tools
- **Communication**: Happens via stdio (standard input/output)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        AI Assistant                          │
│                      (MCP Client)                            │
└────────────────────┬────────────────────────────────────────┘
                     │ MCP Protocol (stdio)
                     │
┌────────────────────▼────────────────────────────────────────┐
│                    server.py                                 │
│              (Main Entry Point)                              │
│  • Initializes all components                                │
│  • Registers MCP handlers                                    │
│  • Manages server lifecycle                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
┌───────▼──────┐ ┌──▼──────┐ ┌──▼──────────┐
│   handlers/  │ │  core/  │ │  security/  │
│              │ │         │ │             │
│ MCP Protocol │ │ Scraper │ │ Validator   │
│   Handlers   │ │ Browser │ │             │
└──────┬───────┘ └──┬──────┘ └─────────────┘
       │            │
       │      ┌─────▼──────┐
       │      │  storage/  │
       │      │            │
       └──────► Resources  │
              └────────────┘
```

---

## Module Breakdown

### 1. **config/** - Configuration & Constants

**Purpose**: Centralized configuration for the entire application

**Files**:
- `settings.py` - All configuration constants

**What it does**:
- Defines server metadata (name, version)
- Sets timeout values for browser operations
- Configures cache sizes and TTLs
- Defines navigation expansion parameters
- Reads environment variables for customization

**Key Constants**:
```python
SERVER_NAME = "mcp-playwright-scraper"
DEFAULT_NAVIGATION_TIMEOUT_MS = 30000  # 30 seconds
MAX_EXPANSION_ROUNDS = 10  # For IBM Docs navigation
```

**Why separate?**: Makes it easy to adjust behavior without touching code logic.

---

### 2. **core/** - Core Business Logic

The heart of the scraper functionality.

#### **core/models.py** - Data Structures

**Purpose**: Defines data classes used throughout the application

**Classes**:
1. **ResourceEntry**: Represents a scraped webpage stored in memory
   ```python
   @dataclass
   class ResourceEntry:
       uri: str          # Unique identifier (scrape://uuid)
       url: str          # Original URL
       content: str      # Scraped markdown content
       mime_type: str    # Content type
       created_at: datetime
       updated_at: datetime
   ```

2. **CacheEntry**: Cached scrape result for performance
   ```python
   @dataclass
   class CacheEntry:
       markdown: str           # Converted content
       mime_type: str         # Content type
       created_monotonic: float  # Timestamp for expiration
   ```

3. **ScrapeResult**: Result of a scraping operation
   ```python
   @dataclass
   class ScrapeResult:
       markdown: str      # Final markdown content
       mime_type: str    # Content type
       final_url: str    # URL after redirects
       from_cache: bool  # Whether result came from cache
   ```

**Why separate?**: Clean data definitions, easy to understand and modify.

---

#### **core/browser.py** - Browser Lifecycle Management

**Purpose**: Manages a shared Playwright browser instance

**Key Class**: `BrowserManager`

**What it does**:
1. **Lazy Initialization**: Browser starts only when first needed
2. **Shared Instance**: Reuses same browser for multiple scrapes (performance)
3. **Automatic Cleanup**: Closes browser after idle timeout
4. **Thread Safety**: Uses asyncio locks to prevent race conditions

**Key Methods**:
```python
async def get_browser()  # Get or create browser
async def mark_used()    # Reset idle timer
async def close()        # Explicit cleanup
```

**Flow**:
```
Request 1 → get_browser() → Launch Chromium → Use browser
Request 2 → get_browser() → Reuse existing → Use browser
[5 min idle] → Auto-close browser
Request 3 → get_browser() → Launch new browser → Use browser
```

**Why separate?**: Browser management is complex and reusable.

---

#### **core/scraper.py** - Web Scraping Engine

**Purpose**: The main scraping logic - converts web pages to markdown

**Key Class**: `Scraper`

**What it does**:

1. **Scrape URLs** (`scrape()` method):
   - Checks cache first (performance)
   - Uses Playwright to load page
   - Handles SSL verification
   - Converts HTML to markdown
   - Stores result in cache

2. **Extract Links** (`extract_links()` method):
   - Navigates to page
   - Expands navigation (for IBM Docs)
   - Extracts all links
   - Returns hierarchical structure

3. **IBM Docs Special Handling**:
   - Detects IBM Docs sites
   - Clicks "Show full table of contents"
   - Expands all collapsed navigation items
   - Extracts links with `?topic=` parameter
   - Preserves hierarchy (indentation)

**Key Methods**:
```python
async def scrape(url, verify_ssl)           # Main scraping
async def extract_links(url)                # Link extraction
async def _expand_ibm_docs_navigation(page) # IBM Docs expansion
async def html_to_markdown(html)            # HTML conversion
```

**Scraping Flow**:
```
1. Check cache → Hit? Return cached
2. Launch browser page
3. Navigate to URL (with fallbacks)
4. Get HTML content
5. Convert to markdown (pandoc or BeautifulSoup)
6. Cache result
7. Return markdown
```

**Link Extraction Flow**:
```
1. Navigate to page
2. Is IBM Docs? → Yes: Expand all navigation
3. Parse HTML with BeautifulSoup
4. Extract links (with hierarchy for IBM Docs)
5. Return formatted markdown
```

**Why separate?**: Core scraping logic is complex and self-contained.

---

### 3. **security/** - Security & Validation

#### **security/validator.py** - URL Safety Validator

**Purpose**: Prevents Server-Side Request Forgery (SSRF) attacks

**Key Class**: `UrlSafetyValidator`

**What it does**:
1. **Validates URL format**: Ensures http/https only
2. **Blocks localhost**: Prevents access to 127.0.0.1, ::1
3. **Blocks private networks**: Prevents access to 10.0.0.0/8, 192.168.0.0/16, etc.
4. **DNS resolution check**: Verifies hostname resolves to public IP

**Validation Flow**:
```
URL Input → Add https:// if missing
         → Parse URL
         → Check scheme (http/https only)
         → Check host (not localhost)
         → Resolve DNS
         → Check IP (not private/reserved)
         → Return safe URL
```

**Why separate?**: Security is critical and should be isolated for auditing.

---

### 4. **storage/** - Resource Management

#### **storage/resources.py** - Resource Manager

**Purpose**: Manages scraped content as MCP resources

**Key Class**: `ResourceManager`

**What it does**:
1. **Stores scraped pages**: Each gets unique URI (scrape://uuid)
2. **TTL Management**: Auto-expires old resources
3. **Capacity Management**: Evicts oldest when limit reached
4. **Subscription Support**: Tracks which clients are interested in resources

**Key Methods**:
```python
def add_resource(url, content, mime_type)  # Store new resource
def get_resource(uri)                      # Retrieve resource
def list_resources()                       # List all resources
def subscribe(uri, session_id)             # Subscribe to updates
```

**Resource Lifecycle**:
```
Scrape → add_resource() → Generate URI (scrape://abc-123)
                       → Store in OrderedDict
                       → Check capacity
                       → Evict old if needed
                       → Return URI to client

Later → get_resource(uri) → Check expiration
                          → Return content or None
```

**Why separate?**: Resource management is a distinct concern from scraping.

---

### 5. **handlers/** - MCP Protocol Handlers

#### **handlers/mcp_handlers.py** - MCP Protocol Implementation

**Purpose**: Implements the MCP protocol - bridges AI requests to scraper functionality

**Key Class**: `MCPHandlers`

**What it does**:
1. **Handles MCP requests**: Translates MCP calls to scraper operations
2. **Input validation**: Validates all parameters
3. **Error handling**: Returns structured errors with codes
4. **Resource management**: Stores results as MCP resources

**MCP Protocol Methods**:

1. **`handle_list_resources()`**: Lists all scraped pages
   ```
   AI: "What resources do you have?"
   → Returns list of scraped pages with URIs
   ```

2. **`handle_read_resource(uri)`**: Reads a specific resource
   ```
   AI: "Show me scrape://abc-123"
   → Returns the markdown content
   ```

3. **`handle_list_tools()`**: Lists available tools
   ```
   AI: "What can you do?"
   → Returns: scrape_to_markdown, map_site_links
   ```

4. **`handle_call_tool(name, args)`**: Executes a tool
   ```
   AI: "Scrape https://example.com"
   → Validates URL
   → Calls scraper.scrape()
   → Stores as resource
   → Returns markdown
   ```

**Tool Handlers**:

1. **`_handle_scrape_to_markdown()`**:
   - Validates URL parameter
   - Validates verify_ssl parameter
   - Calls URL validator
   - Calls scraper
   - Stores result as resource
   - Returns markdown content

2. **`_handle_map_site_links()`**:
   - Validates URL parameter
   - Calls URL validator
   - Calls scraper.extract_links()
   - Returns link structure

**Error Codes**:
- `MISSING_PARAMETER`: Required parameter not provided
- `INVALID_PARAMETER`: Parameter has wrong type/format
- `VALIDATION_ERROR`: URL failed security validation
- `SCRAPING_ERROR`: Scraping operation failed
- `EXTRACTION_ERROR`: Link extraction failed
- `INTERNAL_ERROR`: Unexpected error
- `UNKNOWN_TOOL`: Tool name not recognized

**Why separate?**: MCP protocol logic is distinct from scraping logic.

---

### 6. **server.py** - Main Entry Point

**Purpose**: Orchestrates everything - the conductor of the orchestra

**What it does**:

1. **Initialization** (`main()` function):
   ```python
   # Create all components
   resource_manager = ResourceManager(...)
   url_validator = UrlSafetyValidator(...)
   browser_manager = BrowserManager(...)
   scraper = Scraper(...)
   handlers = MCPHandlers(...)
   ```

2. **Register MCP Handlers**:
   ```python
   @server.list_resources()
   async def handle_list_resources():
       return await handlers.handle_list_resources()
   
   @server.call_tool()
   async def handle_call_tool(name, arguments):
       return await handlers.handle_call_tool(name, arguments)
   ```

3. **Run Server**:
   ```python
   async with mcp.server.stdio.stdio_server() as (read, write):
       await server.run(read, write, ...)
   ```

4. **Cleanup on Exit**:
   ```python
   finally:
       await cleanup_resources(resource_manager, browser_manager)
   ```

**Server Lifecycle**:
```
Start → Initialize components
     → Register handlers
     → Start MCP server (stdio)
     → Listen for requests
     → Process requests via handlers
     → [On shutdown]
     → Cleanup resources
     → Close browser
     → Exit
```

**Why separate?**: Clean entry point, easy to understand flow.

---

## Data Flow Examples

### Example 1: Scraping a URL

```
1. AI Request:
   "Scrape https://example.com"

2. MCP Client → server.py:
   call_tool("scrape_to_markdown", {"url": "https://example.com"})

3. server.py → handlers.handle_call_tool():
   Receives request

4. handlers → handlers._handle_scrape_to_markdown():
   Validates parameters

5. handlers → security.UrlSafetyValidator.validate():
   Checks URL is safe

6. handlers → core.Scraper.scrape():
   a. Check cache (miss)
   b. browser_manager.get_browser() → Get/create browser
   c. Navigate to URL
   d. Get HTML content
   e. Convert to markdown
   f. Cache result
   g. Return ScrapeResult

7. handlers → storage.ResourceManager.add_resource():
   Store as resource with URI

8. handlers → MCP Client:
   Return markdown content

9. AI receives markdown and can analyze it
```

### Example 2: Extracting IBM Docs Links

```
1. AI Request:
   "Map links from https://www.ibm.com/docs/en/instana"

2. MCP Client → server.py:
   call_tool("map_site_links", {"url": "https://..."})

3. server.py → handlers.handle_call_tool():
   Routes to _handle_map_site_links()

4. handlers → security.UrlSafetyValidator.validate():
   Validates URL

5. handlers → core.Scraper.extract_links():
   a. Navigate to page
   b. Detect IBM Docs (check URL)
   c. Click "Show full table of contents" checkbox
   d. Expand all collapsed items (10 rounds max)
      - Find [aria-expanded="false"]
      - Click each visible item
      - Wait for expansion
      - Repeat until no more items
   e. Get final HTML
   f. Parse with BeautifulSoup
   g. Extract links with ?topic=
   h. Calculate hierarchy (count parent ul/ol/li)
   i. Format with indentation
   j. Return markdown

6. handlers → MCP Client:
   Return hierarchical link structure

7. AI receives structured navigation and can analyze it
```

---

## Key Design Patterns

### 1. **Dependency Injection**
Components receive dependencies via constructor:
```python
class Scraper:
    def __init__(self, browser_manager, ...):
        self.browser_manager = browser_manager
```
**Benefit**: Easy to test, swap implementations

### 2. **Single Responsibility Principle**
Each module has one clear purpose:
- `browser.py` → Browser management only
- `security.py` → Security validation only
- `scraper.py` → Scraping logic only

### 3. **Separation of Concerns**
- Configuration separate from logic
- Security separate from functionality
- Storage separate from processing
- Protocol handling separate from business logic

### 4. **Caching Strategy**
Two-level caching:
1. **Scraper cache**: Recent scrapes (5 min TTL)
2. **Resource storage**: Long-term storage (1 hour TTL)

### 5. **Resource Management**
- Browser: Shared instance with idle timeout
- Resources: LRU eviction with TTL
- Cache: Time-based expiration

---

## Configuration

All configuration via environment variables:

```bash
# Logging
MCP_PLAYWRIGHT_SCRAPER_LOG_LEVEL=INFO

# Timeouts
MCP_SCRAPER_TIMEOUT_MS=30000              # Page load timeout
MCP_SCRAPER_BROWSER_IDLE_TTL_SECONDS=300  # Browser idle timeout

# Limits
MCP_SCRAPER_MAX_CONTENT_CHARS=200000      # Max content size
MCP_SCRAPER_MAX_RESOURCES=100             # Max stored resources
MCP_SCRAPER_MAX_CACHE_ENTRIES=100         # Max cache entries

# TTLs
MCP_SCRAPER_RESOURCE_TTL_SECONDS=3600     # Resource expiration
MCP_SCRAPER_CACHE_TTL_SECONDS=300         # Cache expiration

# Security
MCP_SCRAPER_BLOCK_PRIVATE_NETWORKS=true   # Block private IPs
```

---

## Error Handling

Structured error responses with codes:

```python
# Missing parameter
Error [MISSING_PARAMETER]: URL parameter is required

# Invalid parameter
Error [INVALID_PARAMETER]: verify_ssl must be a boolean

# Security validation failed
Error [VALIDATION_ERROR]: Blocked non-public address for host

# Scraping failed
Error [SCRAPING_ERROR]: Playwright scrape failed for URL

# Link extraction failed
Error [EXTRACTION_ERROR]: Link extraction failed for URL

# Unexpected error
Error [INTERNAL_ERROR]: Unexpected error: <details>
```

---

## Performance Optimizations

1. **Browser Reuse**: Single browser instance for all scrapes
2. **Caching**: Avoid re-scraping same URLs
3. **Async Operations**: Non-blocking I/O throughout
4. **Lazy Initialization**: Browser starts only when needed
5. **Efficient Parsing**: BeautifulSoup in thread pool
6. **Smart Expansion**: Early termination for IBM Docs navigation
7. **Adaptive Waits**: Shorter waits for small expansions

---

## Testing Strategy

Each module can be tested independently:

```python
# Test browser manager
browser_manager = BrowserManager(idle_ttl_seconds=60)
browser = await browser_manager.get_browser()
assert browser is not None

# Test URL validator
validator = UrlSafetyValidator()
safe_url = validator.validate("example.com")
assert safe_url == "https://example.com"

# Test scraper (with mock browser)
scraper = Scraper(mock_browser_manager, ...)
result = await scraper.scrape("https://example.com")
assert result.markdown is not None
```

---

## Summary

The MCP Playwright Scraper is a well-architected, modular system that:

1. **Provides web scraping to AI** via MCP protocol
2. **Separates concerns** into logical modules
3. **Handles security** with SSRF protection
4. **Optimizes performance** with caching and browser reuse
5. **Manages resources** with TTL and capacity limits
6. **Handles errors** with structured responses
7. **Supports special cases** like IBM Docs navigation

Each module has a clear purpose, clean interfaces, and can be understood and modified independently. The architecture makes it easy to add new features, fix bugs, and maintain the codebase over time.