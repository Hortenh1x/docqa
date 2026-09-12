from app.core.errors import DomainError


class BudgetExceededError(DomainError):
    status = 429
    code = "quota_exceeded"
    title = "Daily AI budget exhausted"


class BudgetUnavailableError(DomainError):
    status = 503
    code = "budget_unavailable"
    title = "AI spending controls unavailable"
