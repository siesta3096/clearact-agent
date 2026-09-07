import asyncio
import sys
from pathlib import Path

from clearact.tools.mcp import MCPManager, mcp_tool_name


def test_mcp_manager_discovers_and_calls_stdio_tool():
    script = Path(__file__).parents[1] / "fixtures" / "mcp_echo_server.py"

    async def exercise() -> None:
        manager = MCPManager({"echo server": {"command": sys.executable, "args": [str(script)]}})
        await manager.connect()
        try:
            local_name = mcp_tool_name("echo server", "echo")
            assert local_name in {definition.name for definition in manager.definitions()}
            result = await manager.call(local_name, {"value": "ClearAct"})
            assert result.ok is True
            assert result.content == "ClearAct"
            assert result.metadata["server"] == "echo server"
        finally:
            await manager.close()

    asyncio.run(exercise())
