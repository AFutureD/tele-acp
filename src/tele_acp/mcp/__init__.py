from mcp.server.fastmcp import FastMCP


class MCP(FastMCP):
    def __init__(self):
        super().__init__(name="Telegram MCP Server", json_response=True, port=9998)


mcp_server = MCP()


@mcp_server.tool()
def get_self(name: str = "World") -> str:
    """Get Self Information."""

    return f"Hello, {name}!"
