"""Field extraction building blocks: specs, rules, coercion, evidence, stub JSON LLM."""

import pytest

from app.core.errors import InvalidSchemaError
from app.extraction.context import ChunkText
from app.extraction.evidence import find_evidence
from app.extraction.fields import parse_definition, response_schema
from app.extraction.rules import RuleUnknown, compile_rule, evaluate_rule
from app.extraction.validate import parse_date, parse_number, validate
from app.generation.llm.stub import StubLLM

INVOICE_FIELDS = [
    {"name": "invoice_number", "type": "string", "required": True},
    {"name": "invoice_date", "type": "date"},
    {"name": "total", "type": "number", "required": True},
    {"name": "tax", "type": "number"},
    {"name": "subtotal", "type": "number"},
    {"name": "currency", "type": "enum", "enum_values": ["EUR", "USD"]},
    {"name": "paid", "type": "boolean"},
    {"name": "items", "type": "array"},
]


# --- specs ------------------------------------------------------------------------------


def test_definition_rejects_bad_names_duplicates_and_rules():
    with pytest.raises(InvalidSchemaError, match="name"):
        parse_definition([{"name": "Invoice Number"}], [], max_fields=30)
    with pytest.raises(InvalidSchemaError, match="unique"):
        parse_definition([{"name": "a"}, {"name": "a"}], [], max_fields=30)
    with pytest.raises(InvalidSchemaError, match="enum_values"):
        parse_definition([{"name": "kind", "type": "enum"}], [], max_fields=30)
    with pytest.raises(InvalidSchemaError, match="unknown field"):
        parse_definition([{"name": "a"}], ["a == b"], max_fields=30)
    with pytest.raises(InvalidSchemaError, match="unknown function"):
        parse_definition([{"name": "a"}], ["__import__('os')"], max_fields=30)
    with pytest.raises(InvalidSchemaError, match="unsupported"):
        parse_definition([{"name": "a"}], ["a.__class__"], max_fields=30)
    with pytest.raises(InvalidSchemaError, match="at most 1"):
        parse_definition([{"name": "a"}, {"name": "b"}], [], max_fields=1)
    with pytest.raises(InvalidSchemaError, match="regular expression"):
        parse_definition([{"name": "a", "pattern": "("}], [], max_fields=30)


def test_response_schema_mirrors_field_types():
    definition = parse_definition(INVOICE_FIELDS, [], max_fields=30)
    schema = response_schema(definition)
    props = schema["properties"]["fields"]["properties"]
    assert set(props) == {f["name"] for f in INVOICE_FIELDS}
    assert props["total"]["properties"]["value"]["type"] == ["number", "string", "null"]
    assert props["currency"]["properties"]["value"]["enum"] == ["EUR", "USD", None]
    assert props["items"]["properties"]["value"]["items"] == {"type": "string"}
    assert schema["properties"]["fields"]["required"] == list(props)


# --- rules --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "values", "expected"),
    [
        ("abs(subtotal + tax - total) < 0.05", {"subtotal": 100, "tax": 19, "total": 119}, True),
        ("abs(subtotal + tax - total) < 0.05", {"subtotal": 100, "tax": 19, "total": 120}, False),
        ("due >= issued", {"due": "2026-02-01", "issued": "2026-01-15"}, True),
        ("len(parties) >= 2 and total > 0", {"parties": ["A", "B"], "total": 5}, True),
        ("currency in ['EUR', 'USD']", {"currency": "GBP"}, False),
        ("not paid or total == 0", {"paid": True, "total": 0}, True),
        ("sum(amounts) == total", {"amounts": ["10", "5.5"], "total": 15.5}, True),
    ],
)
def test_rules_evaluate(rule, values, expected):
    names = set(values)
    assert evaluate_rule(compile_rule(rule, names), values) is expected


def test_rule_with_missing_operand_is_unknown_not_failed():
    tree = compile_rule("subtotal + tax == total", {"subtotal", "tax", "total"})
    with pytest.raises(RuleUnknown):
        evaluate_rule(tree, {"subtotal": 1, "tax": None, "total": 1})


@pytest.mark.parametrize(
    "rule", ["open('x')", "a.b", "a[0]", "lambda: 1", "a if b else c", "x = 1"]
)
def test_rule_syntax_whitelist(rule):
    with pytest.raises(ValueError):
        compile_rule(rule, {"a", "b", "c", "x"})


