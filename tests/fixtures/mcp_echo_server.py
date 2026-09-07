from mcp.server.fastmcp import FastMCP

server = FastMCP("clearact-test-server")


@server.tool()
def echo(value: str) -> str:
    """Return the value unchanged."""
    return value


if __name__ == "__main__":
    server.run(transport="stdio")
