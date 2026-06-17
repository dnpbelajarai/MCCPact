"""Security and URL validation for the MCP Playwright Scraper."""

import ipaddress
import socket
from pydantic import AnyUrl


class UrlSafetyValidator:
    """
    SSRF protection for scraper input URLs.
    
    Validates URLs to prevent Server-Side Request Forgery attacks by:
    - Ensuring only HTTP/HTTPS schemes
    - Blocking localhost and loopback addresses
    - Optionally blocking private network ranges
    """

    def __init__(self, block_private_networks: bool = True):
        """Initialize the validator.
        
        Args:
            block_private_networks: If True, blocks private IP ranges (RFC 1918)
        """
        self.block_private_networks = block_private_networks

    def validate(self, raw_url: str) -> str:
        """Validate and normalize a URL for safe scraping.
        
        Args:
            raw_url: The URL to validate
            
        Returns:
            Normalized URL string
            
        Raises:
            ValueError: If URL is invalid or blocked
        """
        url = raw_url.strip()
        if not url:
            raise ValueError("URL is required")

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        parsed = AnyUrl(url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise ValueError(f"Unsupported URL scheme: {scheme}")

        host = parsed.host
        if not host:
            raise ValueError("URL host is required")

        lowered_host = host.lower()
        if lowered_host in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Localhost targets are not allowed")

        if self.block_private_networks:
            self._ensure_host_is_public(host)

        return str(parsed)

    def _ensure_host_is_public(self, host: str) -> None:
        """Verify that a hostname resolves only to public IP addresses.
        
        Args:
            host: Hostname to check
            
        Raises:
            ValueError: If host resolves to private/reserved IP
        """
        try:
            infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise ValueError(f"Unable to resolve host: {host}") from exc

        for info in infos:
            ip_text = info[4][0]
            ip_obj = ipaddress.ip_address(ip_text)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_reserved
                or ip_obj.is_unspecified
            ):
                raise ValueError(f"Blocked non-public address for host {host}: {ip_text}")

# Made with Bob
