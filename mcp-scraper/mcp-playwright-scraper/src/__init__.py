from . import server as server_module
import asyncio

def main():
    """Main entry point for the package."""
    asyncio.run(server_module.main())

# Optionally expose other important items at package level
server = server_module
__all__ = ["main", "server"]
