# Bob MCP Configuration Fix

## Problem
Bob is trying to run `server.py` directly, which causes a relative import error:
```
ImportError: attempted relative import with no known parent package
```

## Solution

You need to update your Bob MCP settings to use one of these methods:

### Option 1: Use the standalone run_server.py (RECOMMENDED)

Update your Bob MCP settings to use the new `run_server.py` script:

```json
{
  "mcpServers": {
    "mcp-playwright-scraper": {
      "command": "python",
      "args": [
        "C:/Users/ArfanRusdi/Documents/CLIENT ENGINEERING/Automation/WebScraping/mcp-playwright-scraper-copy/run_server.py"
      ]
    }
  }
}
```

### Option 2: Run as a Python module

```json
{
  "mcpServers": {
    "mcp-playwright-scraper": {
      "command": "python",
      "args": [
        "-m",
        "mcp_playwright_scraper"
      ],
      "cwd": "C:/Users/ArfanRusdi/Documents/CLIENT ENGINEERING/Automation/WebScraping/mcp-playwright-scraper-copy"
    }
  }
}
```

### Option 3: Use python -m with full path

```json
{
  "mcpServers": {
    "mcp-playwright-scraper": {
      "command": "python",
      "args": [
        "-m",
        "mcp_playwright_scraper.server"
      ],
      "cwd": "C:/Users/ArfanRusdi/Documents/CLIENT ENGINEERING/Automation/WebScraping/mcp-playwright-scraper-copy"
    }
  }
}
```

## How to Update Bob MCP Settings

1. **Open Bob Settings:**
   - Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
   - Type "Bob: Open MCP Settings"
   - Or manually edit the file at: `%APPDATA%\Bob-Code\User\globalStorage\bob-code.bob\mcp_settings.json`

2. **Find your mcp-playwright-scraper configuration**

3. **Update the command and args** using one of the options above

4. **Restart Bob** or reload the MCP servers

## Files Created

1. **`run_server.py`** - Standalone script that can be run directly without import issues
2. **`__main__.py`** - Allows running as `python -m mcp_playwright_scraper`

## Testing

After updating the configuration, test it by:

1. Restarting Bob or reloading MCP servers
2. Try using the scraper tool
3. Check Bob's output panel for any errors

## What Was Fixed

In addition to the configuration fix, the following HTTP/2 issues were also resolved:

1. **Browser launch arguments** - Added `--disable-http2` and other flags
2. **HTTP/2 error detection** - Added retry logic for HTTP/2 protocol errors
3. **Connection reset** - Recreates page on HTTP/2 errors

See [`HTTP2_ERROR_FIX.md`](HTTP2_ERROR_FIX.md) for details on the HTTP/2 fixes.

---

*Configuration fix created: 2026-06-09*