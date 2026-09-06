"""Corpus v2 specification: the world, the facts and the documents — facts first.

Everything numeric in the generated corpus comes from here. ``build()`` materializes the
fact registry (values are either pinned from the v1 registry or drawn from a seeded RNG,
unique per unit so a value can be traced to exactly one fact) and the document manifest
(300 documents across families, with versions, country variants, restricted sections and
cross references). ``make_spec.py`` writes both as YAML; the generator, the validator and
the golden builder read only those files.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

SEED = 20260906

COUNTRIES = {
    "DE": "Germany",
    "PT": "Portugal",
    "ES": "Spain",
    "PL": "Poland",
    "FR": "France",
    "UK": "United Kingdom",
}
TEAMS = [
    "Routing Core",
    "Fleet Insights",
    "Platform & Infrastructure",
    "Customer Success",
    "Go-to-Market",
]
YEARS = [2023, 2024, 2025, 2026]

MONTHS_EN = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
MONTHS_DE = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]

# unit → (EN noun, DE noun)
UNITS = {
    "days": ("days", "Tage"),
    "calendar days": ("calendar days", "Kalendertage"),
    "working days": ("working days", "Arbeitstage"),
    "business days": ("business days", "Werktage"),
    "weeks": ("weeks", "Wochen"),
    "months": ("months", "Monate"),
    "years": ("years", "Jahre"),
    "hours": ("hours", "Stunden"),
    "minutes": ("minutes", "Minuten"),
    "ms": ("ms", "ms"),
    "requests per minute": ("requests per minute", "Anfragen pro Minute"),
    "GB": ("GB", "GB"),
    "people": ("people", "Personen"),
    "spaces": ("spaces", "Stellplätze"),
    "slots": ("slots", "Termine"),
    "lines": ("lines", "Zeilen"),
    "per km": ("per km", "pro km"),
    "per month": ("per month", "pro Monat"),
    "per year": ("per year", "pro Jahr"),
    "per day": ("per day", "pro Tag"),
    "per night": ("per night", "pro Nacht"),
}

LABELS = ("all", "managers", "hr", "finance", "leadership")


@dataclass
class Fact:
    id: str
    key: str
    kind: str  # money | percent | count | date | text
    unit: str  # for count: the noun; for money: optional suffix ("per km"); "" otherwise
    value: str | int | float
    text_en: str
    text_de: str
    doc: str  # base doc id ("POL-001")
    versions: list[str]  # doc versions carrying this value ([] = unversioned doc)
    section: int
    label: str = "all"
    current: bool = True
    statement: str = ""  # sentence with {value}; the generator asks for it verbatim-ish
    hints: list[str] = field(default_factory=list)
    family: str | None = None  # "country:<key>" | "year:<key>" | "version:<key>" | "meeting:<key>"
    variant: str | None = None
    buried: bool = False
    table: str | None = None  # table id when the fact is a row of a table
    row_label: str | None = None
    stale_in: list[str] = field(default_factory=list)  # FAQ docs that still state this old value


@dataclass
class Doc:
    doc_id: str
    base: str
    family: str
    title: str
    version: str | None
    effective_date: str
    owner: str
    lang: str
    words: tuple[int, int]
    sections: list[str]
    default_label: str = "all"
    restricted: dict[int, str] = field(default_factory=dict)  # section number → label
    facts: list[str] = field(default_factory=list)
    mentions: list[dict[str, str]] = field(default_factory=list)  # {fact, ref, note}
    supersedes: str | None = None
    superseded_by: str | None = None
    notes: list[str] = field(default_factory=list)
    mirror_of: str | None = None
    format: str = "pdf"
    date_context: str | None = None  # meeting notes / updates: "as of" date


# ---------------------------------------------------------------- formatting helpers


def fmt_money(n: float | int, lang: str, suffix: str = "") -> str:
    if isinstance(n, float) and not n.is_integer():
        en = f"€{n:,.2f}"
        de = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"
    else:
        en = f"€{int(n):,}"
        de = f"{int(n):,}".replace(",", ".") + " €"
    text = en if lang == "en" else de
    if suffix:
        unit = UNITS[suffix][0 if lang == "en" else 1]
        text = f"{text} {unit}"
    return text


def fmt_percent(n: float | int, lang: str) -> str:
    s = f"{n:g}"
    if lang == "de":
        return s.replace(".", ",") + " %"
    return s + "%"


_SINGULAR_DE = {
    "Tage": "Tag",
    "Kalendertage": "Kalendertag",
    "Arbeitstage": "Arbeitstag",
    "Werktage": "Werktag",
    "Wochen": "Woche",
    "Monate": "Monat",
    "Jahre": "Jahr",
    "Stunden": "Stunde",
    "Minuten": "Minute",
    "Personen": "Person",
    "Stellplätze": "Stellplatz",
    "Termine": "Termin",
    "Zeilen": "Zeile",
}


def fmt_count(n: int, unit: str, lang: str) -> str:
    noun = UNITS[unit][0 if lang == "en" else 1]
    if n == 1:
        if (
            lang == "en"
            and noun.endswith("s")
            and noun not in ("ms",)
            and " " not in noun.split()[-1][:-1]
        ):
            noun = noun[:-1] if not noun.endswith("per minute") else noun
        elif lang == "de":
            noun = _SINGULAR_DE.get(noun, noun)
    return f"{n} {noun}"


def fmt_date(month: int, day: int, lang: str) -> str:
    if lang == "de":
        return f"{day}. {MONTHS_DE[month - 1]}"
    return f"{MONTHS_EN[month - 1]} {day}"


# ---------------------------------------------------------------- registry builder


class Registry:
    """Allocates unique values per (kind, unit) so every number traces to one fact."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.facts: list[Fact] = []
        self.used: dict[tuple[str, str], set[str]] = {}
        self._n = 0

    def _next_id(self) -> str:
        self._n += 1
        return f"F2-{self._n:03d}"

    def _reserve(self, kind: str, unit: str, text: str) -> bool:
        pool = self.used.setdefault((kind, unit), set())
        if text in pool:
            return False
        pool.add(text)
        return True

    def pick(self, kind: str, unit: str, lo: float, hi: float, step: float = 1) -> float | int:
        for _ in range(500):
            steps = int(round((hi - lo) / step))
            raw = lo + step * self.rng.randint(0, steps)
            value: float | int = round(raw, 2) if isinstance(step, float) and step < 1 else int(raw)
            text = self.render(kind, unit, value, "en")
            if self._reserve(kind, unit, text):
                return value
        raise RuntimeError(f"no unique value left for {kind}/{unit} in {lo}-{hi}")

    def pin(self, kind: str, unit: str, value: float | int) -> float | int:
        self._reserve(kind, unit, self.render(kind, unit, value, "en"))
        return value

    @staticmethod
    def render(kind: str, unit: str, value: str | int | float, lang: str) -> str:
        if kind == "money":
            return fmt_money(value, lang, unit)  # type: ignore[arg-type]
        if kind == "percent":
            return fmt_percent(value, lang)  # type: ignore[arg-type]
        if kind == "count":
            return fmt_count(int(value), unit, lang)
        if kind == "date":
            month, day = (int(x) for x in str(value).split("-"))
            return fmt_date(month, day, lang)
        return str(value)

    def add(
        self,
        key: str,
        kind: str,
        unit: str,
        value: float | int | str,
        doc: str,
        section: int,
        statement: str,
        hints: list[str],
        *,
        versions: list[str] | None = None,
        label: str = "all",
        current: bool = True,
        family: str | None = None,
        variant: str | None = None,
        buried: bool = False,
        table: str | None = None,
        row_label: str | None = None,
        stale_in: list[str] | None = None,
    ) -> Fact:
        fact = Fact(
            id=self._next_id(),
            key=key,
            kind=kind,
            unit=unit,
            value=value,
            text_en=self.render(kind, unit, value, "en"),
            text_de=self.render(kind, unit, value, "de"),
            doc=doc,
            versions=versions or [],
            section=section,
            label=label,
            current=current,
            statement=statement,
            hints=hints,
            family=family,
            variant=variant,
            buried=buried,
            table=table,
            row_label=row_label,
            stale_in=stale_in or [],
        )
        self.facts.append(fact)
        return fact


# ---------------------------------------------------------------- policies

