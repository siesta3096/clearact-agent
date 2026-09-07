from __future__ import annotations

from clearact.domain.models import ToolDefinition, ToolResult
from clearact.tools.base import ToolContext


class DeclareWorkflowStepTool:
    """A zero-risk marker the model uses to create an honest UI workflow phase."""

    name = "declare_workflow_step"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Create a visible workflow step before beginning a meaningful new phase. "
                "Use a task-specific title and a concise description of what this phase will do. "
                "This does not perform external work."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Specific short phase name, 2-12 words."},
                    "summary": {"type": "string", "description": "Concise user-visible plan for this phase."},
                },
                "required": ["title", "summary"],
            },
        )

    async def execute(self, arguments: dict, _context: ToolContext, action_id: str) -> ToolResult:
        return ToolResult(
            action_id=action_id,
            tool_name=self.name,
            ok=True,
            content="Workflow step recorded. Continue with the work described in this phase.",
        )
