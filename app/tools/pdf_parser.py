from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.tools import BaseTool

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PDFParser:
    """
    PDF extraction facade that prioritizes an MCP tool if available,
    with a local pypdf implementation as a fallback.
    """

    def __init__(self, pdf_tool: BaseTool | None = None) -> None:
        """
        Initializes the parser with an optional PDF processing tool.

        Args:
            pdf_tool: A LangChain BaseTool for PDF parsing, typically from an MCP server.
        """
        self.pdf_tool = pdf_tool
        if self.pdf_tool:
            logger.info(f"PDFParser initialized with MCP tool: {self.pdf_tool.name}")
        else:
            logger.info("PDFParser initialized with local pypdf fallback.")

    def extract_text(self, path_or_url: str) -> str:
        """
        Extracts text from a PDF using the MCP tool or the local fallback.
        """
        if self.pdf_tool:
            try:
                # Assuming the tool expects a dictionary with this key
                tool_input = {"path_or_url": path_or_url}
                logger.info(f"Attempting PDF extraction with tool: {self.pdf_tool.name}")
                result = self.pdf_tool.invoke(tool_input)
                # The actual structure of the result may vary, adjust if needed
                return result.get("text", "") if isinstance(result, dict) else str(result)
            except Exception as e:
                logger.warning(
                    f"MCP PDF tool failed with error: {e}. Falling back to local implementation."
                )
                return self._extract_local(path_or_url)

        return self._extract_local(path_or_url)

    def _extract_local(self, path_or_url: str) -> str:
        """Extracts text from a local PDF file using pypdf."""
        if "://" in path_or_url:
            logger.warning("Local PDF extractor does not support URLs.")
            return ""

        path = Path(path_or_url)
        if not path.exists() or path.suffix.lower() != ".pdf":
            logger.warning(f"Local PDF extractor: file not found or not a PDF at {path}")
            return ""

        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            logger.error(f"Local pypdf failed to parse {path}: {e}")
            return ""
