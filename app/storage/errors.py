from app.core.errors import DomainError


class StorageUnavailableError(DomainError):
    status = 503
    code = "storage_unavailable"
    title = "Document storage unavailable"
