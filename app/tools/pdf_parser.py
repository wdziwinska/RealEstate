from __future__ import annotations

from pathlib import Path

from app.tools.mcp_clients import MCPClientError, MCPPDFClient


class PDFParser:
    """PDF extraction facade with MCP hook and local pypdf fallback."""

    def __init__(self, mcp_client: MCPPDFClient | None = None) -> None:
        self.mcp_client = mcp_client or MCPPDFClient()

    def extract_text(self, path_or_url: str) -> str:
        try:
            return self.mcp_client.extract_text(path_or_url)
        except (MCPClientError, NotImplementedError):
            return self._extract_local(path_or_url)

    def _extract_local(self, path_or_url: str) -> str:
        if "://" in path_or_url:
            return ""
        path = Path(path_or_url)
        if not path.exists() or path.suffix.lower() != ".pdf":
            return ""
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return ""
