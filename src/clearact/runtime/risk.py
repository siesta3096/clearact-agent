from __future__ import annotations

from pathlib import Path

from clearact.domain.enums import RiskLevel
from clearact.domain.models import Action, RiskAssessment


class RiskEvaluator:
    def __init__(self, workspace_root: Path, rules: dict) -> None:
        self._workspace_root = workspace_root.resolve()
        self._rules = rules

    def assess(self, action: Action) -> RiskAssessment:
        if action.tool_name in self._rules.get("hard_stop_operations", []):
            return RiskAssessment(
                level=RiskLevel.RED,
                hard_stop=True,
                reasons=["该操作属于必须单独确认的重大外部或系统行为。"],
            )
        if action.tool_name in {"web_search", "fetch_url", "list_files", "read_file"}:
            return RiskAssessment(level=RiskLevel.WHITE, reasons=["只读操作，不会改变状态。"])
        if action.tool_name.startswith("mcp__"):
            return RiskAssessment(
                level=RiskLevel.YELLOW, reasons=["第三方 MCP 工具的实际副作用由服务声明；默认按受控外部操作处理。"]
            )
        if action.tool_name == "write_file":
            return self._assess_write(action)
        if action.tool_name in {"delete_file", "execute_command"}:
            return RiskAssessment(level=RiskLevel.RED, reasons=["删除或命令执行属于高影响操作。"])
        return RiskAssessment(level=RiskLevel.YELLOW, reasons=["未知工具默认按受控修改处理。"])

    def _assess_write(self, action: Action) -> RiskAssessment:
        raw_path = action.arguments.get("path")
        if not isinstance(raw_path, str):
            return RiskAssessment(
                level=RiskLevel.RED,
                hard_stop=True,
                reasons=["写入路径缺失或格式无效。"],
            )
        candidate = Path(raw_path).expanduser()
        target = candidate.resolve() if candidate.is_absolute() else (self._workspace_root / candidate).resolve()
        if not self._is_within_workspace(target):
            # Yellow can inspect outside paths, but may only write there after approval.
            # Red permits this ordinary user-file write automatically; system paths remain
            # blocked by the filesystem tool itself.
            return RiskAssessment(level=RiskLevel.RED, reasons=["将写入工作区外的文件。"])
        if target.exists():
            return RiskAssessment(level=RiskLevel.YELLOW, reasons=["将修改已有文件。"])
        return RiskAssessment(level=RiskLevel.GREEN, reasons=["将在授权工作区创建新文件，可通过快照撤销。"])

    def _is_within_workspace(self, target: Path) -> bool:
        try:
            target.relative_to(self._workspace_root)
        except ValueError:
            return False
        return True