# --- coercion -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,250.00 EUR", 1250.0),
        ("€ 1.250,00", 1250.0),
        ("1 250,50", 1250.5),
        ("-42", -42.0),
        ("12,345", 12345.0),
        ("12,34", 12.34),
        ("USD 3.5", 3.5),
        ("n/a", None),
        (7, 7.0),
        (True, None),
    ],
)
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-03-05", "2026-03-05"),
        ("05.03.2026", "2026-03-05"),
        ("March 5, 2026", "2026-03-05"),
        ("5 March 2026", "2026-03-05"),
        ("03/05/2026", "2026-05-03"),  # day/month first (European corpus)
        ("Issued 2026-03-05T10:00:00", "2026-03-05"),
        ("sometime", None),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_validate_coerces_and_reports_issues():
    definition = parse_definition(
        INVOICE_FIELDS,
        ["abs(subtotal + tax - total) < 0.05"],
        max_fields=30,
    )
    raw = {
        "invoice_number": {"value": "INV-42", "quote": "Invoice number: INV-42"},
        "invoice_date": {"value": "05.03.2026", "quote": None},
        "total": {"value": "1,190.00 EUR", "quote": "Total: 1,190.00 EUR"},
        "tax": {"value": "190", "quote": None},
        "subtotal": {"value": "1000", "quote": None},
        "currency": {"value": "eur", "quote": None},
        "paid": {"value": "No", "quote": None},
        "items": {"value": "Consulting; Travel", "quote": None},
    }
    values, quotes, issues = validate(definition, raw)
    assert values == {
        "invoice_number": "INV-42",
        "invoice_date": "2026-03-05",
        "total": 1190.0,
        "tax": 190.0,
        "subtotal": 1000.0,
        "currency": "EUR",
        "paid": False,
        "items": ["Consulting", "Travel"],
    }
    assert quotes["total"] == "Total: 1,190.00 EUR"
    assert issues == []

    values, _, issues = validate(
        definition,
        {"total": {"value": "lots", "quote": None}, "currency": {"value": "GBP", "quote": None}},
    )
    codes = sorted((i["field"], i["code"]) for i in issues)
    assert ("total", "type_mismatch") in codes
    assert ("total", "missing_required") in codes
    assert ("invoice_number", "missing_required") in codes
    assert ("currency", "enum_mismatch") in codes
    assert all(i["code"] != "rule_failed" for i in issues)  # operands missing → unknown

    _, _, issues = validate(
        definition,
        {
            "invoice_number": {"value": "X", "quote": None},
            "total": {"value": 100, "quote": None},
            "tax": {"value": 19, "quote": None},
            "subtotal": {"value": 90, "quote": None},
        },
    )
    assert [i["code"] for i in issues] == ["rule_failed"]


# --- evidence ---------------------------------------------------------------------------------


def _chunks():
    return [
        ChunkText(
            1, 0, "Acme Ltd\n\nInvoice number: INV-42\nInvoice date: 05.03.2026", 1, 1, 20, "all"
        ),
        ChunkText(
            2,
            1,
            "Subtotal: 1,000.00 EUR\nVAT 19%: 190.00 EUR\nTotal: 1,190.00 EUR",
            2,
            2,
            20,
            "all",
        ),
    ]


def test_evidence_locates_quote_then_value_with_confidence_tiers():
    evidence, confidence = find_evidence("INV-42", "Invoice number: INV-42", _chunks(), None)
    assert confidence == 0.9
    assert evidence["chunk_id"] == 1 and evidence["page"] == 1
    assert evidence["quote"] == "Invoice number: INV-42"

    evidence, confidence = find_evidence(1190.0, "Total: 1,190.00 EUR", _chunks(), None)
    assert confidence == 0.75  # quote found, value rendered differently
    assert evidence["chunk_id"] == 2

    evidence, confidence = find_evidence("190.00 EUR", None, _chunks(), None)
    assert confidence == 0.6 and evidence["chunk_id"] == 2

    evidence, confidence = find_evidence("nowhere", "not in the document at all", _chunks(), None)
    assert evidence is None and confidence == 0.4


def test_evidence_maps_to_the_ocr_block_box():
    layout = [
        {
            "page": 2,
            "size": [1200, 1600],
            "blocks": [
                {"bbox": [50, 100, 600, 130], "text": "Subtotal: 1,000.00 EUR"},
                {"bbox": [50, 400, 600, 430], "text": "Total: 1,190.00 EUR"},
            ],
        }
    ]
    evidence, _ = find_evidence("1,190.00 EUR", "Total: 1,190.00 EUR", _chunks(), layout)
    assert evidence["page"] == 2
    assert evidence["bbox"] == [50, 400, 600, 430]
    assert evidence["page_size"] == [1200, 1600]


# --- stub llm -------------------------------------------------------------------------------


async def test_stub_complete_json_reads_label_value_lines():
    definition = parse_definition(INVOICE_FIELDS[:3], [], max_fields=30)
    user = (
        "FIELDS:\n...\n\nDOCUMENT:\nInvoice number: INV-42\nInvoice date: 05.03.2026\n"
        "Total: 1,190.00 EUR\n"
    )
    result = await StubLLM().complete_json("sys", user, response_schema(definition), max_tokens=100)
    fields = result.content["fields"]
    assert fields["invoice_number"] == {"value": "INV-42", "quote": "Invoice number: INV-42"}
    assert fields["invoice_date"]["value"] == "05.03.2026"
    assert fields["total"]["value"] == "1,190.00 EUR"
    assert result.prompt_tokens == 200
