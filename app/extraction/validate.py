"""Deterministic post-processing of the model's answer: type coercion (dates → ISO,
numbers with separators and currency symbols), pattern/enum/required checks, then the
schema's cross-field rules. Failures become issues, never exceptions — the user sees
them next to the values and can correct either."""

import re
from datetime import datetime
from typing import Any

from app.extraction.fields import FieldSpec, SchemaDefinition
from app.extraction.rules import RuleUnknown, compile_rule, evaluate_rule

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d %Y",
    "%Y-%m-%dT%H:%M:%S",
)
_TRUE = {"yes", "true", "y", "1", "x", "checked", "ja"}
_FALSE = {"no", "false", "n", "0", "unchecked", "nein", "none"}
_NUMBER_JUNK = re.compile(r"[^\d,.\-]")


def issue(field: str | None, code: str, message: str) -> dict[str, Any]:
    return {"field": field, "code": code, "message": message}


def parse_number(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        return float(raw)
    text = _NUMBER_JUNK.sub("", str(raw)).strip()
    if not text or text in ("-", ".", ","):
        return None
    negative = text.startswith("-")
    text = text.lstrip("-")
    if "," in text and "." in text:
        # the last separator is the decimal mark: 1,250.00 vs 1.250,00
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        head, _, tail = text.rpartition(",")
        text = f"{head.replace(',', '')}.{tail}" if len(tail) in (1, 2) else text.replace(",", "")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


def parse_date(raw: Any) -> str | None:
    text = str(raw).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    return match.group(0) if match else None


def parse_boolean(raw: Any) -> bool | None:
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def coerce(spec: FieldSpec, raw: Any) -> tuple[Any, dict[str, Any] | None]:
    """(value or None, issue or None) for one field's raw model value."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    match spec.type:
        case "number" | "integer":
            number = parse_number(raw)
            if number is None:
                return None, issue(spec.name, "type_mismatch", f"'{raw}' is not a number")
            if spec.type == "integer":
                if abs(number - round(number)) > 1e-9:
                    return None, issue(spec.name, "type_mismatch", f"'{raw}' is not an integer")
                return int(round(number)), None
            return number, None
        case "date":
            date = parse_date(raw)
            if date is None:
                return None, issue(spec.name, "type_mismatch", f"'{raw}' is not a date")
            return date, None
        case "boolean":
            flag = parse_boolean(raw)
            if flag is None:
                return None, issue(spec.name, "type_mismatch", f"'{raw}' is not yes/no")
            return flag, None
        case "enum":
            text = str(raw).strip()
            for option in spec.enum_values or []:
                if option.casefold() == text.casefold():
                    return option, None
            return None, issue(
                spec.name, "enum_mismatch", f"'{text}' is not one of {spec.enum_values}"
            )
        case "array":
            items: list[Any] = raw if isinstance(raw, list) else re.split(r"[;\n]|,\s", str(raw))
            values = [str(item).strip() for item in items if str(item).strip()]
            return (values or None), None
        case _:
            text = str(raw).strip()
            if spec.pattern and not re.fullmatch(spec.pattern, text):
                return text, issue(
                    spec.name, "pattern_mismatch", f"'{text}' does not match {spec.pattern}"
                )
            return text, None


def validate(
    definition: SchemaDefinition, raw_fields: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str | None], list[dict[str, Any]]]:
    """(coerced values, quotes, issues)."""
    values: dict[str, Any] = {}
    quotes: dict[str, str | None] = {}
    issues: list[dict[str, Any]] = []
    for spec in definition.fields:
        entry = raw_fields.get(spec.name)
        raw_value = entry.get("value") if isinstance(entry, dict) else entry
        quote = entry.get("quote") if isinstance(entry, dict) else None
        value, problem = coerce(spec, raw_value)
        if problem:
            issues.append(problem)
        if value is None and spec.required:
            issues.append(issue(spec.name, "missing_required", f"{spec.label} was not found"))
        values[spec.name] = value
        quotes[spec.name] = str(quote).strip() if quote else None
    names = {spec.name for spec in definition.fields}
    for rule in definition.rules:
        try:
            tree = compile_rule(rule, names)
            if not evaluate_rule(tree, values):
                issues.append(issue(None, "rule_failed", f"rule failed: {rule}"))
        except RuleUnknown:
            continue  # an operand is missing; the missing_required issue already says so
        except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
            issues.append(issue(None, "rule_error", f"rule could not be evaluated: {rule} ({exc})"))
    return values, quotes, issues
