"""Two example schemas users can copy (GET /v1/schemas/templates). They are starting
points, not built-in behaviour: the product is schema-agnostic."""

from typing import Any

TEMPLATES: list[dict[str, Any]] = [
    {
        "key": "invoice",
        "name": "Invoice",
        "description": "Supplier invoice header and totals.",
        "fields": [
            {
                "name": "invoice_number",
                "type": "string",
                "required": True,
                "description": "The invoice identifier as printed.",
            },
            {
                "name": "invoice_date",
                "type": "date",
                "required": True,
                "description": "Date of issue.",
            },
            {"name": "due_date", "type": "date", "description": "Payment due date."},
            {
                "name": "supplier",
                "type": "string",
                "required": True,
                "description": "Issuing company name.",
            },
            {"name": "customer", "type": "string", "description": "Billed company or person."},
            {
                "name": "currency",
                "type": "enum",
                "enum_values": ["EUR", "USD", "GBP", "CHF"],
                "description": "Currency of the amounts.",
            },
            {"name": "subtotal", "type": "number", "description": "Net amount before tax."},
            {"name": "tax", "type": "number", "description": "Total tax (VAT) amount."},
            {
                "name": "total",
                "type": "number",
                "required": True,
                "description": "Total amount due, tax included.",
            },
            {
                "name": "line_items",
                "type": "array",
                "description": "One entry per invoice line: description and amount.",
            },
        ],
        "rules": ["abs(subtotal + tax - total) < 0.05", "due_date >= invoice_date"],
    },
    {
        "key": "contract",
        "name": "Contract",
        "description": "Key terms of an agreement.",
        "fields": [
            {
                "name": "title",
                "type": "string",
                "required": True,
                "description": "Title of the agreement.",
            },
            {
                "name": "parties",
                "type": "array",
                "required": True,
                "description": "Legal names of every contracting party.",
            },
            {
                "name": "effective_date",
                "type": "date",
                "description": "Date the agreement takes effect.",
            },
            {"name": "term_months", "type": "integer", "description": "Initial term in months."},
            {
                "name": "auto_renewal",
                "type": "boolean",
                "description": "Whether the term renews automatically.",
            },
            {
                "name": "governing_law",
                "type": "string",
                "description": "Jurisdiction whose law governs the agreement.",
            },
            {
                "name": "notice_period_days",
                "type": "integer",
                "description": "Days of notice required to terminate.",
            },
            {
                "name": "contract_value",
                "type": "number",
                "description": "Total value or fee, if stated.",
            },
        ],
        "rules": ["len(parties) >= 2", "term_months > 0"],
    },
]
