from typing import Protocol

from clearact.domain.models import Action, RiskAssessment


class ApprovalGate(Protocol):
    async def request(self, action: Action, assessment: RiskAssessment) -> bool: ...


class DenyAllApprovalGate:
    async def request(self, action: Action, assessment: RiskAssessment) -> bool:
        return False
