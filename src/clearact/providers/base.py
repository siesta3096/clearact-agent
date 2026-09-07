from typing import Protocol

from clearact.domain.models import ChatMessage, LLMResponse, ToolDefinition


class LLMProvider(Protocol):
    async def chat(self, messages: list[ChatMessage], tools: list[ToolDefinition]) -> LLMResponse: ...
