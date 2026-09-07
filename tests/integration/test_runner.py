import asyncio
from pathlib import Path

import pytest

from clearact.context.budget import ContextBudget
from clearact.context.builder import ContextBuilder
from clearact.domain.enums import RiskLevel, RunStatus
from clearact.domain.models import Action, LLMResponse, Run, ToolDefinition, ToolResult, UserPolicy
from clearact.runtime.approvals import DenyAllApprovalGate
from clearact.runtime.event_bus import EventBus
from clearact.runtime.executor import ToolExecutor
from clearact.runtime.policy import PolicyEngine
from clearact.runtime.risk import RiskEvaluator
from clearact.runtime.runner import AgentRunner
from clearact.runtime.stage_mapper import StageMapper
from clearact.storage.checkpoint_store import CheckpointStore
from clearact.storage.run_store import RunStore
from clearact.tools.base import ToolContext
from clearact.tools.filesystem import WriteFileTool
from clearact.tools.registry import ToolRegistry


class SearchTool:
    name = "web_search"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(name=self.name, description="search", parameters={"type": "object"})

    async def execute(self, arguments: dict, _context: ToolContext, action_id: str) -> ToolResult:
        return ToolResult(action_id=action_id, tool_name=self.name, ok=True, content="Results for: test")


class ScriptedProvider:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = iter(responses)

    async def chat(self, messages, tools) -> LLMResponse:
        return next(self._responses)


def build_runner(root: Path, provider: ScriptedProvider, *, max_tool_calls: int = 4) -> AgentRunner:
    registry = ToolRegistry()
    registry.register(WriteFileTool())
    return AgentRunner(
        provider=provider,
        registry=registry,
        context_builder=ContextBuilder(ContextBudget(4096, 0.7)),
        risk_evaluator=RiskEvaluator(root, {}),
        policy_engine=PolicyEngine(),
        approval_gate=DenyAllApprovalGate(),
        executor=ToolExecutor(registry, 1),
        event_bus=EventBus(),
        run_store=RunStore(root / "data"),
        checkpoint_store=CheckpointStore(root / "data"),
        tool_context=ToolContext(root),
        stage_mapper=StageMapper({}),
        max_iterations=4,
        max_tool_calls=max_tool_calls,
    )


def test_runner_preserves_assistant_tool_call_and_completes(workspace):
    async def execute():
        action = Action(id="call_123", tool_name="write_file", arguments={"path": "answer.txt", "content": "done"})
        runner = build_runner(
            workspace,
            ScriptedProvider([LLMResponse(tool_calls=[action]), LLMResponse(content="文件已经创建。")]),
        )
        run = Run(goal="create answer", policy=UserPolicy(autonomy_threshold=RiskLevel.GREEN))
        return action, run, await runner.run(run)

    action, run, final = asyncio.run(execute())

    assert final == "文件已经创建。"
    assert run.status is RunStatus.COMPLETED
    assert (workspace / "answer.txt").read_text(encoding="utf-8") == "done"
    assert run.messages[0].tool_calls == [action]
    assert run.messages[1].tool_call_id == "call_123"


def test_runner_executes_every_visible_search_in_one_planning_turn(workspace):
    async def execute():
        searches = [
            Action(id=f"call_{index}", tool_name="web_search", arguments={"query": f"query {index}"})
            for index in range(3)
        ]
        registry = ToolRegistry()
        registry.register(SearchTool())
        runner = AgentRunner(
            provider=ScriptedProvider([LLMResponse(tool_calls=searches), LLMResponse(content="done")]),
            registry=registry,
            context_builder=ContextBuilder(ContextBudget(4096, 0.7)),
            risk_evaluator=RiskEvaluator(workspace, {}),
            policy_engine=PolicyEngine(),
            approval_gate=DenyAllApprovalGate(),
            executor=ToolExecutor(registry, 1),
            event_bus=EventBus(),
            run_store=RunStore(workspace / "data"),
            checkpoint_store=CheckpointStore(workspace / "data"),
            tool_context=ToolContext(workspace),
            stage_mapper=StageMapper({}),
            max_iterations=4,
            max_tool_calls=4,
        )
        run = Run(goal="write a report", policy=UserPolicy(autonomy_threshold=RiskLevel.GREEN))
        return run, await runner.run(run)

    run, final = asyncio.run(execute())
    assert final == "done"
    assistant_plan = next(message for message in run.messages if message.role == "assistant")
    assert [action.tool_name for action in assistant_plan.tool_calls] == ["web_search", "web_search", "web_search"]
    assert sum(message.name == "web_search" for message in run.messages if message.role == "tool") == 3


def test_runner_stops_at_tool_call_limit(workspace):
    async def execute():
        action = Action(tool_name="write_file", arguments={"path": "answer.txt", "content": "done"})
        runner = build_runner(workspace, ScriptedProvider([LLMResponse(tool_calls=[action])]), max_tool_calls=0)
        run = Run(goal="create answer")
        with pytest.raises(RuntimeError, match="tool-call limit"):
            await runner.run(run)
        return run

    run = asyncio.run(execute())

    assert run.status is RunStatus.FAILED
    assert not (workspace / "answer.txt").exists()


def test_tool_filter_keeps_focused_search_available_after_a_source_fetch():
    from clearact.context.tool_filter import ToolFilter

    tools = [
        ToolDefinition(name="web_search", description="search", parameters={}),
        ToolDefinition(name="fetch_url", description="fetch", parameters={}),
        ToolDefinition(name="write_file", description="write", parameters={}),
    ]

    allowed = ToolFilter().select(tools, {"fetch_url"})

    assert [tool.name for tool in allowed] == ["web_search", "fetch_url", "write_file"]
