from clearact.domain.models import ChatMessage, ToolDefinition


class ContextBudget:
    def __init__(self, context_window: int, ratio: float) -> None:
        self._limit = int(context_window * ratio)

    @property
    def limit(self) -> int:
        return self._limit

    def estimate(self, messages: list[ChatMessage], tools: list[ToolDefinition]) -> int:
        message_chars = sum(len(message.content or "") + 16 for message in messages)
        tool_chars = sum(len(str(tool.parameters)) + len(tool.description) + len(tool.name) for tool in tools)
        return (message_chars + tool_chars + 3) // 4

    def exceeds(self, messages: list[ChatMessage], tools: list[ToolDefinition]) -> bool:
        return self.estimate(messages, tools) > self._limit
