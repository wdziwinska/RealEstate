from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class MCPClientError(RuntimeError):
    pass


@dataclass(slots=True)
class MCPBaseClient:
    """Minimal adapter placeholder for future MCP server integrations."""

    endpoint_url: str | None = None
    enabled: bool = False

    def _ensure_enabled(self) -> None:
        if not self.enabled or not self.endpoint_url:
            raise MCPClientError("MCP client is not configured; using local mock provider.")


class MCPWebSearchClient(MCPBaseClient):
    def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        self._ensure_enabled()
        raise NotImplementedError("Wire this method to a real MCP web-search server.")


class MCPGoogleMapsClient(MCPBaseClient):
    def geocode(self, address: str) -> dict[str, Any]:
        self._ensure_enabled()
        raise NotImplementedError("Wire this method to a real MCP Google Maps server.")

    def route(self, origin: tuple[float, float], destination: str, mode: str) -> dict[str, Any]:
        self._ensure_enabled()
        raise NotImplementedError("Wire this method to a real MCP routing server.")


class MCPPDFClient(MCPBaseClient):
    def extract_text(self, path_or_url: str) -> str:
        self._ensure_enabled()
        raise NotImplementedError("Wire this method to a real MCP PDF parser server.")


class MCPDatabaseClient(MCPBaseClient):
    def persist(self, collection: str, payload: dict[str, Any]) -> None:
        self._ensure_enabled()
        raise NotImplementedError("Wire this method to a real MCP database server.")
