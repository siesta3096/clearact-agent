from clearact.domain.enums import RiskLevel, Stage
from clearact.domain.models import Action
from clearact.runtime.stage_mapper import StageMapper


def test_stage_mapper_uses_configured_display_metadata():
    mapper = StageMapper(
        {
            "write_file": {
                "stage": "act",
                "display_name": "写入文件",
                "progress_template": "正在写入 {path}",
            }
        }
    )

    stage, title, detail = mapper.map(Action(tool_name="write_file", arguments={"path": "answer.txt"}), RiskLevel.GREEN)

    assert stage is Stage.ACT
    assert title == "写入文件"
    assert detail == "正在写入 answer.txt"


def test_stage_mapper_has_safe_defaults():
    stage, title, detail = StageMapper({}).map(Action(tool_name="custom", arguments={}), RiskLevel.GREEN)

    assert stage is Stage.ACT
    assert title == "custom"
    assert detail == "正在执行：custom"
