"""Extraction prompt: fields with their types and descriptions, strict grounding rules."""

from app.extraction.fields import FieldSpec, SchemaDefinition

SYSTEM = (
    "You extract structured fields from one document. Rules:\n"
    "1. Use only the document text. Never guess or infer values that are not written.\n"
    '2. For every field return an object {"value": ..., "quote": ...}. `value` is the '
    "field's value in the requested type, or null when the document does not state it. "
    "`quote` is a short verbatim passage (one sentence or line, copied exactly) from which "
    "the value is read, or null when value is null.\n"
    "3. Dates as written are fine (they are normalised later); numbers may keep their "
    "separators and currency; booleans as true/false; enum fields must use one of the "
    "listed options exactly; array fields list every distinct item found.\n"
    '4. Return one JSON object with a single key "fields" and nothing else.'
)


def _describe(spec: FieldSpec) -> str:
    parts = [f"- {spec.name} ({spec.type}"]
    if spec.type == "enum" and spec.enum_values:
        parts.append(f"; one of: {', '.join(spec.enum_values)}")
    if spec.required:
        parts.append("; required")
    parts.append(")")
    if spec.description:
        parts.append(f": {spec.description}")
    if spec.examples:
        parts.append(f" Examples: {', '.join(spec.examples)}.")
    return "".join(parts)


def user_prompt(definition: SchemaDefinition, schema_name: str, context: str) -> str:
    fields = "\n".join(_describe(spec) for spec in definition.fields)
    return (
        f"Schema: {schema_name}\n\nFIELDS:\n{fields}\n\n"
        f"DOCUMENT:\n{context}\n\n"
        "Return the JSON object now."
    )
