class ClearActError(Exception):
    pass


class ToolValidationError(ClearActError):
    pass


class ScopeViolationError(ClearActError):
    pass


class RunCancelledError(ClearActError):
    pass


class ApprovalRejectedError(ClearActError):
    pass
