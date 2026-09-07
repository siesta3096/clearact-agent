from clearact.context.budget import ContextBudget
from clearact.context.builder import ContextBuilder
from clearact.domain.models import ChatMessage, ToolDefinition


def test_context_budget_estimates_messages_and_tools():
    budget = ContextBudget(context_window=100, ratio=0.5)
    messages = [ChatMessage(role="user", content="x" * 200)]
    tools = [ToolDefinition(name="tool", description="description", parameters={"type": "object"})]

    assert budget.limit == 50
    assert budget.estimate(messages, tools) > 0
    assert budget.exceeds(messages, tools) is True


def test_context_builder_compacts_over_budget_history():
    builder = ContextBuilder(ContextBudget(context_window=30, ratio=0.5))
    messages = [ChatMessage(role="user", content=f"message {index}: " + "x" * 40) for index in range(8)]
    tools = [ToolDefinition(name="list_files", description="list files", parameters={})]

    selected_messages, selected_tools = builder.build(messages, tools, set())

    assert len(selected_messages) == 7
    assert selected_messages[0].role == "system"
    assert "Earlier task summary" in selected_messages[0].content
    assert selected_tools == tools
