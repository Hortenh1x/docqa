"""Access markers (content labels) and roles (principals)."""

import pytest

from app.access import Principal, resolve_principal
from app.access.roles import sees_everything
from app.config import Settings
from app.core.errors import InvalidRoleError
from app.ingestion.access import FAIL_CLOSED_LABEL, parse_access_marker


def _settings(**overrides) -> Settings:
    return Settings(database_url="postgresql+asyncpg://x/x", redis_url="redis://x", **overrides)


# --- markers ---


@pytest.mark.parametrize(
    ("block", "label"),
    [
        ("Access: Managers only", "managers"),
        ("Access: managers", "managers"),
        ("ACCESS: People & Culture only", "hr"),
        ("Access: HR only", "hr"),
        ("Access: Finance only.", "finance"),
        ("Access: Leadership only", "leadership"),
        ("Access: All staff", "all"),
        ("**Access: Finance only**", "finance"),
        ("Zugriff: nur Führungskräfte", "managers"),
        ("Zugriff: nur Finanzen", "finance"),
        ("Zugriff: nur Geschäftsführung", "leadership"),
        ("Zugriff: alle Mitarbeitenden", "all"),
        ("  Access:   Executive Team   only  ", "leadership"),
    ],
)
def test_marker_forms(block, label):
    assert parse_access_marker(block) == label


def test_marker_glued_to_following_paragraph_by_pdf_extraction():
    glued = "Access: Finance only. Card limits above the threshold need CFO approval."
    assert parse_access_marker(glued) == "finance"
    dashed = "Access: Managers only — calibration guidance for the review cycle."
    assert parse_access_marker(dashed) == "managers"


@pytest.mark.parametrize(
    "block",
    [
        "Access via Fern is granted on day one.",
        # prose starting with "Access:" — unknown group and not a lone marker line
        "Access: via Fern is granted on day one.",
        "The access policy is described in POL-005.",
        "## 5. Access and accounts",
        "",
        "Access: Managers only\nThe second line makes it a paragraph, not a marker.",
        "Access: " + "x" * 100,
    ],
)
def test_non_markers(block):
    assert parse_access_marker(block) is None


def test_unknown_group_on_a_lone_marker_line_fails_closed():
    # a typo must never open a section up: the most restrictive label applies
    assert parse_access_marker("Access: Finannce only") == FAIL_CLOSED_LABEL
    assert parse_access_marker("Zugriff: nur Vorstand") == FAIL_CLOSED_LABEL


# --- roles ---


def test_default_role_is_least_privilege():
    principal = resolve_principal(_settings(), None)
    assert principal == Principal(role="employee", labels=("all",))
    assert principal.sees("all") and not principal.sees("hr")


@pytest.mark.parametrize(
    ("role", "labels"),
    [
        ("employee", ("all",)),
        ("manager", ("all", "managers")),
        ("hr", ("all", "managers", "hr")),
        ("finance", ("all", "managers", "finance")),
        ("leadership", ("all", "managers", "hr", "finance", "leadership")),
    ],
)
def test_builtin_roles(role, labels):
    assert resolve_principal(_settings(), role).labels == labels


def test_hr_and_finance_are_siblings_not_a_ladder():
    settings = _settings()
    assert not resolve_principal(settings, "hr").sees("finance")
    assert not resolve_principal(settings, "finance").sees("hr")


def test_unknown_role_is_rejected():
    with pytest.raises(InvalidRoleError) as info:
        resolve_principal(_settings(), "intern")
    assert info.value.status == 422
    assert info.value.extra["role"] == "intern"


def test_sees_everything_only_for_the_full_label_set():
    settings = _settings()
    assert sees_everything(settings, resolve_principal(settings, "leadership"))
    assert not sees_everything(settings, resolve_principal(settings, "hr"))


def test_settings_reject_roles_without_the_open_label():
    with pytest.raises(ValueError, match="must include the 'all' label"):
        _settings(access_roles={"employee": ["all"], "auditor": ["finance"]})


def test_settings_reject_unknown_default_role():
    with pytest.raises(ValueError, match="ACCESS_DEFAULT_ROLE"):
        _settings(access_roles={"staff": ["all"]}, access_default_role="employee")
