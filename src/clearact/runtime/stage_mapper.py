from clearact.domain.enums import RiskLevel, Stage
from clearact.domain.models import Action


class StageMapper:
    def __init__(self, tool_config: dict[str, dict]) -> None:
        self._tool_config = tool_config

    def map(self, action: Action, risk: RiskLevel) -> tuple[Stage, str, str]:
        config = self._tool_config.get(action.tool_name, {})
        stage = Stage(config.get("stage", "act"))
        title = config.get("display_name", action.tool_name)
        template = config.get("progress_template", "正在执行：{tool}")
        detail = template.format(tool=action.tool_name, **action.arguments)
        return stage, title, detail
