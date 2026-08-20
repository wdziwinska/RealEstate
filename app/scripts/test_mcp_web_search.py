import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


MCP_SCRIPT = (
    r"C:\Tasks\Prywata\AgenticAI\mcps\mcp-servers\web-search-mcp\dist\index.js"
)


async def main():
    server_params = StdioServerParameters(
        command="node",
        args=[MCP_SCRIPT],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("Połączono z MCP.")

            tools = await session.list_tools()

            print("\nDostępne narzędzia:")

            for tool in tools.tools:
                print(f"- {tool.name}")


if __name__ == "__main__":
    asyncio.run(main())