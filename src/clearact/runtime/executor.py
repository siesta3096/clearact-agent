import asyncio

from clearact.domain.models import Action, ToolResult
from clearact.tools.base import ToolContext
from clearact.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, timeout_seconds: float) -> None:
        self._registry = registry
        self._timeout_seconds = timeout_seconds

    async def execute(self, action: Action, context: ToolContext) -> ToolResult:
        tool = self._registry.get(action.tool_name)
        return await asyncio.wait_for(tool.execute(action.arguments, context, action.id), timeout=self._timeout_seconds)
