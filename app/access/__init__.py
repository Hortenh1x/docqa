"""Access control for retrieval: who asks (roles) versus what a chunk is labelled (labels)."""

from app.access.roles import Principal, resolve_principal

__all__ = ["Principal", "resolve_principal"]
