from __future__ import annotations

from clearact.context.builder import ContextBuilder
from clearact.domain.enums import DecisionOutcome, RunStatus, Stage
from clearact.domain.models import ChatMessage, Run, WorkflowStep
from clearact.providers.base import LLMProvider
from clearact.runtime.approvals import ApprovalGate
from clearact.runtime.checkpoints import create_checkpoint
from clearact.runtime.event_bus import EventBus
from clearact.runtime.events import (
    action_completed,
    action_started,
    approval_required,
    model_reasoning,
    run_completed,
    run_started,
)
from clearact.runtime.executor import ToolExecutor
from clearact.runtime.policy import PolicyEngine
from clearact.runtime.risk import RiskEvaluator
from clearact.runtime.stage_mapper import StageMapper
from clearact.runtime.state import transition
from clearact.storage.checkpoint_store import CheckpointStore
from clearact.storage.run_store import RunStore
from clearact.tools.base import ToolContext
from clearact.tools.registry import ToolRegistry


class AgentRunner:
    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        context_builder: ContextBuilder,
        risk_evaluator: RiskEvaluator,
        policy_engine: PolicyEngine,
        approval_gate: ApprovalGate,
        executor: ToolExecutor,
        event_bus: EventBus,
        run_store: RunStore,
        checkpoint_store: CheckpointStore,
        tool_context: ToolContext,
        stage_mapper: StageMapper,
        max_iterations: int,
        max_tool_calls: int,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._context_builder = context_builder
        self._risk_evaluator = risk_evaluator
        self._policy_engine = policy_engine
        self._approval_gate = approval_gate
        self._executor = executor
        self._event_bus = event_bus
        self._run_store = run_store
        self._checkpoint_store = checkpoint_store
        self._tool_context = tool_context
        self._stage_mapper = stage_mapper
        self._max_iterations = max_iterations
        self._max_tool_calls = max_tool_calls

    async def run(self, run: Run) -> str:
        try:
            return await self._run_loop(run)
        except Exception:
            if run.status in {RunStatus.CREATED, RunStatus.RUNNING, RunStatus.WAITING_APPROVAL}:
                transition(run, RunStatus.FAILED)
                self._run_store.save_run(run)
            raise

    async def _run_loop(self, run: Run) -> str:
        transition(run, RunStatus.RUNNING)
        self._run_store.save_run(run)
        await self._event_bus.publish(run_started(run))
        await self._create_stage_note(run, "understand")
        if not run.workflow_steps:
            run.workflow_steps.append(WorkflowStep(title="理解任务", summary="正在识别目标、约束与完成条件。"))
            self._run_store.save_run(run)
        recent_tool_names: set[str] = set()
        tool_call_count = 0

        for _ in range(self._max_iterations):
            messages, tools = self._context_builder.build(run.messages, self._registry.definitions(), recent_tool_names)
            response = await self._provider.chat(messages, tools)
            reasoning = (response.reasoning_content or "").strip() or None
            if not response.tool_calls:
                if "prepare" not in run.stage_notes:
                    await self._create_stage_note(run, "prepare")
                final = response.content or "任务已结束，但模型没有提供最终说明。"
                run.messages.append(ChatMessage(role="assistant", content=final, reasoning_content=reasoning))
                # Save before publishing so a polling UI never sees an event
                # whose referenced reasoning is absent from the run ledger.
                self._run_store.save_run(run)
                if reasoning:
                    await self._event_bus.publish(model_reasoning(run, reasoning, Stage.DELIVER))
                transition(run, RunStatus.COMPLETED)
                self._run_store.save_run(run)
                await self._event_bus.publish(run_completed(run))
                return final

            # Persist and execute precisely the tool plan accepted from the model.
            # A hidden per-turn search cap made the UI show planned searches that
            # never ran and breaks parity with nanobot's default tool semantics.
            accepted_actions = list(response.tool_calls)
            self._record_declared_steps(run, accepted_actions)
            run.messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    reasoning_content=reasoning,
                    tool_calls=accepted_actions,
                )
            )
            # Persist model decisions immediately so the web UI can show live progress.
            self._run_store.save_run(run)
            if reasoning:
                first_action = accepted_actions[0]
                assessment = self._risk_evaluator.assess(first_action)
                stage, _, _ = self._stage_mapper.map(first_action, assessment.level)
                await self._event_bus.publish(model_reasoning(run, reasoning, stage))
            recent_tool_names = set()
            for action in accepted_actions:
                tool_call_count += 1
                if tool_call_count > self._max_tool_calls:
                    raise RuntimeError(f"Agent reached the maximum tool-call limit ({self._max_tool_calls}).")
                recent_tool_names.add(action.tool_name)
                if action.tool_name == "declare_workflow_step":
                    run.messages.append(
                        ChatMessage(
                            role="tool",
                            name=action.tool_name,
                            tool_call_id=action.id,
                            content="Workflow step recorded. Continue with this phase.",
                        )
                    )
                    self._run_store.save_run(run)
                    continue
                assessment = self._risk_evaluator.assess(action)
                decision = self._policy_engine.decide(assessment, run.policy, action.tool_name)
                stage, title, detail = self._stage_mapper.map(action, assessment.level)
                if stage.value == "prepare" and "prepare" not in run.stage_notes:
                    await self._create_stage_note(run, "prepare")
                if decision.outcome == DecisionOutcome.DENY:
                    result_content = f"Action denied: {decision.reason}"
                    run.messages.append(
                        ChatMessage(
                            role="tool",
                            name=action.tool_name,
                            tool_call_id=action.id,
                            content=result_content,
                            metadata={"status": "denied", "reason": decision.reason},
                        )
                    )
                    continue
                if decision.outcome == DecisionOutcome.REQUIRE_APPROVAL:
                    transition(run, RunStatus.WAITING_APPROVAL)
                    await self._event_bus.publish(approval_required(run, action, assessment.level, decision.reason))
                    granted = await self._approval_gate.request(action, assessment)
                    if run.status == RunStatus.WAITING_APPROVAL:
                        transition(run, RunStatus.RUNNING)
                    if not granted:
                        result_content = (
                            "User declined this action. Continue with a safe alternative or explain the limitation."
                        )
                        run.messages.append(
                            ChatMessage(
                                role="tool",
                                name=action.tool_name,
                                tool_call_id=action.id,
                                content=result_content,
                            )
                        )
                        continue
                await self._event_bus.publish(action_started(run, action, stage, assessment.level, title, detail))
                # The event is persisted by the bus; persist the decision too before
                # awaiting the tool so polling clients do not appear stalled.
                self._run_store.save_run(run)
                try:
                    result = await self._executor.execute(action, self._tool_context)
                except Exception as exc:
                    # Persist and emit every failed attempt just like successful
                    # ones. Otherwise polling clients lose the current tool result
                    # until a later model turn happens to save the run.
                    result_content = f"Tool execution failed: {type(exc).__name__}: {exc}"
                    run.messages.append(
                        ChatMessage(
                            role="tool",
                            name=action.tool_name,
                            tool_call_id=action.id,
                            content=result_content,
                            metadata={"status": "failed", "error_type": type(exc).__name__, "error": str(exc)},
                        )
                    )
                    self._run_store.save_run(run)
                    await self._event_bus.publish(
                        action_completed(run, action, stage, assessment.level, result_content[:240])
                    )
                    continue
                run.messages.append(
                    ChatMessage(
                        role="tool",
                        name=action.tool_name,
                        tool_call_id=action.id,
                        content=result.content,
                        metadata={"status": "succeeded", **result.metadata},
                    )
                )
                checkpoint = create_checkpoint(run.id, action)
                self._checkpoint_store.save(checkpoint)
                self._run_store.save_run(run)
                await self._event_bus.publish(
                    action_completed(run, action, stage, assessment.level, result.content[:240])
                )

        raise RuntimeError(f"Agent reached the maximum iteration limit ({self._max_iterations}).")

    def _record_declared_steps(self, run: Run, actions: list) -> None:
        """Persist model-created phase cards and attach later actions to the current phase."""
        current_step = run.workflow_steps[-1] if run.workflow_steps else None
        for action in actions:
            if action.tool_name == "declare_workflow_step":
                title = str(action.arguments.get("title", "")).strip()
                summary = str(action.arguments.get("summary", "")).strip()
                if title and summary:
                    current_step = WorkflowStep(title=title[:80], summary=summary[:500])
                    run.workflow_steps.append(current_step)
                continue
            if current_step is not None:
                current_step.action_ids.append(action.id)

    async def _create_stage_note(self, run: Run, stage: str) -> None:
        """Persist a concise, user-visible process summary for a workflow card."""
        prompts = {
            "understand": (
                "用中文写一段简洁但具体的任务分析：目标、需要比较或验证的要点、"
                "资料判断标准与计划步骤。不要回答任务本身，不要使用工具，不要提及提示词。"
            ),
            "prepare": (
                "用中文写一段简洁但具体的报告编写说明：将如何组织结论、证据、"
                "限制条件和建议。不要给出最终答复，不要使用工具，不要提及提示词。"
            ),
        }
        prompt = prompts.get(stage)
        if not prompt:
            return
        summarize_stage = getattr(self._provider, "summarize_stage", None)
        if summarize_stage is None:
            return
        try:
            note = (await summarize_stage(prompt, run.goal)).strip()
            if note:
                run.stage_notes[stage] = note
                self._run_store.save_run(run)
        except Exception:
            # Stage summaries enhance observability but must never block the actual task.
            return
