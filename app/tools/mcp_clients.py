from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


class MCPManager:
    """
    Singleton manager for MCP servers used in the application.

    Currently configured servers:
    - web-search -> mrkrsl/web-search-mcp via stdio
    """

    _instance: "MCPManager" | None = None
    _lock = asyncio.Lock()

    def __new__(cls) -> "MCPManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)

            cls._instance.servers_config = {}
            cls._instance.client = None
            cls._instance._initialized = False

        return cls._instance

    async def initialize(self) -> None:
        """
        Build configuration for all enabled MCP servers.
        """

        async with self._lock:
            if self._initialized:
                return

            logger.info("Initializing MCPManager...")

            self._configure_web_search()

            if not self.servers_config:
                logger.warning("No MCP servers configured.")

            self.client = MultiServerMCPClient(
                self.servers_config,
                handle_tool_errors=True,
            )

            self._initialized = True

            logger.info(
                "MCPManager initialized with servers: %s",
                list(self.servers_config.keys()),
            )

    def _configure_web_search(self) -> None:
        """
        Configure mrkrsl/web-search-mcp using stdio transport.
        """

        transport = os.getenv(
            "MCP_WEB_SEARCH_TRANSPORT",
            "stdio",
        ).lower()

        if transport != "stdio":
            logger.warning(
                "Unsupported MCP_WEB_SEARCH_TRANSPORT=%s. "
                "web-search-mcp currently expected to run via stdio.",
                transport,
            )
            return

        script_path_raw = os.getenv("MCP_WEB_SEARCH_SCRIPT")

        if not script_path_raw:
            logger.warning(
                "MCP_WEB_SEARCH_SCRIPT is not configured. "
                "Web Search MCP will be unavailable."
            )
            return

        script_path = Path(script_path_raw).expanduser().resolve()

        if not script_path.is_file():
            logger.warning(
                "Web Search MCP script does not exist: %s",
                script_path,
            )
            return

        node_command = os.getenv(
            "MCP_WEB_SEARCH_COMMAND",
            "node",
        )

        mcp_env = {
            **os.environ,

            "MAX_CONTENT_LENGTH": os.getenv(
                "MCP_WEB_SEARCH_MAX_CONTENT_LENGTH",
                "15000",
            ),

            "DEFAULT_TIMEOUT": os.getenv(
                "MCP_WEB_SEARCH_DEFAULT_TIMEOUT",
                "6000",
            ),

            "MAX_BROWSERS": os.getenv(
                "MCP_WEB_SEARCH_MAX_BROWSERS",
                "2",
            ),

            "BROWSER_HEADLESS": os.getenv(
                "MCP_WEB_SEARCH_BROWSER_HEADLESS",
                "true",
            ),

            "BROWSER_FALLBACK_THRESHOLD": os.getenv(
                "MCP_WEB_SEARCH_BROWSER_FALLBACK_THRESHOLD",
                "3",
            ),

            "ENABLE_RELEVANCE_CHECKING": os.getenv(
                "MCP_WEB_SEARCH_ENABLE_RELEVANCE_CHECKING",
                "true",
            ),

            "RELEVANCE_THRESHOLD": os.getenv(
                "MCP_WEB_SEARCH_RELEVANCE_THRESHOLD",
                "0.3",
            ),

            "FORCE_MULTI_ENGINE_SEARCH": os.getenv(
                "MCP_WEB_SEARCH_FORCE_MULTI_ENGINE_SEARCH",
                "false",
            ),
        }

        self.servers_config["web-search"] = {
            "transport": "stdio",
            "command": node_command,
            "args": [str(script_path)],
            "env": mcp_env,
        }

        logger.info(
            "Web Search MCP configured via stdio: %s %s",
            node_command,
            script_path,
        )

    async def get_tools(
        self,
        server_name: str | None = None,
    ) -> List[BaseTool]:
        """
        Retrieve LangChain tools from MCP.

        If server_name is provided, tools are loaded only
        from that MCP server.
        """

        if not self._initialized:
            await self.initialize()

        if self.client is None:
            return []

        if server_name and server_name not in self.servers_config:
            logger.warning(
                "MCP server '%s' is not configured.",
                server_name,
            )
            return []

        try:
            tools = await self.client.get_tools(
                server_name=server_name,
            )

            logger.info(
                "Loaded %d MCP tools from %s",
                len(tools),
                server_name or "all servers",
            )

            for tool in tools:
                logger.info("MCP tool available: %s", tool.name)

            return tools

        except Exception:
            logger.exception(
                "Failed to retrieve MCP tools from server: %s",
                server_name,
            )

            return []

    async def get_web_search_tools(self) -> List[BaseTool]:
        """
        Convenience method for Web Search MCP.
        """

        return await self.get_tools(
            server_name="web-search"
        )

    async def close_all(self) -> None:
        """
        Reset MCP manager state.

        MultiServerMCPClient creates sessions/subprocesses
        for tool loading/invocation, so there may be no persistent
        client-level process to close depending on adapter version.
        """

        async with self._lock:
            self.client = None
            self.servers_config.clear()
            self._initialized = False

            logger.info("MCPManager reset.")


async def get_mcp_tools(
    server_name: str,
) -> list[BaseTool]:
    manager = MCPManager()

    return await manager.get_tools(
        server_name=server_name
    )


async def get_web_search_tools() -> list[BaseTool]:
    manager = MCPManager()

    return await manager.get_web_search_tools()


async def shutdown_mcp_clients() -> None:
    manager = MCPManager()

    await manager.close_all()