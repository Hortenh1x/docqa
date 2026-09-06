"""Roles → labels.

Two vocabularies, deliberately separate:

- **labels** classify content (``all``, ``managers``, ``hr``, ``finance``, ``leadership``) —
  they come from access markers in the documents (app/ingestion/access.py);
- **roles** describe who is asking (``employee``, ``manager``, …) — a claim the trusted
  API client makes about its end user (``role`` on POST /v1/query).

The map role → visible labels lives in settings (``ACCESS_ROLES``); nothing here is
hierarchical by construction, so HR and Finance can each see their own content without
seeing each other's. A missing role resolves to the default role (least privilege).
"""

from dataclasses import dataclass

from app.config import Settings
from app.core.errors import InvalidRoleError


@dataclass(frozen=True)
class Principal:
    role: str
    labels: tuple[str, ...]

    def sees(self, label: str) -> bool:
        return label in self.labels


def resolve_principal(settings: Settings, role: str | None) -> Principal:
    name = role if role is not None else settings.access_default_role
    labels = settings.access_roles.get(name)
    if labels is None:
        raise InvalidRoleError(
            f"Unknown role '{name}'. Known roles: {', '.join(settings.access_roles)}.",
            role=name,
        )
    return Principal(role=name, labels=tuple(labels))


def all_labels(settings: Settings) -> tuple[str, ...]:
    """Every label any role can see — used to short-circuit filters for full-access roles."""
    seen: dict[str, None] = {}
    for labels in settings.access_roles.values():
        for label in labels:
            seen.setdefault(label, None)
    return tuple(seen)


def sees_everything(settings: Settings, principal: Principal) -> bool:
    return set(all_labels(settings)) <= set(principal.labels)