# (base, title, owner, versions [(version, effective)], sections)
POLICIES: list[tuple[str, str, str, list[tuple[str, str]], list[str]]] = [
    (
        "POL-001",
        "Vacation & Leave Policy",
        "People & Culture",
        [("1.0", "2023-01-01"), ("2.0", "2024-03-01"), ("2.3", "2025-04-01")],
        [
            "Purpose",
            "Scope",
            "Annual vacation entitlement",
            "Requesting vacation",
            "Carryover",
            "Special leave",
            "Questions",
        ],
    ),
    (
        "POL-002",
        "Remote Work Policy",
        "People & Culture",
        [("1.0", "2022-09-01"), ("2.0", "2024-06-01")],
        [
            "Purpose",
            "Where you may work",
            "Working hours and availability",
            "Equipment and workspace",
            "Security at home",
            "Questions",
        ],
    ),
    (
        "POL-003",
        "Workation Guideline",
        "People & Culture",
        [("1.0", "2024-01-15"), ("1.1", "2025-01-15")],
        ["Purpose", "How much workation is allowed", "Approval", "Tax and insurance", "Questions"],
    ),
    (
        "POL-004",
        "Travel & Expense Policy",
        "Finance",
        [("2.0", "2023-06-01"), ("3.0", "2025-02-01")],
        [
            "Purpose",
            "When to travel",
            "Booking",
            "Per-diems",
            "What is reimbursable",
            "Submitting expenses",
            "Questions",
        ],
    ),
    (
        "POL-005",
        "IT & Information Security Policy",
        "Information Security",
        [("3.0", "2023-09-01"), ("4.1", "2025-09-01")],
        [
            "Purpose",
            "Accounts and passwords",
            "Security training",
            "Devices",
            "Reporting incidents",
            "Questions",
        ],
    ),
    (
        "POL-006",
        "Equipment & Hardware Policy",
        "Workplace & Operations",
        [("1.0", "2023-02-01"), ("2.2", "2025-05-01")],
        [
            "Purpose",
            "Standard setup",
            "Equipment budget",
            "Refresh cycle",
            "Returning equipment",
            "Repairs and loss",
            "Questions",
        ],
    ),
    (
        "POL-007",
        "Sick Leave & Medical Absence",
        "People & Culture",
        [("1.0", "2023-03-01"), ("1.2", "2024-03-01")],
        [
            "Purpose",
            "Telling us",
            "Doctor's certificate",
            "Pay during illness",
            "Returning to work",
            "Questions",
        ],
    ),
    (
        "POL-008",
        "Parental Leave Policy",
        "People & Culture",
        [("1.0", "2023-05-01"), ("2.1", "2025-07-01")],
        [
            "Purpose",
            "Scope",
            "Telling us",
            "Leave and pay",
            "Before the leave",
            "During the leave",
            "Returning to work",
            "Questions",
        ],
    ),
    (
        "POL-009",
        "Code of Conduct",
        "Leadership Team",
        [("0.9", "2022-11-01"), ("1.0", "2023-05-01")],
        [
            "Purpose",
            "How we treat each other",
            "Gifts and hospitality",
            "Conflicts of interest",
            "Speaking up",
            "Questions",
        ],
    ),
    (
        "POL-010",
        "Internal Data Protection Policy",
        "Legal",
        [("1.0", "2023-03-01"), ("1.5", "2024-03-01"), ("2.0", "2025-03-01")],
        [
            "Purpose",
            "Personal data we handle",
            "Retention",
            "Requests from data subjects",
            "Working with processors",
            "Questions",
        ],
    ),
    (
        "POL-011",
        "Training & Development Policy",
        "People & Culture",
        [("1.0", "2023-08-01"), ("1.5", "2024-08-01"), ("2.0", "2025-08-01")],
        ["Purpose", "Learning budget", "Conferences", "Internal learning", "Questions"],
    ),
    (
        "POL-012",
        "Home Office Allowance Policy",
        "Finance",
        [("0.9", "2023-07-01"), ("1.0", "2024-01-01")],
        [
            "Purpose",
            "One-off setup allowance",
            "Monthly connectivity allowance",
            "Claiming",
            "Questions",
        ],
    ),
    (
        "POL-013",
        "Working Time & Overtime Policy",
        "People & Culture",
        [("1.0", "2023-01-01"), ("1.5", "2024-09-01"), ("2.0", "2026-01-01")],
        ["Purpose", "Working time", "Overtime and compensation", "Time tracking", "Questions"],
    ),
    (
        "POL-014",
        "Public Holidays & Bridge Days",
        "People & Culture",
        [("0.9", "2023-01-01"), ("1.0", "2024-01-01")],
        ["Purpose", "Public holidays", "Bridge days", "Questions"],
    ),
    (
        "POL-015",
        "Internal Mobility Policy",
        "People & Culture",
        [("1.0", "2024-04-01"), ("1.1", "2025-10-01")],
        ["Purpose", "Eligibility", "How to apply", "Transition", "Questions"],
    ),
    (
        "POL-016",
        "Speak-Up & Anti-Harassment Policy",
        "People & Culture",
        [("0.9", "2023-05-01"), ("1.0", "2023-11-01")],
        [
            "Purpose",
            "What we do not tolerate",
            "How to raise a concern",
            "What happens next",
            "Questions",
        ],
    ),
    (
        "POL-017",
        "Corporate Card Policy",
        "Finance",
        [("1.0", "2023-04-01"), ("2.0", "2025-06-01")],
        [
            "Purpose",
            "Who gets a card",
            "Using the card",
            "Receipts and reconciliation",
            "Limits and approvals",
            "Questions",
        ],
    ),
    (
        "POL-018",
        "Procurement Policy",
        "Finance",
        [("1.0", "2024-02-01"), ("1.2", "2025-11-01")],
        [
            "Purpose",
            "Requesting a purchase",
            "Approval thresholds",
            "Preferred suppliers",
            "Questions",
        ],
    ),
    (
        "POL-019",
        "Business Travel Insurance",
        "Finance",
        [("0.9", "2023-11-01"), ("1.0", "2024-05-01")],
        ["Purpose", "What is covered", "Making a claim", "Questions"],
    ),
    (
        "POL-020",
        "Meeting Culture Guideline",
        "Leadership Team",
        [("1.0", "2024-08-01"), ("1.1", "2025-09-01")],
        ["Purpose", "Focus time", "Running a good meeting", "Async first", "Questions"],
    ),
    (
        "POL-021",
        "Contractor Engagement Policy",
        "Legal",
        [("0.9", "2023-12-01"), ("1.0", "2024-06-01")],
        [
            "Purpose",
            "When to use a contractor",
            "Duration and renewal",
            "Access and equipment",
            "Questions",
        ],
    ),
    (
        "POL-022",
        "External Communications & Social Media",
        "Go-to-Market",
        [("1.0", "2023-10-01"), ("1.5", "2024-06-01"), ("2.0", "2025-04-01")],
        [
            "Purpose",
            "Speaking for Kranich",
            "Personal accounts",
            "Approval of public content",
            "Questions",
        ],
    ),
    (
        "POL-023",
        "Access Control & Identity Policy",
        "Information Security",
        [("1.0", "2024-01-01"), ("2.0", "2025-12-01")],
        ["Purpose", "Least privilege", "Access reviews", "Joiners, movers, leavers", "Questions"],
    ),
    (
        "POL-024",
        "Vendor & SaaS Management Policy",
        "Finance",
        [("0.9", "2024-07-01"), ("1.0", "2025-01-01")],
        ["Purpose", "Adding a tool", "Renewals and notice", "Offboarding a vendor", "Questions"],
    ),
    (
        "POL-025",
        "Performance Review Policy",
        "People & Culture",
        [("1.0", "2023-01-01"), ("1.5", "2024-01-01"), ("2.0", "2025-01-01")],
        ["Purpose", "Review cycle", "Ratings", "Calibration", "Questions"],
    ),
    (
        "POL-026",
        "Benefits Policy",
        "People & Culture",
        [("2.0", "2024-01-01"), ("3.1", "2026-01-01")],
        ["Purpose", "Wellness budget", "Mobility", "Hardship advances", "Questions"],
    ),
    (
        "POL-027",
        "Security Incident Policy",
        "Information Security",
        [("1.0", "2024-10-01"), ("1.3", "2025-10-01")],
        [
            "Purpose",
            "What counts as an incident",
            "Reporting",
            "Containment",
            "Disclosure decisions",
            "Questions",
        ],
    ),
    (
        "POL-028",
        "Office & Meeting Room Policy",
        "Workplace & Operations",
        [("1.0", "2024-06-01"), ("1.5", "2025-06-01")],
        ["Purpose", "Desks", "Meeting rooms", "Guests", "Questions"],
    ),
]

FORBIDDEN_TOPICS = [
    "sabbatical",
    "unpaid extended leave",
    "company car",
    "car allowance",
    "pet insurance",
    "relocation package",
    "visa sponsorship",
    "stock option",
    "ESOP",
    "equity grant",
    "share option",
    "tuition reimbursement",
    "4-day week",
    "four-day week",
    "unlimited PTO",
    "unlimited vacation",
    "gym membership",
    "childcare subsidy",
    "referral bonus",
    "overtime pay rate",
    "bike leasing",
    "sign-on bonus",
]


def _versions_of(policy: tuple) -> list[str]:
    return [v for v, _ in policy[3]]


