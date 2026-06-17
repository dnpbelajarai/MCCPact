"""Entry point when running as a module: python -m mcp_playwright_scraper"""

import asyncio
from .server import main

if __name__ == "__main__":
    asyncio.run(main())

# Made with Bob
