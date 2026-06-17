"""Core scraping functionality for the MCP Playwright Scraper."""

import asyncio
import logging
import re
import time
from collections import OrderedDict
from contextlib import suppress
from urllib.parse import urljoin

from ..config import (
    CHECKBOX_TOGGLE_WAIT_MS,
    DEFAULT_USER_AGENT,
    FALLBACK_WAIT_MS,
    INITIAL_PAGE_LOAD_WAIT_MS,
    LARGE_EXPANSION_WAIT_MS,
    MAX_EXPANSION_ROUNDS,
    NO_PROGRESS_THRESHOLD,
    SMALL_EXPANSION_THRESHOLD,
    SMALL_EXPANSION_WAIT_MS,
)
from .browser import BrowserManager
from .models import CacheEntry, ScrapeResult

logger = logging.getLogger(__name__)


class Scraper:
    """
    Web scraper with caching, shared browser reuse, and deterministic fallbacks.
    
    Provides two main capabilities:
    1. Scrape URLs and convert HTML to markdown
    2. Extract navigation links with hierarchical structure support
    """

    def __init__(
        self,
        browser_manager: BrowserManager,
        navigation_timeout_ms: int,
        max_content_chars: int,
        cache_ttl_seconds: int,
        max_cache_entries: int,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        """Initialize the scraper.
        
        Args:
            browser_manager: Shared browser instance manager
            navigation_timeout_ms: Timeout for page navigation
            max_content_chars: Maximum content size to process
            cache_ttl_seconds: Cache entry time-to-live
            max_cache_entries: Maximum number of cache entries
            user_agent: User agent string to use
        """
        self.browser_manager = browser_manager
        self.navigation_timeout_ms = navigation_timeout_ms
        self.max_content_chars = max_content_chars
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_cache_entries = max_cache_entries
        self.user_agent = user_agent
        self._cache: "OrderedDict[str, CacheEntry]" = OrderedDict()
        self._pandoc_available: bool | None = None

    def _prune_cache(self) -> None:
        """Remove expired cache entries and enforce capacity limits."""
        now = time.monotonic()
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if now - entry.created_monotonic > self.cache_ttl_seconds
        ]
        for key in expired_keys:
            self._cache.pop(key, None)
        while len(self._cache) > self.max_cache_entries:
            self._cache.popitem(last=False)

    def _get_cached(self, url: str) -> CacheEntry | None:
        """Retrieve a cached scrape result.
        
        Args:
            url: URL to look up
            
        Returns:
            Cached entry if found and not expired, None otherwise
        """
        self._prune_cache()
        entry = self._cache.get(url)
        if entry is None:
            return None
        self._cache.move_to_end(url)
        return entry

    def _set_cached(self, url: str, markdown: str, mime_type: str) -> None:
        """Store a scrape result in cache.
        
        Args:
            url: URL being cached
            markdown: Markdown content
            mime_type: Content MIME type
        """
        self._cache[url] = CacheEntry(
            markdown=markdown,
            mime_type=mime_type,
            created_monotonic=time.monotonic(),
        )
        self._cache.move_to_end(url)
        self._prune_cache()

    async def scrape(self, url: str, verify_ssl: bool = True) -> ScrapeResult:
        """Scrape a URL and convert content to markdown.
        
        Args:
            url: URL to scrape
            verify_ssl: Whether to verify SSL certificates
            
        Returns:
            Scrape result with markdown content
            
        Raises:
            RuntimeError: If scraping fails
        """
        cached = self._get_cached(url)
        if cached is not None:
            logger.info("Cache hit for %s", url)
            return ScrapeResult(
                markdown=cached.markdown,
                mime_type=cached.mime_type,
                final_url=url,
                from_cache=True,
            )

        started = time.monotonic()
        content, mime_type, final_url = await self.scrape_with_playwright(url, verify_ssl=verify_ssl)

        if not content:
            raise RuntimeError(f"Failed to retrieve content from {url}")

        if len(content) > self.max_content_chars:
            logger.warning("Truncating content for %s from %s to %s chars", url, len(content), self.max_content_chars)
            content = content[: self.max_content_chars]

        if (mime_type and mime_type.startswith("text/html")) or (
            mime_type is None and self.looks_like_html(content)
        ):
            markdown = await self.html_to_markdown(content)
            result_mime_type = "text/markdown"
        else:
            markdown = f"```\n{content}\n```"
            result_mime_type = mime_type or "text/plain"

        self._set_cached(url, markdown, result_mime_type)
        logger.info("Scraped %s in %.2fs", url, time.monotonic() - started)
        return ScrapeResult(
            markdown=markdown,
            mime_type=result_mime_type,
            final_url=final_url,
            from_cache=False,
        )

    def looks_like_html(self, content: str) -> bool:
        """Check if content appears to be HTML.
        
        Args:
            content: Content to check
            
        Returns:
            True if content looks like HTML
        """
        html_patterns = [
            r"<!DOCTYPE\s+html",
            r"<html",
            r"<head",
            r"<body",
            r"<div",
            r"<p>",
            r"<a\s+href=",
        ]
        return any(re.search(pattern, content, re.IGNORECASE) for pattern in html_patterns)

    def _sanitize_user_agent(self, user_agent: str) -> str:
        """Sanitize user agent string to prevent header injection.
        
        Args:
            user_agent: User agent string
            
        Returns:
            Sanitized user agent
        """
        return user_agent.replace("\n", "").replace("\r", "")

    def _is_valid_link_href(self, href: str) -> bool:
        """Check if href is a valid link (not anchor, javascript, or mailto).
        
        Args:
            href: Link href attribute
            
        Returns:
            True if valid link
        """
        return bool(href) and not href.startswith(("#", "javascript:", "mailto:"))

    def _make_absolute_url(self, href: str, base_url: str) -> str:
        """Convert relative URL to absolute URL.
        
        Args:
            href: Relative or absolute URL
            base_url: Base URL for resolution
            
        Returns:
            Absolute URL
        """
        if href.startswith("/"):
            return f"https://www.ibm.com{href}" if "ibm.com" in base_url else urljoin(base_url, href)
        elif href.startswith("http"):
            return href
        else:
            return urljoin(base_url, href)

    async def scrape_with_playwright(self, url: str, verify_ssl: bool) -> tuple[str | None, str | None, str]:
        """Scrape a URL using Playwright browser automation.
        
        Args:
            url: URL to scrape
            verify_ssl: Whether to verify SSL certificates
            
        Returns:
            Tuple of (content, mime_type, final_url)
            
        Raises:
            RuntimeError: If scraping fails
        """
        browser = await self.browser_manager.get_browser()
        context = None
        page = None
        final_url = url

        try:
            context = await browser.new_context(ignore_https_errors=not verify_ssl)
            page = await context.new_page()

            browser_user_agent = await page.evaluate("navigator.userAgent")
            browser_user_agent = browser_user_agent.replace("Headless", "").replace("headless", "")
            safe_user_agent = self._sanitize_user_agent(self.user_agent)
            await page.set_extra_http_headers({"User-Agent": f"{browser_user_agent} {safe_user_agent}"})

            try:
                response = await page.goto(url, wait_until="networkidle", timeout=self.navigation_timeout_ms)
            except Exception as e:
                error_msg = str(e)
                # Check for HTTP/2 protocol errors
                if "ERR_HTTP2_PROTOCOL_ERROR" in error_msg or "HTTP2" in error_msg:
                    logger.warning("HTTP/2 error for %s: %s, retrying with different strategy", url, e)
                    # Close and recreate page to reset connection
                    await page.close()
                    page = await context.new_page()
                    await page.set_extra_http_headers({"User-Agent": f"{browser_user_agent} {safe_user_agent}"})
                    
                logger.warning("networkidle failed for %s: %s, falling back to domcontentloaded", url, e)
                response = await page.goto(url, wait_until="domcontentloaded", timeout=self.navigation_timeout_ms)
                await page.wait_for_timeout(FALLBACK_WAIT_MS)
            final_url = page.url
            
            # For JavaScript-heavy SPAs (like IBM Cloud API docs), wait for content to load
            # Wait for main content area or specific selectors
            try:
                # Wait for common content selectors with a reasonable timeout
                await page.wait_for_selector('main, article, .content, #content, [role="main"]', timeout=5000)
                logger.info("Main content selector found, waiting for render")
                await page.wait_for_timeout(2000)  # Additional time for JS to populate content
            except Exception as e:
                logger.warning("Content selector not found: %s, proceeding anyway", e)
                # Fallback: just wait a bit more
                await page.wait_for_timeout(3000)
            
            content = await page.content()
            mime_type = None
            if response:
                content_type = await response.header_value("content-type")
                if content_type:
                    mime_type = content_type.split(";")[0].strip()

            await self.browser_manager.mark_used()
            return content, mime_type, final_url
        except Exception as exc:
            logger.exception("Playwright scrape failed for %s", url)
            raise RuntimeError(f"Playwright scrape failed for {url}: {exc}") from exc
        finally:
            if page is not None:
                with suppress(Exception):
                    await page.close()
            if context is not None:
                with suppress(Exception):
                    await context.close()

    async def _expand_ibm_docs_navigation(self, page) -> int:
        """Expand all navigation items in IBM Docs with optimized strategy.
        
        Args:
            page: Playwright page object
            
        Returns:
            Total number of items expanded
        """
        # Try to enable "Show full table of contents"
        try:
            show_full_checkbox = await page.query_selector('input[type="checkbox"]')
            if show_full_checkbox:
                is_checked = await show_full_checkbox.is_checked()
                if not is_checked:
                    await show_full_checkbox.click()
                    await page.wait_for_timeout(CHECKBOX_TOGGLE_WAIT_MS)
                    logger.info("Enabled 'Show full table of contents'")
        except Exception as e:
            logger.debug("Could not toggle checkbox: %s", e)
        
        # Optimized expansion strategy with early termination
        no_progress_count = 0
        total_expanded = 0
        
        for attempt in range(MAX_EXPANSION_ROUNDS):
            logger.info("Expansion attempt %d/%d", attempt + 1, MAX_EXPANSION_ROUNDS)
            
            clicked = await page.evaluate("""
                () => {
                    let count = 0;
                    
                    // Find all elements with aria-expanded="false"
                    const collapsedItems = document.querySelectorAll('[aria-expanded="false"]');
                    collapsedItems.forEach(item => {
                        try {
                            const rect = item.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                item.click();
                                count++;
                            }
                        } catch (e) {
                            console.error('Click failed:', e);
                        }
                    });
                    
                    return count;
                }
            """)
            
            total_expanded += clicked
            logger.info("Expanded %d items in attempt %d (total: %d)", clicked, attempt + 1, total_expanded)
            
            if clicked > 0:
                # Adaptive wait time: shorter for small expansions
                wait_time = SMALL_EXPANSION_WAIT_MS if clicked < SMALL_EXPANSION_THRESHOLD else LARGE_EXPANSION_WAIT_MS
                await page.wait_for_timeout(wait_time)
                no_progress_count = 0
            else:
                no_progress_count += 1
                # Early termination: stop if no progress for threshold consecutive rounds
                if no_progress_count >= NO_PROGRESS_THRESHOLD:
                    logger.info("No progress for %d rounds - stopping expansion", NO_PROGRESS_THRESHOLD)
                    break
        
        logger.info("Navigation expansion complete - expanded %d total items", total_expanded)
        return total_expanded

    async def _extract_ibm_docs_links(self, soup, url: str) -> str:
        """Extract hierarchical navigation links from IBM Docs.
        
        Args:
            soup: BeautifulSoup parsed HTML
            url: Base URL for the page
            
        Returns:
            Formatted markdown string with hierarchical links
        """
        logger.info("IBM Docs detected - extracting hierarchical navigation structure")
        
        # Find all links with ?topic= parameter
        all_links = soup.find_all("a", href=True)
        logger.info("Found %d total links in HTML", len(all_links))
        
        # Build a map of links with their DOM depth
        link_data = []
        
        for link in all_links:
            href = str(link.get("href", ""))
            text = link.get_text(strip=True)
            
            if not self._is_valid_link_href(href):
                continue
            
            # Convert to absolute URL
            absolute_url = self._make_absolute_url(href, url)
            
            # IBM Docs NAVIGATION links have ?topic= parameter
            if "?topic=" in absolute_url and "ibm.com/docs" in absolute_url:
                # Calculate nesting level by counting parent elements
                depth = 0
                parent = link.parent
                while parent and parent.name != "[document]":
                    if parent.name in ["ul", "ol", "li"]:
                        depth += 1
                    parent = parent.parent
                
                link_data.append({
                    "url": absolute_url,
                    "text": text,
                    "depth": depth,
                    "element": link
                })
        
        logger.info("Found %d navigation links with ?topic=", len(link_data))
        
        if not link_data:
            return f"No navigation links found on {url}"
        
        # Remove duplicates while preserving order and hierarchy
        seen_urls = set()
        nav_lines = []
        
        # Calculate min_depth once before the loop
        min_depth = min((d["depth"] for d in link_data), default=0)
        
        for item in link_data:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                # Use depth for indentation (normalize to start from 0)
                normalized_depth = item["depth"] - min_depth
                indent = "  " * normalized_depth
                nav_lines.append(f"{indent}- [{item['text']}]({item['url']})")
        
        result = f"# Hierarchical Navigation Links from {url}\n\n"
        result += f"Total navigation links: {len(nav_lines)}\n\n"
        result += "Indentation shows hierarchy (parent-child relationships):\n\n"
        result += "\n".join(nav_lines)
        return result

    async def _extract_generic_links(self, soup, url: str) -> str:
        """Extract links from a generic webpage.
        
        Args:
            soup: BeautifulSoup parsed HTML
            url: Base URL for the page
            
        Returns:
            Formatted markdown string with links
        """
        all_links = soup.find_all("a", href=True)
        links = []
        seen_urls = set()
        
        for link in all_links:
            href = str(link.get("href", ""))
            text = link.get_text(strip=True)
            
            if not self._is_valid_link_href(href):
                continue
            
            absolute_url = self._make_absolute_url(href, url)
            
            if absolute_url not in seen_urls:
                seen_urls.add(absolute_url)
                links.append(f"- [{text}]({absolute_url})")
        
        if not links:
            return f"No links found on {url}"
        
        result = f"# Links extracted from {url}\n\n"
        result += f"Total links found: {len(links)}\n\n"
        result += "\n".join(links)
        return result

    async def extract_links(self, url: str) -> str:
        """Extract navigation links from a webpage by parsing HTML content.
        
        For IBM Docs, extracts sidebar navigation links with hierarchical structure.
        For other sites, extracts all links in a flat list.
        
        Args:
            url: The URL to extract links from
            
        Returns:
            Formatted markdown string with extracted links
            
        Raises:
            RuntimeError: If link extraction fails
        """
        browser = await self.browser_manager.get_browser()
        context = None
        page = None

        try:
            context = await browser.new_context()
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="networkidle", timeout=self.navigation_timeout_ms)
            except Exception as e:
                logger.info("networkidle timeout for %s: %s, falling back to domcontentloaded", url, e)
                await page.goto(url, wait_until="domcontentloaded", timeout=self.navigation_timeout_ms)
            
            await page.wait_for_timeout(INITIAL_PAGE_LOAD_WAIT_MS)
            
            is_ibm_docs = "ibm.com/docs" in url
            
            # For IBM Docs, expand ALL navigation items first
            if is_ibm_docs:
                logger.info("IBM Docs detected - expanding navigation items with optimized strategy")
                await self._expand_ibm_docs_navigation(page)
            
            # Get the HTML content after expansion
            html_content = await page.content()
            
            try:
                from bs4 import BeautifulSoup
            except ImportError:
                logger.error("BeautifulSoup not available")
                return "Error: BeautifulSoup required for link extraction"
            
            # Parse HTML asynchronously to avoid blocking event loop
            soup = await asyncio.to_thread(BeautifulSoup, html_content, "html.parser")
            
            # Extract links based on site type
            if is_ibm_docs:
                result = await self._extract_ibm_docs_links(soup, url)
            else:
                result = await self._extract_generic_links(soup, url)
            
            await self.browser_manager.mark_used()
            return result

        except Exception as exc:
            logger.exception("Link extraction failed for %s", url)
            raise RuntimeError(f"Link extraction failed for {url}: {exc}") from exc
        finally:
            if page is not None:
                with suppress(Exception):
                    await page.close()
            if context is not None:
                with suppress(Exception):
                    await context.close()

    async def try_pandoc(self) -> bool:
        """Check if pandoc is available for HTML to markdown conversion.
        
        Returns:
            True if pandoc is available, False otherwise
        """
        if self._pandoc_available is not None:
            return self._pandoc_available

        try:
            import pypandoc

            try:
                pypandoc.get_pandoc_version()
                self._pandoc_available = True
                return True
            except OSError:
                logger.info("Pandoc binary not available; using BeautifulSoup fallback")
                self._pandoc_available = False
                return False
        except ImportError:
            logger.info("pypandoc not installed; using BeautifulSoup fallback")
            self._pandoc_available = False
            return False

    async def html_to_markdown(self, page_source: str) -> str:
        """Convert HTML to markdown format.
        
        Args:
            page_source: HTML source code
            
        Returns:
            Markdown formatted text
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return f"# Scraped Content\n\n{page_source}"

        soup = BeautifulSoup(page_source, "html.parser")
        soup = await asyncio.to_thread(self.slimdown_html, soup)
        cleaned_html = str(soup)

        if not await self.try_pandoc():
            text = soup.get_text(separator="\n\n", strip=True)
            title = soup.title.string.strip() if soup.title and soup.title.string else "Scraped Content"
            return f"# {title}\n\n{text}"

        try:
            import pypandoc

            markdown = await asyncio.to_thread(
                pypandoc.convert_text,
                cleaned_html,
                "markdown",
                format="html",
            )
        except Exception:
            text = soup.get_text(separator="\n\n", strip=True)
            title = soup.title.string.strip() if soup.title and soup.title.string else "Scraped Content"
            return f"# {title}\n\n{text}"

        markdown = re.sub(r"</div>", "      ", markdown)
        markdown = re.sub(r"<div>", "     ", markdown)
        markdown = re.sub(r"\n\s*\n", "\n\n", markdown)
        return markdown.strip()

    def slimdown_html(self, soup):
        """Remove unnecessary HTML elements to reduce content size.
        
        Removes: SVG elements, images, data URIs, and all attributes except href.
        This helps focus on text content and reduces markdown conversion overhead.
        
        Args:
            soup: BeautifulSoup object to clean
            
        Returns:
            Cleaned BeautifulSoup object
        """
        for svg in soup.find_all("svg"):
            svg.decompose()

        for image in soup.find_all("img"):
            image.decompose()

        for tag in soup.find_all(href=lambda x: x and x.startswith("data:")):
            tag.decompose()

        for tag in soup.find_all(src=lambda x: x and x.startswith("data:")):
            tag.decompose()

        for tag in soup.find_all(True):
            for attr in list(tag.attrs):
                if attr != "href":
                    tag.attrs.pop(attr, None)

        return soup

# Made with Bob
