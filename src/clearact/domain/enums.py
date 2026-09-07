from enum import Enum


class RiskLevel(str, Enum):
    WHITE = "white"
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"

    @property
    def rank(self) -> int:
        return list(type(self)).index(self)


class RunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Stage(str, Enum):
    UNDERSTAND = "understand"
    COLLECT = "collect"
    ANALYZE = "analyze"
    PREPARE = "prepare"
    ACT = "act"
    DELIVER = "deliver"


class DecisionOutcome(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class ViewMode(str, Enum):
    SIMPLE = "simple"
    EXPERT = "expert"