def build_facts(reg: Registry) -> None:  # noqa: PLR0915 — one long, readable registry
    cur = {p[0]: _versions_of(p)[-1] for p in POLICIES}

    # --- POL-001 vacation (v1 pinned values as history: 24 → 25 → 27)
    reg.add(
        "vacation.base_days",
        "count",
        "days",
        reg.pin("count", "days", 27),
        "POL-001",
        3,
        "Full-time employees receive {value} of vacation per calendar year.",
        ["how many vacation days", "annual leave allowance"],
        versions=[cur["POL-001"]],
        family="version:vacation.base_days",
        variant=cur["POL-001"],
    )
    reg.add(
        "vacation.base_days",
        "count",
        "days",
        reg.pin("count", "days", 25),
        "POL-001",
        3,
        "Full-time employees receive {value} of vacation per calendar year.",
        ["how many vacation days"],
        versions=["2.0"],
        current=False,
        family="version:vacation.base_days",
        variant="2.0",
        stale_in=["FAQ-001"],
    )
    reg.add(
        "vacation.base_days",
        "count",
        "days",
        reg.pin("count", "days", 24),
        "POL-001",
        3,
        "Full-time employees receive {value} of vacation per calendar year.",
        ["how many vacation days"],
        versions=["1.0"],
        current=False,
        family="version:vacation.base_days",
        variant="1.0",
    )
    reg.add(
        "vacation.carryover_deadline",
        "date",
        "",
        "3-31",
        "POL-001",
        5,
        "Unused vacation days must be taken by {value} of the following year.",
        ["carryover deadline", "when do unused days expire"],
        versions=[cur["POL-001"], "2.0"],
        family="version:vacation.carryover",
        variant=cur["POL-001"],
    )
    reg.add(
        "vacation.carryover_deadline",
        "date",
        "",
        "3-15",
        "POL-001",
        5,
        "Unused vacation days must be taken by {value} of the following year.",
        ["carryover deadline"],
        versions=["1.0"],
        current=False,
        family="version:vacation.carryover",
        variant="1.0",
    )
    reg.add(
        "vacation.notice_weeks",
        "count",
        "weeks",
        reg.pin("count", "weeks", 4),
        "POL-001",
        4,
        "Requests for more than five consecutive days must be submitted {value} in advance.",
        ["how far in advance request vacation"],
        versions=_versions_of(POLICIES[0]),
    )
    reg.add(
        "vacation.cap_days",
        "count",
        "days",
        reg.pin("count", "days", 30),
        "POL-001",
        3,
        "Tenure adds one day per two full years of service, up to a total of {value}.",
        ["maximum vacation days with tenure"],
        versions=[cur["POL-001"]],
    )

    # --- POL-002 remote
    reg.add(
        "remote.share",
        "percent",
        "",
        reg.pin("percent", "", 100),
        "POL-002",
        2,
        "Employees may work up to {value} remotely within their country of employment.",
        ["how much remote work", "fully remote allowed"],
        versions=["2.0"],
        family="version:remote.share",
        variant="2.0",
    )
    reg.add(
        "remote.share",
        "percent",
        "",
        reg.pick("percent", "", 40, 80, 10),
        "POL-002",
        2,
        "Employees may work up to {value} of their working time remotely.",
        ["how much remote work"],
        versions=["1.0"],
        current=False,
        family="version:remote.share",
        variant="1.0",
        stale_in=["FAQ-002"],
    )
    reg.add(
        "remote.workspace_check_months",
        "count",
        "months",
        reg.pick("count", "months", 6, 24, 6),
        "POL-002",
        4,
        "Your home workspace is reviewed with your manager every {value}.",
        ["how often home workspace review"],
        versions=["2.0"],
    )

    # --- POL-003 workation
    reg.add(
        "workation.days",
        "count",
        "working days",
        reg.pin("count", "working days", 30),
        "POL-003",
        2,
        "Workation is limited to {value} per calendar year within the EU/EEA.",
        ["how many workation days", "work from another country"],
    )
    reg.add(
        "workation.max_trip_days",
        "count",
        "calendar days",
        reg.pick("count", "calendar days", 14, 28, 7),
        "POL-003",
        2,
        "A single workation stay may not exceed {value}.",
        ["longest single workation"],
    )

    # --- POL-004 travel (per-diem rates live in FIN-RATES-<year>; POL-004 only references them)
    reg.add(
        "expense.deadline",
        "count",
        "calendar days",
        reg.pin("count", "calendar days", 30),
        "POL-004",
        6,
        "Expense reports are due within {value} after the trip ends.",
        ["expense report deadline"],
        versions=["3.0"],
        family="version:expense.deadline",
        variant="3.0",
    )
    reg.add(
        "expense.deadline",
        "count",
        "calendar days",
        reg.pick("count", "calendar days", 45, 90, 15),
        "POL-004",
        6,
        "Expense reports are due within {value} after the trip ends.",
        ["expense report deadline"],
        versions=["2.0"],
        current=False,
        family="version:expense.deadline",
        variant="2.0",
        stale_in=["FAQ-003"],
    )
    reg.add(
        "travel.train_threshold_hours",
        "count",
        "hours",
        reg.pin("count", "hours", 5),
        "POL-004",
        3,
        "Trains are preferred over flights for routes under {value} door to door.",
        ["when take the train instead of flying"],
        versions=["3.0", "2.0"],
    )
    reg.add(
        "travel.booking_advance_days",
        "count",
        "days",
        reg.pick("count", "days", 7, 21, 7),
        "POL-004",
        3,
        "Trips should be booked at least {value} before departure.",
        ["how early to book travel"],
        versions=["3.0"],
        buried=True,
    )

    # --- POL-005 security
    reg.add(
        "security.training_deadline",
        "count",
        "days",
        reg.pin("count", "days", 14),
        "POL-005",
        3,
        "New hires complete the mandatory security training within {value} of their start date.",
        ["security training deadline new hires"],
        versions=["4.1", "3.0"],
    )
    reg.add(
        "security.password_min_chars",
        "text",
        "",
        f"{reg.pick('count', 'lines', 12, 16, 2)} characters",
        "POL-005",
        2,
        "Passwords must be at least {value} long.",
        ["minimum password length"],
        versions=["4.1"],
        family="version:security.password",
        variant="4.1",
    )
    reg.add(
        "security.password_min_chars",
        "text",
        "",
        f"{reg.pick('count', 'lines', 8, 10, 2)} characters",
        "POL-005",
        2,
        "Passwords must be at least {value} long.",
        ["minimum password length"],
        versions=["3.0"],
        current=False,
        family="version:security.password",
        variant="3.0",
        stale_in=["FAQ-004"],
    )

    # --- POL-006 equipment
    reg.add(
        "equipment.budget_standard",
        "money",
        "",
        reg.pin("money", "", 2200),
        "POL-006",
        3,
        "The equipment budget for a standard role is {value}.",
        ["equipment budget standard role"],
        versions=["2.2"],
        table="equipment_budget",
        row_label="Standard role",
        family="version:equipment.budget_standard",
        variant="2.2",
    )
    reg.add(
        "equipment.budget_standard",
        "money",
        "",
        reg.pick("money", "", 1600, 2000, 100),
        "POL-006",
        3,
        "The equipment budget for a standard role is {value}.",
        ["equipment budget standard role"],
        versions=["1.0"],
        current=False,
        family="version:equipment.budget_standard",
        variant="1.0",
    )
    reg.add(
        "equipment.budget_engineering",
        "money",
        "",
        reg.pin("money", "", 2800),
        "POL-006",
        3,
        "The equipment budget for an engineering role is {value}.",
        ["equipment budget engineers"],
        versions=["2.2"],
        table="equipment_budget",
        row_label="Engineering role",
    )
    reg.add(
        "equipment.refresh_months",
        "count",
        "months",
        reg.pin("count", "months", 36),
        "POL-006",
        4,
        "Equipment is refreshed every {value}.",
        ["how often laptops replaced"],
        versions=["2.2", "1.0"],
    )
    reg.add(
        "equipment.return_days",
        "count",
        "business days",
        reg.pin("count", "business days", 10),
        "POL-006",
        5,
        "Equipment must be returned within {value} after the last working day.",
        ["when return laptop after leaving"],
        versions=["2.2", "1.0"],
    )
    reg.add(
        "equipment.writeoff_threshold",
        "money",
        "",
        reg.pin("money", "", 400),
        "POL-006",
        6,
        "Hardware with a net book value below {value} is written off without a separate approval.",
        ["write-off threshold equipment"],
        versions=["2.2"],
        label="finance",
    )

    # --- POL-007 sick leave
    reg.add(
        "sick.note_day",
        "text",
        "",
        "3rd calendar day",
        "POL-007",
        3,
        "A doctor's certificate is required from the {value} of absence.",
        ["when do I need a sick note"],
    )
    reg.add(
        "sick.full_pay_weeks",
        "count",
        "weeks",
        reg.pick("count", "weeks", 6, 12, 2),
        "POL-007",
        4,
        "Kranich continues full pay for the first {value} of illness.",
        ["how long sick pay full salary"],
    )

    # --- POL-008 parental
    reg.add(
        "parental.carryover_exception",
        "date",
        "",
        "6-30",
        "POL-008",
        7,
        "Employees returning from parental leave may take carried-over vacation until {value}.",
        ["carryover deadline after parental leave"],
        versions=["2.1"],
        buried=True,
        family="version:parental.carryover",
        variant="2.1",
    )
    reg.add(
        "parental.notice_weeks",
        "count",
        "weeks",
        reg.pick("count", "weeks", 6, 10, 1),
        "POL-008",
        3,
        "Please tell People & Culture at least {value} before the planned start of the leave.",
        ["how much notice for parental leave"],
        versions=["2.1", "1.0"],
    )

    # --- POL-009 conduct
    reg.add(
        "conduct.gift_limit",
        "money",
        "",
        reg.pick("money", "", 40, 90, 10),
        "POL-009",
        3,
        "Gifts and hospitality above {value} in value must be declared.",
        ["gift limit declare"],
    )

    # --- POL-010 data protection
    reg.add(
        "privacy.retention_years",
        "count",
        "years",
        reg.pick("count", "years", 3, 7, 1),
        "POL-010",
        3,
        "Applicant data is deleted {value} after the hiring decision.",
        ["how long applicant data kept"],
        versions=["2.0"],
        family="version:privacy.retention",
        variant="2.0",
    )
    reg.add(
        "privacy.retention_years",
        "count",
        "years",
        reg.pick("count", "years", 8, 10, 1),
        "POL-010",
        3,
        "Applicant data is deleted {value} after the hiring decision.",
        ["how long applicant data kept"],
        versions=["1.0", "1.5"],
        current=False,
        family="version:privacy.retention",
        variant="1.0",
    )
    reg.add(
        "privacy.dsar_days",
        "count",
        "calendar days",
        reg.pick("count", "calendar days", 20, 28, 1),
        "POL-010",
        4,
        "Data subject requests are answered within {value}.",
        ["how fast data subject request answered"],
        versions=["2.0", "1.0"],
    )

    # --- POL-011 training
    reg.add(
        "training.budget",
        "money",
        "per year",
        reg.pick("money", "per year", 800, 1500, 100),
        "POL-011",
        2,
        "Every employee has a learning budget of {value}.",
        ["learning budget per year"],
        versions=["2.0"],
        family="version:training.budget",
        variant="2.0",
    )
    reg.add(
        "training.budget",
        "money",
        "per year",
        reg.pick("money", "per year", 400, 700, 100),
        "POL-011",
        2,
        "Every employee has a learning budget of {value}.",
        ["learning budget per year"],
        versions=["1.0", "1.5"],
        current=False,
        family="version:training.budget",
        variant="1.0",
        stale_in=["FAQ-005"],
    )
    reg.add(
        "training.conference_days",
        "count",
        "working days",
        reg.pick("count", "working days", 2, 5, 1),
        "POL-011",
        3,
        "Up to {value} per year may be spent at conferences without using vacation.",
        ["conference days per year"],
        versions=["2.0", "1.0"],
    )

    # --- POL-012 home office
    reg.add(
        "homeoffice.setup_allowance",
        "money",
        "",
        reg.pick("money", "", 300, 600, 50),
        "POL-012",
        2,
        "The one-off home office setup allowance is {value}.",
        ["home office setup allowance"],
    )
    reg.add(
        "homeoffice.internet_allowance",
        "money",
        "per month",
        reg.pick("money", "per month", 20, 40, 5),
        "POL-012",
        3,
        "The connectivity allowance is {value}.",
        ["internet allowance per month"],
    )

    # --- POL-013 working time
    reg.add(
        "worktime.max_weekly_hours",
        "count",
        "hours",
        reg.pick("count", "hours", 44, 48, 1),
        "POL-013",
        2,
        "Working time may not exceed {value} in any week.",
        ["maximum weekly working hours"],
        versions=["2.0", "1.5", "1.0"],
    )
    reg.add(
        "worktime.comp_time_weeks",
        "count",
        "weeks",
        reg.pick("count", "weeks", 8, 12, 1),
        "POL-013",
        3,
        "Overtime is compensated with time off within {value}.",
        ["when must comp time be taken"],
        versions=["2.0"],
        family="version:worktime.comp",
        variant="2.0",
    )
    reg.add(
        "worktime.comp_time_weeks",
        "count",
        "weeks",
        reg.pick("count", "weeks", 13, 16, 1),
        "POL-013",
        3,
        "Overtime is compensated with time off within {value}.",
        ["when must comp time be taken"],
        versions=["1.5"],
        current=False,
        family="version:worktime.comp",
        variant="1.5",
    )
    reg.add(
        "worktime.comp_time_weeks",
        "count",
        "weeks",
        reg.pick("count", "weeks", 17, 26, 1),
        "POL-013",
        3,
        "Overtime is compensated with time off within {value}.",
        ["when must comp time be taken"],
        versions=["1.0"],
        current=False,
        family="version:worktime.comp",
        variant="1.0",
        stale_in=["FAQ-006"],
    )

    # --- POL-014 holidays
    reg.add(
        "holidays.bridge_days",
        "count",
        "days",
        reg.pick("count", "days", 2, 4, 1),
        "POL-014",
        3,
        "Kranich grants {value} of bridge-day leave per year in addition to vacation.",
        ["bridge days per year"],
    )

    # --- POL-015 mobility
    reg.add(
        "mobility.min_tenure_months",
        "count",
        "months",
        reg.pick("count", "months", 12, 18, 3),
        "POL-015",
        2,
        "Internal transfers require at least {value} in the current role.",
        ["minimum tenure internal transfer"],
        versions=["1.1", "1.0"],
    )
    reg.add(
        "mobility.transition_weeks",
        "count",
        "weeks",
        reg.pick("count", "weeks", 5, 7, 1),
        "POL-015",
        4,
        "The transition period between teams is {value}.",
        ["transition period internal move"],
        versions=["1.1"],
        buried=True,
    )

    # --- POL-016 speak-up
    reg.add(
        "speakup.response_days",
        "count",
        "business days",
        reg.pick("count", "business days", 3, 7, 1),
        "POL-016",
        4,
        "Every concern receives a first response within {value}.",
        ["how fast speak-up concern answered"],
    )

    # --- POL-017 corporate cards (finance-restricted limits)
    reg.add(
        "card.transaction_limit",
        "money",
        "",
        reg.pin("money", "", 1500),
        "POL-017",
        5,
        "The single-transaction limit on the corporate card is {value}.",
        ["card single transaction limit"],
        versions=["2.0"],
        label="finance",
        family="version:card.limit",
        variant="2.0",
    )
    reg.add(
        "card.transaction_limit",
        "money",
        "",
        reg.pick("money", "", 800, 1200, 100),
        "POL-017",
        5,
        "The single-transaction limit on the corporate card is {value}.",
        ["card single transaction limit"],
        versions=["1.0"],
        current=False,
        label="finance",
        family="version:card.limit",
        variant="1.0",
    )
    reg.add(
        "card.monthly_cap",
        "money",
        "",
        reg.pick("money", "", 3000, 6000, 500),
        "POL-017",
        5,
        "Monthly spend per card is capped at {value}.",
        ["monthly card cap"],
        versions=["2.0", "1.0"],
        label="finance",
    )

    # --- POL-018 procurement
    reg.add(
        "procurement.manager_threshold",
        "money",
        "",
        reg.pick("money", "", 500, 900, 100),
        "POL-018",
        3,
        "Purchases up to {value} are approved by your manager.",
        ["purchase approval manager threshold"],
        versions=["1.2", "1.0"],
    )
    reg.add(
        "procurement.cfo_threshold",
        "money",
        "",
        reg.pick("money", "", 10000, 25000, 5000),
        "POL-018",
        3,
        "Purchases above {value} require CFO approval.",
        ["purchase approval CFO threshold"],
        versions=["1.2"],
        label="finance",
        family="version:procurement.cfo",
        variant="1.2",
    )
    reg.add(
        "procurement.cfo_threshold",
        "money",
        "",
        reg.pick("money", "", 5000, 8000, 1000),
        "POL-018",
        3,
        "Purchases above {value} require CFO approval.",
        ["purchase approval CFO threshold"],
        versions=["1.0"],
        current=False,
        label="finance",
        family="version:procurement.cfo",
        variant="1.0",
    )

    # --- POL-019 travel insurance
    reg.add(
        "insurance.medical_cover",
        "money",
        "",
        reg.pick("money", "", 50000, 250000, 50000),
        "POL-019",
        2,
        "Medical costs abroad are covered up to {value} per trip.",
        ["travel insurance medical coverage"],
    )
    reg.add(
        "insurance.claim_days",
        "count",
        "calendar days",
        reg.pick("count", "calendar days", 5, 14, 1),
        "POL-019",
        3,
        "Claims must be filed within {value} of the event.",
        ["travel insurance claim deadline"],
    )

    # --- POL-020 meetings
    reg.add(
        "meetings.focus_hours",
        "count",
        "hours",
        reg.pick("count", "hours", 2, 4, 1),
        "POL-020",
        2,
        "Every weekday afternoon holds {value} of company-wide focus time with no meetings.",
        ["focus time hours"],
        versions=["1.1", "1.0"],
    )
    reg.add(
        "meetings.max_attendees",
        "count",
        "people",
        reg.pick("count", "people", 6, 9, 1),
        "POL-020",
        3,
        "Decision meetings are capped at {value}.",
        ["max attendees decision meeting"],
        versions=["1.1"],
        buried=True,
    )

    # --- POL-021 contractors
    reg.add(
        "contractor.max_months",
        "count",
        "months",
        reg.pick("count", "months", 9, 11, 1),
        "POL-021",
        3,
        "A contractor engagement may not exceed {value} without a Legal review.",
        ["maximum contractor engagement length"],
    )

    # --- POL-022 comms
    reg.add(
        "comms.approval_days",
        "count",
        "business days",
        reg.pick("count", "business days", 1, 2, 1),
        "POL-022",
        4,
        "Public content is approved by Go-to-Market within {value}.",
        ["approval time public content"],
        versions=["2.0", "1.0"],
    )

    # --- POL-023 access control
    reg.add(
        "access.review_months",
        "count",
        "months",
        reg.pick("count", "months", 3, 4, 1),
        "POL-023",
        3,
        "Access rights are reviewed every {value}.",
        ["how often access reviews"],
        versions=["2.0"],
        family="version:access.review",
        variant="2.0",
    )
    reg.add(
        "access.review_months",
        "count",
        "months",
        reg.pick("count", "months", 5, 8, 1),
        "POL-023",
        3,
        "Access rights are reviewed every {value}.",
        ["how often access reviews"],
        versions=["1.0"],
        current=False,
        family="version:access.review",
        variant="1.0",
    )
    reg.add(
        "access.revoke_for_cause",
        "text",
        "",
        "1 hour",
        "POL-023",
        4,
        "For a departure for cause, all access is revoked within {value} of the manager's notification.",
        ["how fast access revoked for cause"],
        versions=["2.0", "1.0"],
        label="managers",
    )

    # --- POL-024 vendors
    reg.add(
        "vendor.notice_days",
        "count",
        "days",
        reg.pick("count", "days", 60, 90, 30),
        "POL-024",
        3,
        "Renewals must be reviewed at least {value} before the notice deadline.",
        ["vendor renewal notice"],
    )

    # --- POL-025 performance
    reg.add(
        "perf.calibration_cap",
        "percent",
        "",
        reg.pin("percent", "", 20),
        "POL-025",
        4,
        "No more than {value} of a team's ratings may be 'exceeds expectations'.",
        ["calibration cap exceeds expectations"],
        versions=["2.0"],
        label="managers",
    )
    reg.add(
        "perf.self_review_days",
        "count",
        "working days",
        reg.pick("count", "working days", 4, 7, 1),
        "POL-025",
        2,
        "Self-reviews are due within {value} of the cycle opening.",
        ["self review deadline"],
        versions=["2.0", "1.0"],
    )

    # --- POL-026 benefits
    reg.add(
        "benefits.wellness",
        "money",
        "per month",
        reg.pin("money", "per month", 50),
        "POL-026",
        2,
        "The wellness budget is {value}.",
        ["wellness budget"],
        versions=["3.1", "2.0"],
    )
    reg.add(
        "benefits.hardship_advance",
        "money",
        "",
        reg.pin("money", "", 2000),
        "POL-026",
        4,
        "A hardship advance is limited to {value}.",
        ["hardship advance maximum"],
        versions=["3.1"],
        label="hr",
    )
    reg.add(
        "benefits.hardship_repay_months",
        "count",
        "months",
        reg.pin("count", "months", 12),
        "POL-026",
        4,
        "Hardship advances are repaid through payroll within {value}.",
        ["hardship advance repayment period"],
        versions=["3.1"],
        label="hr",
    )

    # --- POL-027 incidents
    reg.add(
        "incident.report_hours",
        "count",
        "hours",
        reg.pin("count", "hours", 24),
        "POL-027",
        3,
        "Suspected incidents are reported within {value} to security@kranich.example.",
        ["incident report deadline"],
        versions=["1.3", "1.0"],
    )
    reg.add(
        "incident.disclosure_hours",
        "count",
        "hours",
        reg.pin("count", "hours", 48),
        "POL-027",
        5,
        "Leadership decides on customer disclosure within {value} of confirmation.",
        ["customer disclosure decision time"],
        versions=["1.3"],
        label="leadership",
    )

    # --- POL-028 office
    reg.add(
        "office.recurring_slots",
        "count",
        "slots",
        reg.pin("count", "slots", 3),
        "POL-028",
        3,
        "Each person may hold at most {value} of recurring room bookings.",
        ["recurring meeting room bookings"],
    )
    reg.add(
        "office.desk_booking_days",
        "count",
        "days",
        reg.pick("count", "days", 5, 9, 1),
        "POL-028",
        2,
        "Desks can be booked up to {value} ahead in Perch.",
        ["how far ahead book a desk"],
    )

    # --- country handbooks (HB-<CC>) and supplements (HB-S-<CC>)
    vac_values = {"DE": 27, "PT": 22, "ES": 23, "PL": 26, "FR": 25, "UK": 28}
    for cc, name in COUNTRIES.items():
        reg.add(
            "country.vacation_days",
            "count",
            "days",
            reg.pin("count", "days", vac_values[cc]) if cc != "DE" else 27,
            f"HB-{cc}",
            3,
            f"Employees in {name} receive {{value}} of statutory-plus-Kranich vacation per year.",
            [f"vacation days {name}"],
            family="country:vacation_days",
            variant=cc,
        )
        reg.add(
            "country.probation_months",
            "count",
            "months",
            reg.pin("count", "months", 6) if cc == "DE" else reg.pick("count", "months", 1, 9, 1),
            f"HB-{cc}",
            4,
            f"The probation period in {name} is {{value}}.",
            [f"probation period {name}"],
            family="country:probation",
            variant=cc,
        )
        reg.add(
            "country.notice_weeks",
            "count",
            "weeks",
            reg.pick("count", "weeks", 2, 12, 1),
            f"HB-{cc}",
            5,
            f"The contractual notice period in {name} is {{value}}.",
            [f"notice period {name}"],
            family="country:notice",
            variant=cc,
        )
        reg.add(
            "country.public_holidays",
            "count",
            "days",
            reg.pick("count", "days", 8, 15, 1),
            f"HB-{cc}",
            6,
            f"Employees in {name} observe {{value}} of public holidays in the reference year.",
            [f"public holidays {name}"],
            family="country:holidays",
            variant=cc,
        )
        reg.add(
            "country.weekly_hours",
            "text",
            "",
            f"{reg.pick('count', 'hours', 35, 40, 0.5)} hours per week",
            f"HB-{cc}",
            7,
            f"The standard working week in {name} is {{value}}.",
            [f"working hours per week {name}"],
            family="country:weekly_hours",
            variant=cc,
        )
        reg.add(
            "country.hotel_cap",
            "money",
            "per night",
            reg.pick("money", "per night", 90, 200, 5),
            f"HB-S-{cc}",
            3,
            f"The hotel cap for trips in {name} is {{value}}.",
            [f"hotel cap {name}"],
            family="country:hotel_cap",
            variant=cc,
            table="hotel_caps",
            row_label=name,
        )
        reg.add(
            "country.mileage_rate",
            "money",
            "per km",
            reg.pick("money", "per km", 0.2, 0.5, 0.01),
            f"HB-S-{cc}",
            4,
            f"Mileage in a private car in {name} is reimbursed at {{value}}.",
            [f"mileage rate {name}"],
            family="country:mileage",
            variant=cc,
        )

    # --- FIN rate sheets per year: per-diem per country (2026 current; v1 pinned values)
    pinned_2026 = {"DE": 28, "PT": 24, "FR": 32, "UK": 36, "PL": 22, "ES": 26}
    for year in YEARS:
        for cc, name in COUNTRIES.items():
            value = pinned_2026[cc] if year == 2026 else reg.pick("money", "per day", 18, 70, 1)
            if year == 2026:
                reg.pin("money", "per day", value)
            reg.add(
                "perdiem.rate",
                "money",
                "per day",
                value,
                f"FIN-RATES-{year}",
                2,
                f"The {year} per-diem for {name} is {{value}}.",
                [f"per-diem {name} {year}"],
                family=f"year:perdiem.{cc}",
                variant=str(year),
                current=year == 2026,
                table=f"perdiem_{year}",
                row_label=name,
            )
        reg.add(
            "perdiem.partial_day",
            "percent",
            "",
            50,
            f"FIN-RATES-{year}",
            3,
            "Trips under eight hours pay {value} of the country rate.",
            ["per-diem short trips percentage"],
            current=year == 2026,
        )
    reg.pin("percent", "", 50)

    # --- FIN quarterly updates (finance-only)
    for i, q in enumerate(
        ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
    ):
        reg.add(
            "finance.revenue_growth",
            "percent",
            "",
            reg.pick("percent", "", 3, 18, 0.5),
            f"FIN-UPD-{q}",
            2,
            f"Revenue grew {{value}} year over year in {q.replace('-', ' ')}.",
            [f"revenue growth {q}"],
            label="finance",
            family="quarter:revenue_growth",
            variant=q,
            current=i == 7,
        )
    reg.add(
        "finance.invoice_sla_days",
        "count",
        "business days",
        reg.pick("count", "business days", 3, 9, 1),
        "FIN-GUIDE-INVOICES",
        3,
        "Supplier invoices are approved within {value} of receipt.",
        ["invoice approval time"],
    )
    reg.add(
        "finance.budget_variance_alert",
        "percent",
        "",
        reg.pick("percent", "", 5, 15, 1),
        "FIN-GUIDE-BUDGET",
        3,
        "Cost-center owners are alerted when spend deviates by more than {value} from plan.",
        ["budget variance alert threshold"],
        label="finance",
    )

    # --- SEC standards and runbooks
    reg.add(
        "sec.backup_retention_days",
        "count",
        "days",
        reg.pick("count", "days", 35, 120, 5),
        "SEC-STD-BACKUP",
        3,
        "Backups are retained for {value}.",
        ["backup retention"],
    )
    reg.add(
        "sec.log_retention_days",
        "count",
        "days",
        reg.pick("count", "days", 180, 400, 10),
        "SEC-STD-LOGGING",
        3,
        "Security logs are kept for {value}.",
        ["log retention period"],
    )
    reg.add(
        "sec.session_max_hours",
        "count",
        "hours",
        reg.pick("count", "hours", 8, 16, 1),
        "SEC-STD-IDENTITY",
        3,
        "SSO sessions expire after {value}.",
        ["session timeout"],
    )
    reg.add(
        "sec.patch_days",
        "count",
        "calendar days",
        reg.pick("count", "calendar days", 10, 21, 1),
        "SEC-STD-ENDPOINT",
        4,
        "Critical patches are installed within {value} of release.",
        ["patch deadline critical"],
    )
    reg.add(
        "sec.lost_device_hours",
        "count",
        "hours",
        reg.pick("count", "hours", 2, 6, 1),
        "SEC-RB-LOSTDEVICE",
        2,
        "A lost or stolen device is reported within {value}.",
        ["lost laptop report time"],
    )
    reg.add(
        "sec.password_reset_minutes",
        "count",
        "minutes",
        reg.pick("count", "minutes", 20, 45, 5),
        "SEC-RB-ACCESS",
        3,
        "IT resets a locked account within {value} during business hours.",
        ["how fast password reset"],
    )
    for i in range(1, 7):
        reg.add(
            "sec.postmortem_downtime",
            "count",
            "minutes",
            reg.pick("count", "minutes", 50, 400, 5),
            f"SEC-PM-{i:02d}",
            2,
            "The incident caused {value} of customer-facing downtime.",
            [f"downtime postmortem {i}"],
            label="managers",
            family="postmortem:downtime",
            variant=str(i),
        )
    for i in (2, 5):
        reg.add(
            "sec.postmortem_credit",
            "percent",
            "",
            reg.pick("percent", "", 2, 12, 1),
            f"SEC-PM-{i:02d}",
            5,
            "Affected customers received a service credit of {value} of the monthly fee.",
            [f"service credit postmortem {i}"],
            label="leadership",
            family="postmortem:credit",
            variant=str(i),
        )

    # --- ENG
    reg.add(
        "eng.api_rate_limit",
        "count",
        "requests per minute",
        reg.pick("count", "requests per minute", 300, 1200, 100),
        "ENG-RFC-01",
        3,
        "The public API is limited to {value} per API key.",
        ["API rate limit"],
    )
    reg.add(
        "eng.p95_latency",
        "count",
        "ms",
        reg.pick("count", "ms", 150, 400, 10),
        "ENG-RFC-02",
        2,
        "The route-planning endpoint targets a p95 latency of {value}.",
        ["p95 latency target"],
    )
    reg.add(
        "eng.event_retention_days",
        "count",
        "days",
        reg.pick("count", "days", 14, 60, 2),
        "ENG-RFC-03",
        3,
        "Telemetry events are retained for {value}.",
        ["telemetry retention"],
    )
    reg.add(
        "eng.max_payload_gb",
        "count",
        "GB",
        reg.pick("count", "GB", 2, 10, 1),
        "ENG-RFC-04",
        3,
        "Bulk imports are capped at {value} per file.",
        ["bulk import size limit"],
    )
    reg.add(
        "eng.oncall_response_minutes",
        "count",
        "minutes",
        reg.pick("count", "minutes", 10, 15, 1),
        "ENG-GUIDE-ONCALL",
        2,
        "The on-call engineer acknowledges a page within {value}.",
        ["on-call acknowledge time"],
    )
    reg.add(
        "eng.release_freeze_days",
        "count",
        "days",
        reg.pick("count", "days", 2, 4, 1),
        "ENG-GUIDE-RELEASE",
        3,
        "A release freeze starts {value} before a major customer go-live.",
        ["release freeze length"],
    )
    reg.add(
        "eng.pr_max_lines",
        "count",
        "lines",
        reg.pick("count", "lines", 300, 600, 50),
        "ENG-GUIDE-REVIEW",
        2,
        "Pull requests above {value} are split before review.",
        ["max PR size"],
    )
    for i, team in enumerate(TEAMS, start=1):
        reg.add(
            "eng.team_headcount",
            "count",
            "people",
            reg.pick("count", "people", 10, 40, 1),
            f"ENG-TEAM-{i:02d}",
            2,
            f"{team} currently has {{value}}.",
            [f"how many people {team}"],
            family="team:headcount",
            variant=team,
        )
    adr_topics = {
        1: (
            "days",
            121,
            179,
            "cache TTL for tenant settings",
            "Tenant settings are cached for {value}.",
        ),
        2: (
            "minutes",
            20,
            45,
            "cold-start budget for batch jobs",
            "Batch jobs must finish their cold start within {value}.",
        ),
        3: (
            "days",
            181,
            240,
            "staging data snapshot retention",
            "Staging snapshots are kept for {value}.",
        ),
        4: (
            "minutes",
            46,
            90,
            "build pipeline time budget",
            "The full pipeline must finish within {value}.",
        ),
        5: (
            "days",
            241,
            300,
            "feature-flag cleanup window",
            "Stale feature flags are removed after {value}.",
        ),
        6: (
            "minutes",
            91,
            180,
            "database migration lock timeout",
            "Migrations abort after holding a lock for {value}.",
        ),
        7: ("days", 301, 360, "map tile cache lifetime", "Map tiles are cached for {value}."),
        8: (
            "hours",
            50,
            96,
            "vendor SLA escalation window",
            "Vendor tickets escalate after {value}.",
        ),
    }
    for i, (unit, lo, hi, hint, statement) in adr_topics.items():
        reg.add(
            f"eng.adr{i:02d}",
            "count",
            unit,
            reg.pick("count", unit, lo, hi, 1),
            f"ENG-ADR-{i:02d}",
            3,
            statement,
            [hint],
        )

    # --- OPS
    reg.add(
        "ops.event_budget",
        "money",
        "",
        reg.pick("money", "", 25, 60, 5),
        "OPS-EVENTS",
        2,
        "Team events are budgeted at {value} per person.",
        ["team event budget per person"],
    )
    reg.add(
        "ops.visitor_notice_hours",
        "count",
        "hours",
        reg.pick("count", "hours", 18, 30, 1),
        "OPS-VISITORS",
        2,
        "Visitors are registered in Perch at least {value} ahead.",
        ["visitor registration notice"],
    )
    reg.add(
        "ops.parking_spaces",
        "count",
        "spaces",
        reg.pick("count", "spaces", 4, 12, 1),
        "OPS-BERLIN",
        5,
        "The Berlin office has {value} for visitors and deliveries.",
        ["parking spaces Berlin"],
    )
    reg.add(
        "ops.lisbon_desks",
        "count",
        "people",
        reg.pick("count", "people", 20, 40, 1),
        "OPS-LISBON",
        2,
        "The Lisbon office seats {value}.",
        ["how many desks Lisbon"],
    )

    # --- EXEC
    reg.add(
        "exec.headcount",
        "count",
        "people",
        reg.pick("count", "people", 130, 150, 1),
        "EXEC-AH-06",
        2,
        "Kranich now has {value}.",
        ["current headcount"],
    )
    reg.add(
        "exec.nps",
        "text",
        "",
        f"{reg.pick('count', 'lines', 40, 65, 1)} points",
        "EXEC-AH-04",
        3,
        "Customer NPS reached {value} in the last survey.",
        ["customer NPS"],
    )
    for i in range(1, 5):
        reg.add(
            "exec.okr_target",
            "percent",
            "",
            reg.pick("percent", "", 20, 60, 5),
            f"EXEC-OKR-{i:02d}",
            2,
            "The key result targets {value} growth in active fleets.",
            [f"OKR target {i}"],
            label="managers",
            family="okr:target",
            variant=str(i),
        )
    for i in range(1, 6):
        reg.add(
            "exec.arr_growth",
            "percent",
            "",
            reg.pick("percent", "", 15, 45, 1),
            f"EXEC-BOARD-{i:02d}",
            2,
            "ARR grew {value} year over year.",
            [f"ARR growth board memo {i}"],
            label="leadership",
            family="board:arr",
            variant=str(i),
        )
        reg.add(
            "exec.runway_months",
            "count",
            "months",
            reg.pick("count", "months", 18, 40, 1),
            f"EXEC-BOARD-{i:02d}",
            3,
            "Cash runway stands at {value}.",
            [f"cash runway board memo {i}"],
            label="leadership",
            family="board:runway",
            variant=str(i),
        )
    reg.add(
        "exec.band_senior_engineer",
        "text",
        "",
        "€78,000–€96,000",
        "EXEC-COMP",
        2,
        "The Senior Engineer band in Berlin is {value}.",
        ["salary band senior engineer"],
        label="leadership",
        table="comp_bands",
        row_label="Senior Engineer",
    )
    reg.add(
        "exec.band_eng_manager",
        "text",
        "",
        "€92,000–€115,000",
        "EXEC-COMP",
        2,
        "The Engineering Manager band in Berlin is {value}.",
        ["salary band engineering manager"],
        label="leadership",
        table="comp_bands",
        row_label="Engineering Manager",
    )
    reg.add(
        "exec.band_pm",
        "text",
        "",
        "€70,000–€88,000",
        "EXEC-COMP",
        2,
        "The Product Manager band in Berlin is {value}.",
        ["salary band product manager"],
        label="leadership",
        table="comp_bands",
        row_label="Product Manager",
    )
    reg.add(
        "exec.review_budget",
        "percent",
        "",
        reg.pin("percent", "", 3.5),
        "EXEC-COMP",
        3,
        "The annual salary review budget is {value} of total payroll.",
        ["salary review budget"],
        label="leadership",
    )

    # --- meeting decisions (as-of-date pairs): earlier meeting states an old value, later one changes it
    decisions = [
        (
            "mtg.oncall_rotation_days",
            "count",
            "days",
            (5, 9),
            (16, 21),
            "On-call rotations last {value}.",
            "on-call rotation length",
        ),
        (
            "mtg.standup_minutes",
            "count",
            "minutes",
            (16, 19),
            (10, 14),
            "Daily standups are capped at {value}.",
            "standup length",
        ),
        (
            "mtg.deploy_window_hours",
            "count",
            "hours",
            (1, 3),
            (4, 7),
            "The deploy window is {value} per day.",
            "deploy window",
        ),
    ]
    for i, (key, kind, unit, old_range, new_range, statement, hint) in enumerate(
        decisions, start=1
    ):
        reg.add(
            key,
            kind,
            unit,
            reg.pick(kind, unit, *old_range),
            f"MTG-{2 * i - 1:02d}",
            3,
            statement,
            [hint],
            current=False,
            family=f"meeting:{key}",
            variant="earlier",
        )
        reg.add(
            key,
            kind,
            unit,
            reg.pick(kind, unit, *new_range),
            f"MTG-{2 * i:02d}",
            3,
            statement,
            [hint],
            family=f"meeting:{key}",
            variant="later",
        )

    # --- PUB
    reg.add(
        "pub.uptime_sla",
        "percent",
        "",
        reg.pick("percent", "", 99.5, 99.95, 0.05),
        "PUB-SLA",
        2,
        "Kranich Route Cloud commits to {value} monthly uptime.",
        ["uptime SLA"],
    )
    reg.add(
        "pub.support_response_hours",
        "count",
        "hours",
        reg.pick("count", "hours", 1, 4, 1),
        "PUB-SUPPORT",
        2,
        "Priority-1 tickets receive a first response within {value}.",
        ["support response time P1"],
    )
    reg.add(
        "pub.api_key_validity_days",
        "count",
        "days",
        reg.pick("count", "days", 200, 400, 5),
        "PUB-API",
        3,
        "API keys expire after {value} unless rotated.",
        ["API key validity"],
    )


