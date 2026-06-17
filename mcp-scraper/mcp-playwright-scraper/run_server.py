#!/usr/bin/env python3
"""
Standalone entry point for MCP Playwright Scraper.
This script can be run directly without module import issues.
"""

import sys
import os
import asyncio

# Add the parent directory to the path so we can import the package
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Now import and run the server
from mcp_playwright_scraper.server import main

if __name__ == "__main__":
    asyncio.run(main())

# Made with Bob
