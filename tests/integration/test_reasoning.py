import asyncio

import httpx

from clearact.context.budget import ContextBudget
from clearact.context.builder import ContextBuilder
from clearact.domain.enums import RiskLevel, RunStatus
from clearact.domain.models import ChatMessage, LLMResponse, Run, ToolDefinition, ToolResult, UserPolicy
from clearact.providers.openai_compatible import OpenAICompatibleProvider
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
from clearact.tools.registry import ToolRegistry


class ScriptedProvider:
    def __init__(self, response):
        self.response = response

    async def chat(self, messages, tools):
        return self.response


class SearchTool:
    name = "web_search"

    def definition(self):
        return ToolDefinition(name=self.name, description="search", parameters={})

    async def execute(self, arguments, context, action_id):
        return ToolResult(action_id=action_id, tool_name=self.name, ok=True, content="result")


def test_openai_provider_extracts_and_returns_reasoning_content(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, *, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json, headers):
            captured["payload"] = json
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "choices": [{"message": {"content": "answer", "reasoning_content": "returned thinking"}}],
                    "usage": {},
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    response = asyncio.run(
        OpenAICompatibleProvider("m", "https://example.test", "k").chat(
            [ChatMessage(role="assistant", content="previous", reasoning_content="prior returned reasoning")], []
        )
    )

    assert response.reasoning_content == "returned thinking"
    assert captured["payload"]["messages"][0]["reasoning_content"] == "prior returned reasoning"


def test_runner_persists_reasoning_and_emits_a_stage_event(workspace):
    async def execute():
        registry = ToolRegistry()
        registry.register(SearchTool())
        store = RunStore(workspace / "data")
        bus = EventBus()
        bus.subscribe_sync(store.append_event)
        runner = AgentRunner(
            provider=ScriptedProvider(LLMResponse(content="final", reasoning_content="provider-visible reasoning")),
            registry=registry,
            context_builder=ContextBuilder(ContextBudget(4096, 0.7)),
            risk_evaluator=RiskEvaluator(workspace, {}),
            policy_engine=PolicyEngine(),
            approval_gate=DenyAllApprovalGate(),
            executor=ToolExecutor(registry, 1),
            event_bus=bus,
            run_store=store,
            checkpoint_store=CheckpointStore(workspace / "data"),
            tool_context=ToolContext(workspace),
            stage_mapper=StageMapper({}),
            max_iterations=2,
            max_tool_calls=2,
        )
        run = Run(goal="test", policy=UserPolicy(autonomy_threshold=RiskLevel.GREEN))
        await runner.run(run)
        return run, store

    run, store = asyncio.run(execute())
    saved = store.load_run(run.id)
    assert run.status is RunStatus.COMPLETED
    assert saved.messages[-1].reasoning_content == "provider-visible reasoning"
    assert any(
        event.type == "model.reasoning" and event.detail == "provider-visible reasoning"
        for event in store.load_events(run.id)
    )
