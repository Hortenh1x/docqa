"""Field specifications as users define them, and the response schema built from them."""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.core.errors import InvalidSchemaError
from app.extraction.rules import compile_rule

FieldType = Literal["string", "number", "integer", "date", "boolean", "enum", "array"]

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class FieldSpec(BaseModel):
    # snake_case identifier; the label shown to the model is the name with spaces
    name: str = Field(pattern=_NAME_RE.pattern)
    type: FieldType = "string"
    description: str = Field(default="", max_length=400)
    required: bool = False
    enum_values: list[str] | None = Field(default=None, max_length=50)
    pattern: str | None = Field(default=None, max_length=200)
    examples: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("pattern")
    @classmethod
    def _compiles(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"invalid regular expression: {exc}") from exc
        return value

    @model_validator(mode="after")
    def _enum_needs_values(self) -> "FieldSpec":
        if self.type == "enum" and not self.enum_values:
            raise ValueError("an enum field needs enum_values")
        if self.type != "enum" and self.enum_values:
            raise ValueError("enum_values is only valid for type 'enum'")
        return self

    @property
    def label(self) -> str:
        return self.name.replace("_", " ")


class SchemaDefinition(BaseModel):
    fields: list[FieldSpec] = Field(min_length=1)
    rules: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _unique_names_and_valid_rules(self) -> "SchemaDefinition":
        names = [f.name for f in self.fields]
        if len(set(names)) != len(names):
            raise ValueError("field names must be unique")
        for rule in self.rules:
            compile_rule(rule, set(names))  # raises ValueError with the reason
        return self


def parse_definition(
    fields: list[dict[str, Any]], rules: list[str] | None, *, max_fields: int
) -> SchemaDefinition:
    try:
        definition = SchemaDefinition.model_validate({"fields": fields, "rules": rules or []})
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"])
        message = str(first["msg"]).removeprefix("Value error, ")
        raise InvalidSchemaError(f"{location}: {message}" if location else message) from None
    except ValueError as exc:
        raise InvalidSchemaError(str(exc)) from None
    if len(definition.fields) > max_fields:
        raise InvalidSchemaError(f"a schema may have at most {max_fields} fields")
    return definition


def _json_type(spec: FieldSpec) -> dict[str, Any]:
    match spec.type:
        case "number":
            return {"type": ["number", "string", "null"]}
        case "integer":
            return {"type": ["integer", "string", "null"]}
        case "boolean":
            return {"type": ["boolean", "string", "null"]}
        case "array":
            return {"type": ["array", "null"], "items": {"type": "string"}}
        case "enum":
            return {"type": ["string", "null"], "enum": [*(spec.enum_values or []), None]}
        case _:
            return {"type": ["string", "null"]}


def response_schema(definition: SchemaDefinition) -> dict[str, Any]:
    """JSON Schema of the model's answer: ``{"fields": {name: {"value", "quote"}}}``."""
    properties: dict[str, Any] = {}
    for spec in definition.fields:
        properties[spec.name] = {
            "type": "object",
            "description": spec.description or spec.label,
            "properties": {
                "value": _json_type(spec),
                "quote": {"type": ["string", "null"]},
            },
            "required": ["value", "quote"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": {
            "fields": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            }
        },
        "required": ["fields"],
        "additionalProperties": False,
    }