# ---------------------------------------------------------------- documents


def _fmt(base: str, family: str) -> str:
    if family in ("MTG", "FAQ", "ANN"):
        return "md"
    if family in ("HR",) and base.endswith(("2", "7")):
        return "docx"
    if family == "ENG" and base.endswith(("3", "8")):
        return "docx"
    return "pdf"


def build_docs(reg: Registry) -> list[Doc]:  # noqa: PLR0915
    docs: list[Doc] = []
    by_doc: dict[str, list[Fact]] = {}
    for f in reg.facts:
        by_doc.setdefault(f.doc, []).append(f)

    def facts_for(base: str, version: str | None) -> list[str]:
        out = []
        for f in by_doc.get(base, []):
            if version is None or not f.versions or version in f.versions:
                out.append(f.id)
        return out

    # policies with versions
    for base, title, owner, versions, sections in POLICIES:
        for i, (version, effective) in enumerate(versions):
            current = i == len(versions) - 1
            doc_id = f"{base}-v{version}"
            restricted: dict[int, str] = {}
            for fid in facts_for(base, version):
                f = next(x for x in reg.facts if x.id == fid)
                if f.label != "all":
                    restricted[f.section] = f.label
            notes = []
            if not current:
                notes.append(
                    "This is a SUPERSEDED version: write it as the policy read at its effective date, "
                    "with no reference to later versions and no hint that anything changed."
                )
                if i % 2 == 0:
                    notes.append("Do NOT add a 'superseded' banner.")
                else:
                    notes.append(
                        f"Add a one-line note under the title: 'Superseded by version {versions[i + 1][0]}.'"
                    )
            else:
                if len(versions) > 1 and base not in ("POL-013", "POL-023"):
                    notes.append(
                        f"State in §1 that this version supersedes version {versions[i - 1][0]}."
                    )
            docs.append(
                Doc(
                    doc_id=doc_id,
                    base=base,
                    family="POL",
                    title=title,
                    version=version,
                    effective_date=effective,
                    owner=owner,
                    lang="en",
                    words=(800, 1200),
                    sections=sections,
                    restricted=restricted,
                    facts=facts_for(base, version),
                    supersedes=f"{base} v{versions[i - 1][0]}" if i > 0 else None,
                    superseded_by=f"{base} v{versions[i + 1][0]}" if not current else None,
                    notes=notes,
                    format=_fmt(base, "POL"),
                )
            )

    # cross references: POL-004 mentions the rate sheet; POL-006 mentions procurement thresholds; etc.
    mention_map = {
        "POL-004": [
            (
                "perdiem.rate",
                "FIN-RATES-2026",
                "per-diem rates are maintained in the current Expense Rates sheet (FIN-RATES-2026); quote no numbers",
            )
        ],
        "POL-017": [
            (
                "expense.deadline",
                "POL-004",
                "the expense deadline is defined in POL-004 §6; do not quote it",
            )
        ],
        "POL-018": [
            (
                "card.transaction_limit",
                "POL-017",
                "card limits are defined in POL-017 §5; do not quote them",
            )
        ],
        "POL-023": [
            (
                "equipment.return_days",
                "POL-006",
                "equipment return is governed by POL-006 §5; do not quote the number",
            )
        ],
        "POL-027": [
            (
                "sec.lost_device_hours",
                "SEC-RB-LOSTDEVICE",
                "lost devices follow the runbook SEC-RB-LOSTDEVICE; do not quote its deadline",
            )
        ],
        "POL-012": [
            (
                "equipment.budget_standard",
                "POL-006",
                "the equipment budget itself is in POL-006 §3; do not quote it",
            )
        ],
        "POL-025": [
            (
                "training.budget",
                "POL-011",
                "the learning budget is set in POL-011 §2; do not quote it",
            )
        ],
        "POL-003": [
            (
                "remote.share",
                "POL-002",
                "remote work within your country is governed by POL-002; do not quote its percentage",
            )
        ],
        "POL-019": [
            (
                "expense.deadline",
                "POL-004",
                "claims are reimbursed through the expense process in POL-004; do not quote its deadline",
            )
        ],
        "POL-028": [
            (
                "ops.visitor_notice_hours",
                "OPS-VISITORS",
                "guest registration is described in OPS-VISITORS; do not quote the notice period",
            )
        ],
    }
    fact_by_key_current = {f.key: f for f in reg.facts if f.current}
    for d in docs:
        if d.base in mention_map and d.superseded_by is None:
            for key, ref, note in mention_map[d.base]:
                f = fact_by_key_current.get(key)
                if f:
                    d.mentions.append({"fact": f.id, "ref": ref, "note": note})

    # country handbooks and supplements
    for cc, name in COUNTRIES.items():
        docs.append(
            Doc(
                doc_id=f"HB-{cc}",
                base=f"HB-{cc}",
                family="HB",
                title=f"Employee Handbook — {name}",
                version="2026",
                effective_date="2026-01-01",
                owner="People & Culture",
                lang="en",
                words=(2500, 3800),
                sections=[
                    "Welcome",
                    "Your employment in " + name,
                    "Vacation",
                    "Probation",
                    "Notice periods",
                    "Public holidays",
                    "Working hours",
                    "Sick leave basics",
                    "Remote work in " + name,
                    "Benefits in " + name,
                    "Payroll and taxes",
                    "Useful contacts",
                ],
                facts=facts_for(f"HB-{cc}", None),
                mentions=[
                    {
                        "fact": fact_by_key_current["sick.note_day"].id,
                        "ref": "POL-007",
                        "note": "sick-note rules are in POL-007; do not quote the day",
                    }
                ],
                notes=[
                    "Same structure as the other country handbooks; the numbers differ per country. "
                    "Never mention another country's figures."
                ],
            )
        )
        docs.append(
            Doc(
                doc_id=f"HB-S-{cc}",
                base=f"HB-S-{cc}",
                family="HB-S",
                title=f"Travel Supplement — {name}",
                version="2026",
                effective_date="2026-01-01",
                owner="Finance",
                lang="en",
                words=(300, 500),
                sections=["Purpose", "Per-diem", "Hotel cap", "Mileage", "Questions"],
                facts=facts_for(f"HB-S-{cc}", None),
                mentions=[
                    {
                        "fact": next(
                            f.id
                            for f in reg.facts
                            if f.family == f"year:perdiem.{cc}" and f.current
                        ),
                        "ref": "FIN-RATES-2026",
                        "note": "the per-diem for this country is in FIN-RATES-2026; do not quote it",
                    }
                ],
                notes=["Present the hotel cap as a small markdown table with one row."],
            )
        )

    # HR guides
    hr_titles = [
        (f"HR-ONB-{i:02d}", f"Onboarding Guide — {team}") for i, team in enumerate(TEAMS, start=1)
    ]
    hr_titles += [
        ("HR-OFFB", "Offboarding Checklist"),
        ("HR-REVIEW", "Performance Review Process Guide"),
        ("HR-PROMO", "Promotion Process"),
        ("HR-LEAVE", "Leave Administration Guide"),
        ("HR-DISC", "Disciplinary Procedure"),
        ("HR-GRIEV", "Grievance Procedure"),
        ("HR-COMPREV", "Compensation Review Process"),
        ("HR-BGCHECK", "Background Checks"),
        ("HR-INTERV", "Interview Guide"),
        ("HR-JOBLEVELS", "Job Levels Framework"),
        ("HR-1ON1", "1:1 Meetings Guide"),
        ("HR-FEEDBACK", "Giving Feedback"),
        ("HR-REMOTEMGR", "Managing Remote Teams"),
        ("HR-WELLBEING", "Wellbeing Resources"),
        ("HR-EXIT", "Exit Interview Guide"),
        ("HR-PARENTS", "Guide for New Parents"),
        ("HR-PROBATION", "Probation Reviews"),
        ("HR-FLEX", "Flexible Working Requests"),
        ("HR-HOLIDAYS", "Holiday Calendar Guide"),
    ]
    hr_restricted = {
        "HR-DISC": "managers",
        "HR-COMPREV": "hr",
        "HR-BGCHECK": "hr",
        "HR-INTERV": "managers",
        "HR-PROBATION": "managers",
        "HR-EXIT": "hr",
    }
    for base, title in hr_titles:
        mentions = []
        if base.startswith("HR-ONB"):
            mentions.append(
                {
                    "fact": fact_by_key_current["security.training_deadline"].id,
                    "ref": "POL-005",
                    "note": "security training deadline: see §3 of POL-005; do not quote it",
                }
            )
            mentions.append(
                {
                    "fact": fact_by_key_current["equipment.budget_engineering"].id,
                    "ref": "POL-006",
                    "note": "equipment budget: see POL-006 §3; do not quote it",
                }
            )
        if base == "HR-OFFB":
            mentions.append(
                {
                    "fact": fact_by_key_current["equipment.return_days"].id,
                    "ref": "POL-006",
                    "note": "return deadline: see POL-006 §5; do not quote it",
                }
            )
            mentions.append(
                {
                    "fact": fact_by_key_current["access.revoke_for_cause"].id,
                    "ref": "POL-023",
                    "note": "for-cause access revocation: see POL-023 §4 (manager-only); do not quote it",
                }
            )
        if base == "HR-LEAVE":
            mentions.append(
                {
                    "fact": fact_by_key_current["parental.carryover_exception"].id,
                    "ref": "POL-008",
                    "note": "the parental carryover exception lives in POL-008 §7; do not quote the date",
                }
            )
        if base == "HR-PARENTS":
            mentions.append(
                {
                    "fact": fact_by_key_current["parental.notice_weeks"].id,
                    "ref": "POL-008",
                    "note": "notice period for parental leave: see POL-008 §3; do not quote it",
                }
            )
        docs.append(
            Doc(
                doc_id=base,
                base=base,
                family="HR",
                title=title,
                version="1.0",
                effective_date="2025-06-01",
                owner="People & Culture",
                lang="en",
                words=(600, 1000),
                sections=[
                    "Purpose",
                    "Before you start",
                    "Step by step",
                    "Common questions",
                    "Contacts",
                ]
                if base.startswith("HR-ONB")
                else ["Purpose", "Who this is for", "Process", "Timelines", "Questions"],
                default_label=hr_restricted.get(base, "all"),
                facts=facts_for(base, None),
                mentions=mentions,
                format=_fmt(base, "HR"),
            )
        )

    # FIN
    for year in YEARS:
        docs.append(
            Doc(
                doc_id=f"FIN-RATES-{year}",
                base=f"FIN-RATES-{year}",
                family="FIN",
                title=f"Expense Rates & Per-Diems {year}",
                version=str(year),
                effective_date=f"{year}-01-01",
                owner="Finance",
                lang="en",
                words=(400, 700),
                sections=[
                    "Purpose",
                    "Per-diem rates by country",
                    "Partial travel days",
                    "Meals provided by others",
                    "Questions",
                ],
                facts=facts_for(f"FIN-RATES-{year}", None),
                notes=[
                    f"This is the {year} sheet. "
                    + (
                        "It is the current sheet."
                        if year == 2026
                        else f"It is a historical sheet; write it as valid for {year} only, no reference to later sheets."
                    )
                ],
            )
        )
    for base, title, sections in [
        (
            "FIN-GUIDE-PROCURE",
            "Procurement How-To",
            ["Purpose", "Raising a request", "Approvals", "Suppliers", "Questions"],
        ),
        (
            "FIN-GUIDE-BUDGET",
            "Budget Guidelines",
            ["Purpose", "Planning cycle", "Variance monitoring", "Reforecasts", "Questions"],
        ),
        (
            "FIN-GUIDE-CARDS",
            "Corporate Card How-To",
            ["Purpose", "Getting a card", "Everyday use", "Reconciliation", "Questions"],
        ),
        (
            "FIN-GUIDE-EXPENSES",
            "Expense Reports FAQ",
            ["Purpose", "Submitting", "Receipts", "Timelines", "Questions"],
        ),
        (
            "FIN-GUIDE-INVOICES",
            "Supplier Invoice Approval",
            ["Purpose", "Receiving invoices", "Approval SLA", "Payment runs", "Questions"],
        ),
        (
            "FIN-GUIDE-COSTCENTERS",
            "Cost Center Guide",
            ["Purpose", "Structure", "Owners", "Questions"],
        ),
        (
            "FIN-GUIDE-TRAVELBOOK",
            "Travel Booking How-To",
            ["Purpose", "Ledgerly travel module", "Rail and flights", "Hotels", "Questions"],
        ),
        (
            "FIN-GUIDE-YEAREND",
            "Year-End Close Guide",
            ["Purpose", "Timeline", "What we need from you", "Questions"],
        ),
    ]:
        mentions = []
        if base == "FIN-GUIDE-PROCURE":
            mentions.append(
                {
                    "fact": fact_by_key_current["procurement.manager_threshold"].id,
                    "ref": "POL-018",
                    "note": "thresholds live in POL-018 §3; do not quote them",
                }
            )
        if base == "FIN-GUIDE-CARDS":
            mentions.append(
                {
                    "fact": fact_by_key_current["card.transaction_limit"].id,
                    "ref": "POL-017",
                    "note": "limits live in POL-017 §5 (Finance-only); do not quote them",
                }
            )
        if base == "FIN-GUIDE-EXPENSES":
            mentions.append(
                {
                    "fact": fact_by_key_current["expense.deadline"].id,
                    "ref": "POL-004",
                    "note": "the deadline is in POL-004 §6; do not quote it",
                }
            )
        if base == "FIN-GUIDE-TRAVELBOOK":
            mentions.append(
                {
                    "fact": fact_by_key_current["travel.train_threshold_hours"].id,
                    "ref": "POL-004",
                    "note": "the rail-over-flight rule is in POL-004 §3; do not quote the hours",
                }
            )
        restricted = {}
        for fid in facts_for(base, None):
            f = next(x for x in reg.facts if x.id == fid)
            if f.label != "all":
                restricted[f.section] = f.label
        docs.append(
            Doc(
                doc_id=base,
                base=base,
                family="FIN",
                title=title,
                version="1.0",
                effective_date="2025-03-01",
                owner="Finance",
                lang="en",
                words=(500, 800),
                sections=sections,
                facts=facts_for(base, None),
                mentions=mentions,
                restricted=restricted,
            )
        )
    for q in [
        "2024-Q1",
        "2024-Q2",
        "2024-Q3",
        "2024-Q4",
        "2025-Q1",
        "2025-Q2",
        "2025-Q3",
        "2025-Q4",
    ]:
        docs.append(
            Doc(
                doc_id=f"FIN-UPD-{q}",
                base=f"FIN-UPD-{q}",
                family="FIN",
                title=f"Finance Update {q.replace('-', ' ')}",
                version="1.0",
                effective_date=f"{q[:4]}-{int(q[-1]) * 3:02d}-28",
                owner="Finance",
                lang="en",
                words=(400, 600),
                sections=["Summary", "Revenue", "Costs", "Outlook"],
                default_label="finance",
                facts=facts_for(f"FIN-UPD-{q}", None),
                notes=[
                    "Finance-only quarterly update; mention no figures other than the one assigned."
                ],
            )
        )

    # SEC / IT
    sec_docs = [
        (
            "SEC-STD-PASSWORD",
            "Password Standard",
            ["Purpose", "Requirements", "Managers and vaults", "Questions"],
            "all",
        ),
        (
            "SEC-STD-ENDPOINT",
            "Endpoint Security Standard",
            ["Purpose", "Baseline", "Encryption", "Patching", "Questions"],
            "all",
        ),
        (
            "SEC-STD-CLOUD",
            "Cloud Security Standard",
            ["Purpose", "Accounts", "Network", "Secrets", "Questions"],
            "all",
        ),
        (
            "SEC-STD-DATACLASS",
            "Data Classification Standard",
            ["Purpose", "Classes", "Handling rules", "Questions"],
            "all",
        ),
        (
            "SEC-STD-BACKUP",
            "Backup Standard",
            ["Purpose", "What is backed up", "Retention", "Restore tests", "Questions"],
            "all",
        ),
        (
            "SEC-STD-LOGGING",
            "Logging & Monitoring Standard",
            ["Purpose", "What we log", "Retention", "Alerting", "Questions"],
            "all",
        ),
        (
            "SEC-STD-IDENTITY",
            "Identity & SSO Standard",
            ["Purpose", "SSO", "Sessions", "MFA", "Questions"],
            "all",
        ),
        (
            "SEC-STD-VENDOR",
            "Vendor Security Assessment",
            ["Purpose", "When to assess", "Questionnaire", "Questions"],
            "all",
        ),
        (
            "SEC-RB-INCIDENT",
            "Incident Response Runbook",
            ["Purpose", "Report", "Contain", "Escalate", "After", "Contacts"],
            "all",
        ),
        (
            "SEC-RB-PHISHING",
            "Phishing Runbook",
            ["Purpose", "Spotting phishing", "What to do", "Questions"],
            "all",
        ),
        (
            "SEC-RB-LOSTDEVICE",
            "Lost or Stolen Device Runbook",
            ["Purpose", "Report", "Remote wipe", "Replacement", "Questions"],
            "all",
        ),
        (
            "SEC-RB-ACCESS",
            "Access Requests Runbook",
            ["Purpose", "Requesting access", "Locked accounts", "Reviews", "Questions"],
            "all",
        ),
        (
            "SEC-RB-OFFB",
            "Security Offboarding Runbook",
            ["Purpose", "Checklist", "Timing", "Questions"],
            "managers",
        ),
        (
            "SEC-RB-VULN",
            "Vulnerability Handling Runbook",
            ["Purpose", "Intake", "Triage", "Fix windows", "Questions"],
            "all",
        ),
        ("SEC-AUP", "Acceptable Use Policy", ["Purpose", "Do", "Don't", "Questions"], "all"),
        (
            "SEC-AUP-AI",
            "Acceptable Use of AI Tools",
            ["Purpose", "Allowed tools", "What never goes in", "Questions"],
            "all",
        ),
        (
            "SEC-TRAIN",
            "Security Awareness Programme",
            ["Purpose", "Modules", "Cadence", "Questions"],
            "all",
        ),
        (
            "SEC-DR",
            "Disaster Recovery Overview",
            ["Purpose", "Objectives", "Roles", "Questions"],
            "all",
        ),
    ]
    for base, title, sections, label in sec_docs:
        mentions = []
        if base == "SEC-STD-PASSWORD":
            mentions.append(
                {
                    "fact": fact_by_key_current["security.password_min_chars"].id,
                    "ref": "POL-005",
                    "note": "the minimum length is set in POL-005 §2; do not quote it",
                }
            )
        if base == "SEC-RB-INCIDENT":
            mentions.append(
                {
                    "fact": fact_by_key_current["incident.report_hours"].id,
                    "ref": "POL-027",
                    "note": "the reporting deadline is in POL-027 §3; do not quote it",
                }
            )
        if base == "SEC-RB-OFFB":
            mentions.append(
                {
                    "fact": fact_by_key_current["access.revoke_for_cause"].id,
                    "ref": "POL-023",
                    "note": "the for-cause revocation window is in POL-023 §4; do not quote it",
                }
            )
        if base == "SEC-TRAIN":
            mentions.append(
                {
                    "fact": fact_by_key_current["security.training_deadline"].id,
                    "ref": "POL-005",
                    "note": "the new-hire deadline is in POL-005 §3; do not quote it",
                }
            )
        docs.append(
            Doc(
                doc_id=base,
                base=base,
                family="SEC",
                title=title,
                version="1.0",
                effective_date="2025-09-01",
                owner="Information Security",
                lang="en",
                words=(500, 900) if not base.startswith("SEC-STD") else (900, 1600),
                sections=sections,
                default_label=label,
                facts=facts_for(base, None),
                mentions=mentions,
            )
        )
    for i in range(1, 7):
        restricted = {}
        for fid in facts_for(f"SEC-PM-{i:02d}", None):
            f = next(x for x in reg.facts if x.id == fid)
            restricted[f.section] = f.label
        docs.append(
            Doc(
                doc_id=f"SEC-PM-{i:02d}",
                base=f"SEC-PM-{i:02d}",
                family="SEC",
                title=f"Postmortem — Incident {2024 + i // 4}-{i:02d}",
                version="1.0",
                effective_date=f"{2024 + i // 4}-{(i * 2) % 12 + 1:02d}-15",
                owner="Information Security",
                lang="en",
                words=(600, 900),
                sections=[
                    "Summary",
                    "Impact",
                    "Timeline",
                    "Root cause",
                    "Customer communication",
                    "Actions",
                ],
                default_label="managers",
                facts=facts_for(f"SEC-PM-{i:02d}", None),
                restricted=restricted,
                notes=[
                    "A blameless postmortem of a fictional incident (a routing outage, a queue backlog, "
                    "an expired certificate…); invent no numbers beyond the assigned ones — describe "
                    "durations in words otherwise."
                ],
            )
        )

    # ENG
    for i in range(1, 11):
        docs.append(
            Doc(
                doc_id=f"ENG-RFC-{i:02d}",
                base=f"ENG-RFC-{i:02d}",
                family="ENG",
                title=f"RFC-{i:02d}: "
                + [
                    "Public API rate limiting",
                    "Route planning latency budget",
                    "Telemetry pipeline",
                    "Bulk import service",
                    "Tenant isolation model",
                    "Feature flag platform",
                    "Map tile caching",
                    "Event schema versioning",
                    "Background job scheduler",
                    "Search over fleet documents",
                ][i - 1],
                version="1.0",
                effective_date=f"2025-{i:02d}-10",
                owner="Platform & Infrastructure",
                lang="en",
                words=(700, 1200),
                sections=[
                    "Context",
                    "Proposal",
                    "Details",
                    "Alternatives considered",
                    "Rollout",
                    "Open questions",
                ],
                facts=facts_for(f"ENG-RFC-{i:02d}", None),
                format=_fmt(f"ENG-RFC-{i:02d}", "ENG"),
                notes=[
                    "Technical prose for engineers; invent no numeric targets beyond the assigned facts."
                ],
            )
        )
    for i in range(1, 9):
        docs.append(
            Doc(
                doc_id=f"ENG-ADR-{i:02d}",
                base=f"ENG-ADR-{i:02d}",
                family="ENG",
                title=f"ADR-{i:02d}: "
                + [
                    "Tenant settings cache",
                    "Batch job cold starts",
                    "Staging snapshots",
                    "Pipeline time budget",
                    "Feature flag hygiene",
                    "Migration lock timeouts",
                    "Tile cache lifetime",
                    "Vendor escalation",
                ][i - 1],
                version="1.0",
                effective_date=f"2025-{(i % 12) + 1:02d}-20",
                owner="Platform & Infrastructure",
                lang="en",
                words=(400, 700),
                sections=["Status", "Context", "Decision", "Consequences"],
                facts=facts_for(f"ENG-ADR-{i:02d}", None),
                format=_fmt(f"ENG-ADR-{i:02d}", "ENG"),
            )
        )
    for base, title, sections in [
        (
            "ENG-GUIDE-ONCALL",
            "On-Call Guide",
            ["Purpose", "Acknowledging pages", "Escalation", "Handover", "Questions"],
        ),
        (
            "ENG-GUIDE-RELEASE",
            "Release Process",
            ["Purpose", "Cadence", "Freeze windows", "Rollback", "Questions"],
        ),
        (
            "ENG-GUIDE-REVIEW",
            "Code Review Guide",
            ["Purpose", "Size and scope", "Reviewing", "Merging", "Questions"],
        ),
        (
            "ENG-GUIDE-INCIDENTS",
            "Engineering Incident Guide",
            ["Purpose", "Severity", "Roles", "Retros", "Questions"],
        ),
        (
            "ENG-GUIDE-TESTING",
            "Testing Standards",
            ["Purpose", "Unit and integration", "Fixtures", "Questions"],
        ),
        (
            "ENG-GUIDE-OBSERV",
            "Observability Guide",
            ["Purpose", "Metrics", "Tracing", "Dashboards", "Questions"],
        ),
        (
            "ENG-GUIDE-LOCALDEV",
            "Local Development Setup",
            ["Purpose", "Prerequisites", "Running services", "Questions"],
        ),
    ]:
        docs.append(
            Doc(
                doc_id=base,
                base=base,
                family="ENG",
                title=title,
                version="1.0",
                effective_date="2025-05-01",
                owner="Platform & Infrastructure",
                lang="en",
                words=(500, 900),
                sections=sections,
                facts=facts_for(base, None),
            )
        )
    for i, team in enumerate(TEAMS, start=1):
        docs.append(
            Doc(
                doc_id=f"ENG-TEAM-{i:02d}",
                base=f"ENG-TEAM-{i:02d}",
                family="ENG",
                title=f"Team Charter — {team}",
                version="1.0",
                effective_date="2025-02-01",
                owner=team,
                lang="en",
                words=(400, 700),
                sections=["Mission", "Team", "How we work", "Interfaces", "Questions"],
                facts=facts_for(f"ENG-TEAM-{i:02d}", None),
            )
        )

    # OPS
    for base, title, sections in [
        (
            "OPS-BERLIN",
            "Berlin Office Guide",
            [
                "Welcome",
                "Getting in",
                "Desks and rooms",
                "Kitchen",
                "Parking and deliveries",
                "Questions",
            ],
        ),
        (
            "OPS-LISBON",
            "Lisbon Office Guide",
            ["Welcome", "Desks", "Getting in", "Kitchen", "Questions"],
        ),
        ("OPS-DESKS", "Desk Booking How-To", ["Purpose", "Perch basics", "Etiquette", "Questions"]),
        ("OPS-EVENTS", "Team Events Guide", ["Purpose", "Budget", "Booking", "Questions"]),
        (
            "OPS-FACILITIES",
            "Facilities Requests",
            ["Purpose", "Reporting an issue", "Timelines", "Questions"],
        ),
        ("OPS-MAIL", "Mail & Shipping", ["Purpose", "Incoming", "Outgoing", "Questions"]),
        (
            "OPS-VISITORS",
            "Visitors Guide",
            ["Purpose", "Registering guests", "On the day", "Questions"],
        ),
        (
            "OPS-KITCHEN",
            "Kitchen & Supplies",
            ["Purpose", "What we stock", "Keeping it tidy", "Questions"],
        ),
        (
            "OPS-FIRSTAID",
            "First Aid & Emergencies",
            ["Purpose", "First aiders", "Evacuation", "Questions"],
        ),
        ("OPS-ROOMS", "Meeting Room Guide", ["Purpose", "Rooms", "Booking", "Questions"]),
        (
            "OPS-SUSTAIN",
            "Sustainability at the Office",
            ["Purpose", "Waste", "Energy", "Questions"],
        ),
        (
            "OPS-ACCESSIBILITY",
            "Accessibility at Our Offices",
            ["Purpose", "Berlin", "Lisbon", "Questions"],
        ),
        ("OPS-QUIET", "Quiet Zones", ["Purpose", "Where", "Rules", "Questions"]),
        (
            "OPS-SWAG",
            "Merchandise & Welcome Packs",
            ["Purpose", "What you get", "Ordering more", "Questions"],
        ),
    ]:
        mentions = []
        if base == "OPS-ROOMS":
            mentions.append(
                {
                    "fact": fact_by_key_current["office.recurring_slots"].id,
                    "ref": "POL-028",
                    "note": "the recurring-booking cap is in POL-028 §3; do not quote it",
                }
            )
        docs.append(
            Doc(
                doc_id=base,
                base=base,
                family="OPS",
                title=title,
                version="1.0",
                effective_date="2025-06-01",
                owner="Workplace & Operations",
                lang="en",
                words=(300, 700),
                sections=sections,
                facts=facts_for(base, None),
                mentions=mentions,
            )
        )

    # EXEC
    for i in range(1, 7):
        docs.append(
            Doc(
                doc_id=f"EXEC-AH-{i:02d}",
                base=f"EXEC-AH-{i:02d}",
                family="EXEC",
                title=f"All-Hands Notes — {['January', 'March', 'May', 'July', 'September', 'November'][i - 1]} 2025",
                version="1.0",
                effective_date=f"2025-{2 * i - 1:02d}-20",
                owner="Leadership Team",
                lang="en",
                words=(500, 800),
                sections=["Highlights", "People", "Customers", "Questions from the floor"],
                facts=facts_for(f"EXEC-AH-{i:02d}", None),
                format="md",
            )
        )
    for i in range(1, 5):
        docs.append(
            Doc(
                doc_id=f"EXEC-OKR-{i:02d}",
                base=f"EXEC-OKR-{i:02d}",
                family="EXEC",
                title=f"Company OKRs — {['Q1', 'Q2', 'Q3', 'Q4'][i - 1]} 2025",
                version="1.0",
                effective_date=f"2025-{3 * i - 2:02d}-01",
                owner="Leadership Team",
                lang="en",
                words=(400, 600),
                sections=["Objectives", "Key results", "Owners", "Review"],
                default_label="managers",
                facts=facts_for(f"EXEC-OKR-{i:02d}", None),
            )
        )
    for i in range(1, 6):
        docs.append(
            Doc(
                doc_id=f"EXEC-BOARD-{i:02d}",
                base=f"EXEC-BOARD-{i:02d}",
                family="EXEC",
                title=f"Board Memo {i} — 2025",
                version="1.0",
                effective_date=f"2025-{2 * i:02d}-05",
                owner="Leadership Team",
                lang="en",
                words=(500, 800),
                sections=["Summary", "Growth", "Cash", "Risks", "Asks"],
                default_label="leadership",
                facts=facts_for(f"EXEC-BOARD-{i:02d}", None),
            )
        )
    docs.append(
        Doc(
            doc_id="EXEC-COMP",
            base="EXEC-COMP",
            family="EXEC",
            title="Compensation Bands (Berlin)",
            version="1.0",
            effective_date="2026-01-01",
            owner="Leadership Team",
            lang="en",
            words=(350, 500),
            sections=["Purpose", "Bands", "Annual review budget", "Handling"],
            default_label="leadership",
            facts=facts_for("EXEC-COMP", None),
            notes=["Render the bands as a markdown table with three rows."],
        )
    )

    # meeting notes
    mtg_topics = [
        "Routing Core weekly",
        "Platform sync",
        "Release planning",
        "Customer Success review",
        "Fleet Insights planning",
        "Security council",
        "Workplace committee",
        "People ops sync",
    ]
    for i in range(1, 31):
        base = f"MTG-{i:02d}"
        team = mtg_topics[(i - 1) % len(mtg_topics)]
        date = f"2025-{(i % 12) + 1:02d}-{(i * 3) % 27 + 1:02d}"
        docs.append(
            Doc(
                doc_id=base,
                base=base,
                family="MTG",
                title=f"Meeting Notes — {team} ({date})",
                version=None,
                effective_date=date,
                owner=team,
                lang="en",
                words=(250, 450),
                sections=["Attendees", "Discussion", "Decisions", "Action items"],
                facts=facts_for(base, None),
                format="md",
                date_context=date,
                notes=[
                    "Informal meeting notes: bullet points, first names, no policy numbers. "
                    + (
                        "Record the assigned decision value in the Decisions section."
                        if facts_for(base, None)
                        else "Invent no numeric decisions."
                    )
                ],
            )
        )

    # FAQ + announcements (FAQ-001..006 are stale: they still state the old value of a versioned fact)
    faq_titles = [
        "Vacation FAQ",
        "Remote Work FAQ",
        "Expenses FAQ",
        "Passwords FAQ",
        "Learning Budget FAQ",
        "Overtime FAQ",
        "Onboarding FAQ",
        "Equipment FAQ",
        "Sick Leave FAQ",
        "Parental Leave FAQ",
        "Travel FAQ",
        "Meeting Rooms FAQ",
        "Benefits FAQ",
        "Data Protection FAQ",
        "Security FAQ",
        "Workation FAQ",
        "Performance Review FAQ",
        "Procurement FAQ",
    ]
    stale = {f.stale_in[0]: f for f in reg.facts if f.stale_in}
    for i, title in enumerate(faq_titles, start=1):
        base = f"FAQ-{i:03d}"
        facts = [stale[base].id] if base in stale else []
        notes = [
            "Short Q&A format (question in bold, short answer). Refer to policies by id for anything numeric — "
            "do not quote figures."
        ]
        if base in stale:
            notes = [
                f"STALE FAQ written when {stale[base].doc} version {stale[base].versions[0]} was current: "
                f"state the assigned (old) value plainly as if it were current. No hint that it is outdated."
            ]
        docs.append(
            Doc(
                doc_id=base,
                base=base,
                family="FAQ",
                title=title,
                version=None,
                effective_date="2024-02-01" if base in stale else "2025-09-01",
                owner="People & Culture",
                lang="en",
                words=(250, 450),
                sections=["Questions"],
                facts=facts,
                format="md",
                notes=notes,
            )
        )
    ann_titles = [
        "New Travel Policy version",
        "Security training reminder",
        "Office closure over the holidays",
        "Perch desk booking launch",
        "Benefits changes 2026",
        "Vacation policy update",
        "New corporate card provider",
        "Equipment refresh wave",
    ]
    for i, title in enumerate(ann_titles, start=1):
        docs.append(
            Doc(
                doc_id=f"ANN-{i:02d}",
                base=f"ANN-{i:02d}",
                family="ANN",
                title=f"Announcement: {title}",
                version=None,
                effective_date=f"2025-{i + 2:02d}-03",
                owner="People & Culture",
                lang="en",
                words=(200, 350),
                sections=["Announcement"],
                format="md",
                notes=["An intranet announcement; refer to the policy by id, quote no numbers."],
            )
        )

    # public-facing
    for base, title, sections in [
        ("PUB-SLA", "Service Level Agreement", ["Scope", "Availability", "Maintenance", "Credits"]),
        ("PUB-SUPPORT", "Support Handbook", ["Scope", "Priorities", "Channels", "Escalation"]),
        ("PUB-API", "API Overview", ["Scope", "Authentication", "Keys and rotation", "Versioning"]),
        (
            "PUB-SECURITY",
            "Security Overview",
            ["Scope", "Infrastructure", "Data handling", "Compliance"],
        ),
        ("PUB-DPA", "Data Processing Summary", ["Scope", "Roles", "Sub-processors", "Retention"]),
        (
            "PUB-ONBOARD",
            "Customer Onboarding Guide",
            ["Scope", "Kick-off", "Data import", "Go-live"],
        ),
        ("PUB-RELEASE", "Release Notes Policy", ["Scope", "Cadence", "Deprecations"]),
        ("PUB-STATUS", "Status Page Guide", ["Scope", "Components", "Subscribing"]),
        ("PUB-TRAINING", "Customer Training Catalogue", ["Scope", "Courses", "Booking"]),
        ("PUB-GLOSSARY", "Product Glossary", ["Scope", "Terms"]),
    ]:
        docs.append(
            Doc(
                doc_id=base,
                base=base,
                family="PUB",
                title=title,
                version="1.0",
                effective_date="2025-07-01",
                owner="Go-to-Market",
                lang="en",
                words=(500, 900),
                sections=sections,
                facts=facts_for(base, None),
                notes=["Customer-facing tone; nothing about internal HR matters."],
            )
        )

    # DE mirrors: current versions of POL-001..POL-020 and FAQ-007..FAQ-016
    for d in list(docs):
        if d.family == "POL" and d.superseded_by is None and int(d.base[-3:]) <= 20:
            docs.append(
                Doc(
                    doc_id=f"{d.base}-DE",
                    base=f"{d.base}-DE",
                    family="DE",
                    title=d.title,
                    version=d.version,
                    effective_date=d.effective_date,
                    owner=d.owner,
                    lang="de",
                    words=d.words,
                    sections=d.sections,
                    restricted=d.restricted,
                    facts=d.facts,
                    mentions=d.mentions,
                    mirror_of=d.doc_id,
                    notes=[
                        "Faithful German translation of the English document: same "
                        "structure, same facts, German number formatting."
                    ],
                )
            )
        if d.family == "FAQ" and 7 <= int(d.base[-3:]) <= 16:
            docs.append(
                Doc(
                    doc_id=f"{d.base}-DE",
                    base=f"{d.base}-DE",
                    family="DE",
                    title=d.title,
                    version=None,
                    effective_date=d.effective_date,
                    owner=d.owner,
                    lang="de",
                    words=d.words,
                    sections=d.sections,
                    facts=d.facts,
                    mirror_of=d.doc_id,
                    format="md",
                    notes=["Faithful German translation."],
                )
            )
    return docs


def build() -> tuple[list[Fact], list[Doc]]:
    reg = Registry(SEED)
    build_facts(reg)
    docs = build_docs(reg)
    return reg.facts, docs


def to_dicts(items: list) -> list[dict]:
    out = []
    for item in items:
        d = asdict(item)
        if "words" in d:
            d["words"] = list(d["words"])
        if "restricted" in d:
            d["restricted"] = {str(k): v for k, v in d["restricted"].items()}
        out.append(d)
    return out
