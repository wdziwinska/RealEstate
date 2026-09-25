import asyncio
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    # env = {
    #     **os.environ,
    #     "NODE_NO_WARNINGS": "1",       # tłumi warnings Node
    #     "NO_COLOR": "1",               # brak ANSI escape codes
    #     "LOG_LEVEL": "error",          # wiele serwerów honoruje
    #     "DEBUG": "",                   # wyłącza namespace debug
    # }

    env = {
        **os.environ,
        "PATH": os.environ.get("PATH", ""),
        "NODE_NO_WARNINGS": "1",
        "LOG_LEVEL": "error",
    }

    server_params = StdioServerParameters(
        command="node",
        args=[
            "--no-warnings",                                                  # flaga CLI
            r"C:\Tasks\Prywata\AgenticAI\mcps\mcp-servers\web-search-mcp\dist\index.js",
        ],
        env=env,                                                              # ← kluczowe
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for tool in tools.tools:
                logger.info(f"Found tool: {tool.name}")


if __name__ == "__main__":
    asyncio.run(main())

# import asyncio
#
# from mcp import ClientSession, StdioServerParameters
# from mcp.client.stdio import stdio_client
# import logging
#
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)
#
#
# async def main():
#     server_params = StdioServerParameters(
#         command="node",
#         args=[
#             r"C:\Tasks\Prywata\AgenticAI\mcps\mcp-servers\web-search-mcp\dist\index.js"
#         ],
#     )
#
#     async with stdio_client(server_params) as (read, write):
#         async with ClientSession(read, write) as session:
#             await session.initialize()
#
#             tools = await session.list_tools()
#
#             for tool in tools.tools:
#                 logger.info(f"Found tool: {tool.name}")
#
# if __name__ == "__main__":
#     asyncio.run(main())