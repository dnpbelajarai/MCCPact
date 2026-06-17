"""Resource management for the MCP Playwright Scraper."""

import logging
import uuid
from collections import OrderedDict
from datetime import datetime, timezone

from ..core.models import ResourceEntry

logger = logging.getLogger(__name__)


class ResourceManager:
    """
    In-memory resource store with TTL and bounded size.
    
    Manages scraped content as MCP resources with automatic expiration
    and capacity management. Resources are stored with unique URIs and
    can be subscribed to for updates.
    """

    def __init__(self, ttl_seconds: int, max_resources: int):
        """Initialize the resource manager.
        
        Args:
            ttl_seconds: Time-to-live for resources in seconds
            max_resources: Maximum number of resources to store
        """
        self.ttl_seconds = ttl_seconds
        self.max_resources = max_resources
        self.resources: "OrderedDict[str, ResourceEntry]" = OrderedDict()
        self.subscriptions: dict[str, set[str]] = {}

    def _now(self) -> datetime:
        """Get current UTC datetime."""
        return datetime.now(timezone.utc)

    def _is_expired(self, entry: ResourceEntry) -> bool:
        """Check if a resource entry has expired.
        
        Args:
            entry: Resource entry to check
            
        Returns:
            True if expired, False otherwise
        """
        age = (self._now() - entry.updated_at).total_seconds()
        return age > self.ttl_seconds

    def _prune_expired(self) -> None:
        """Remove expired resources from storage."""
        expired_uris = [uri for uri, entry in self.resources.items() if self._is_expired(entry)]
        for uri in expired_uris:
            self.resources.pop(uri, None)
            self.subscriptions.pop(uri, None)
        if expired_uris:
            logger.info("Pruned %s expired resources", len(expired_uris))

    def _enforce_capacity(self) -> None:
        """Enforce maximum resource capacity by evicting oldest entries."""
        while len(self.resources) > self.max_resources:
            oldest_uri, _ = self.resources.popitem(last=False)
            self.subscriptions.pop(oldest_uri, None)
            logger.info("Evicted oldest resource %s due to capacity limit", oldest_uri)

    def add_resource(self, url: str, content: str, mime_type: str) -> str:
        """Add a new resource to storage.
        
        Args:
            url: Source URL of the resource
            content: Resource content
            mime_type: MIME type of the content
            
        Returns:
            URI of the created resource
        """
        self._prune_expired()
        now = self._now()
        resource_id = str(uuid.uuid4())
        uri = f"scrape://{resource_id}"
        self.resources[uri] = ResourceEntry(
            uri=uri,
            url=url,
            content=content,
            mime_type=mime_type,
            created_at=now,
            updated_at=now,
        )
        self.resources.move_to_end(uri)
        self._enforce_capacity()
        self.notify_list_changed()
        return uri

    def get_resource(self, uri: str) -> ResourceEntry | None:
        """Retrieve a resource by URI.
        
        Args:
            uri: Resource URI
            
        Returns:
            Resource entry if found and not expired, None otherwise
        """
        self._prune_expired()
        entry = self.resources.get(uri)
        if entry is None:
            return None
        self.resources.move_to_end(uri)
        return entry

    def list_resources(self) -> list[dict[str, str]]:
        """List all non-expired resources.
        
        Returns:
            List of resource metadata dictionaries
        """
        self._prune_expired()
        return [
            {
                "uri": uri,
                "name": f"Scraped: {entry.url}",
                "description": f"Web page scraped on {entry.updated_at.isoformat()}",
                "mimeType": entry.mime_type,
            }
            for uri, entry in self.resources.items()
        ]

    def subscribe(self, uri: str, session_id: str) -> bool:
        """Subscribe to resource updates.
        
        Args:
            uri: Resource URI
            session_id: Session identifier
            
        Returns:
            True if subscription successful, False if resource not found
        """
        self._prune_expired()
        if uri not in self.resources:
            return False
        self.subscriptions.setdefault(uri, set()).add(session_id)
        return True

    def unsubscribe(self, uri: str, session_id: str) -> bool:
        """Unsubscribe from resource updates.
        
        Args:
            uri: Resource URI
            session_id: Session identifier
            
        Returns:
            True if unsubscription successful, False if not subscribed
        """
        subscribers = self.subscriptions.get(uri)
        if not subscribers:
            return False
        subscribers.discard(session_id)
        if not subscribers:
            self.subscriptions.pop(uri, None)
        return True

    def update_resource(self, uri: str, content: str, mime_type: str) -> bool:
        """Update an existing resource.
        
        Args:
            uri: Resource URI
            content: New content
            mime_type: New MIME type
            
        Returns:
            True if update successful, False if resource not found
        """
        self._prune_expired()
        entry = self.resources.get(uri)
        if entry is None:
            return False
        entry.content = content
        entry.mime_type = mime_type
        entry.updated_at = self._now()
        self.resources.move_to_end(uri)
        self.notify_resource_updated(uri)
        return True

    def notify_list_changed(self) -> None:
        """Notify that the resource list has changed."""
        logger.debug("Resource list changed; subscriptions=%s", len(self.subscriptions))

    def notify_resource_updated(self, uri: str) -> None:
        """Notify that a specific resource has been updated.
        
        Args:
            uri: URI of the updated resource
        """
        logger.debug("Resource updated: %s", uri)

    def cleanup(self) -> None:
        """Clean up all resources and subscriptions."""
        self.resources.clear()
        self.subscriptions.clear()

# Made with Bob
