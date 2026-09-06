"""Access markers: how a section of a document declares who may read it.

A section is restricted by a visible line placed right after its heading (or before the
first heading to classify the whole document), exactly like real corporate documents:

    Access: Managers only
    Zugriff: nur Führungskräfte
    Access: All staff                      (explicitly open — resets an inherited label)

The whole block must be the marker (``Access:``/``Zugriff:`` at the start of the line) —
prose such as "Access: via Fern is granted…" never matches because a marker block is a
single short line and the group name must be known. The chunker propagates the label to
the section's sub-sections until a heading of the same or a higher level; every chunk
carries it, and retrieval filters on it (see app/access).

Unknown group names fail **closed**: the section is labelled ``leadership`` (the most
restrictive label) and a warning is logged — a typo must never open a section up.
"""

import re
from typing import Final

import structlog

log = structlog.get_logger("docqa.access")

LABEL_ALL: Final = "all"
LABEL_MANAGERS: Final = "managers"
LABEL_HR: Final = "hr"
LABEL_FINANCE: Final = "finance"
LABEL_LEADERSHIP: Final = "leadership"

KNOWN_LABELS: Final[tuple[str, ...]] = (
    LABEL_ALL,
    LABEL_MANAGERS,
    LABEL_HR,
    LABEL_FINANCE,
    LABEL_LEADERSHIP,
)
FAIL_CLOSED_LABEL: Final = LABEL_LEADERSHIP

# human names (EN + DE) → canonical label; matched case-insensitively on the group
# text after "Access:"/"Zugriff:", with an optional trailing "only" / leading "nur"
_ALIASES: Final[dict[str, str]] = {
    "all": LABEL_ALL,
    "all staff": LABEL_ALL,
    "all employees": LABEL_ALL,
    "everyone": LABEL_ALL,
    "alle": LABEL_ALL,
    "alle mitarbeitenden": LABEL_ALL,
    "alle mitarbeiter": LABEL_ALL,
    "managers": LABEL_MANAGERS,
    "manager": LABEL_MANAGERS,
    "people managers": LABEL_MANAGERS,
    "line managers": LABEL_MANAGERS,
    "führungskräfte": LABEL_MANAGERS,
    "fuehrungskraefte": LABEL_MANAGERS,
    "hr": LABEL_HR,
    "people & culture": LABEL_HR,
    "people and culture": LABEL_HR,
    "people & culture team": LABEL_HR,
    "personalabteilung": LABEL_HR,
    "finance": LABEL_FINANCE,
    "finance team": LABEL_FINANCE,
    "finanzen": LABEL_FINANCE,
    "finanzabteilung": LABEL_FINANCE,
    "leadership": LABEL_LEADERSHIP,
    "leadership team": LABEL_LEADERSHIP,
    "executive team": LABEL_LEADERSHIP,
    "executives": LABEL_LEADERSHIP,
    "geschäftsführung": LABEL_LEADERSHIP,
    "geschaeftsfuehrung": LABEL_LEADERSHIP,
}

_MARKER_RE: Final = re.compile(
    r"^\**\s*(?:access|zugriff)\s*:\s*(?:nur\s+)?(?P<group>[^\n.:;]{1,60}?)(?:\s+only)?\**\s*"
    r"(?P<rest>$|[.:;\u2014\u2013-]\s*.*)",
    re.IGNORECASE | re.DOTALL,
)
_MAX_MARKER_CHARS: Final = 80


def parse_access_marker(block: str) -> str | None:
    """The label a block declares, or None when the block is not a marker.

    Two forms are recognized:

    - the whole block is one short marker line — the canonical form; an unknown group
      fails closed (``leadership``) with a warning;
    - the block *starts* with a marker followed by a sentence terminator ("Access:
      Finance only. The limit…") — PDF extraction sometimes glues the marker line to the
      paragraph below it. Only known group names count here, so ordinary prose that
      happens to start with "Access:" is never mistaken for a marker.
    """
    text = block.strip()
    if not text:
        return None
    match = _MARKER_RE.match(text)
    if match is None:
        return None
    group = " ".join(match.group("group").split()).strip(" *").casefold()
    label = _ALIASES.get(group)
    whole_line = "\n" not in text and len(text) <= _MAX_MARKER_CHARS and not match.group("rest")
    if label is None:
        if not whole_line:
            return None
        log.warning("access_marker_unknown_group", group=group, applied=FAIL_CLOSED_LABEL)
        return FAIL_CLOSED_LABEL
    return label
