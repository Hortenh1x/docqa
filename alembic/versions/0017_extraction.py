"""Schema-driven field extraction: schemas, extractions, OCR layout for evidence.

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # paragraph boxes of OCR'd pages so a field's evidence can be drawn on the scan
    op.add_column("documents", sa.Column("ocr_layout", postgresql.JSONB()))

    op.create_table(
        "extraction_schemas",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("fields", postgresql.JSONB(), nullable=False),
        sa.Column(
            "rules", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("index_facts", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "name", name=op.f("uq_extraction_schemas_tenant_id")),
    )

    op.create_table(
        "extractions",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "schema_id",
            sa.Uuid(),
            sa.ForeignKey("extraction_schemas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("processing_token", sa.Uuid()),
        sa.Column("model", sa.Text()),
        sa.Column(
            "fields", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "issues", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("error", sa.Text()),
        sa.Column("facts_chunk_id", sa.BigInteger()),
        sa.Column("billing_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("billing_ip_digest", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed')",
            name=op.f("ck_extractions_status"),
        ),
        sa.UniqueConstraint("document_id", "schema_id", name=op.f("uq_extractions_document_id")),
    )
    op.create_index("ix_extractions_schema_id", "extractions", ["schema_id"])
    op.create_index("ix_extractions_tenant_id", "extractions", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_extractions_tenant_id", table_name="extractions")
    op.drop_index("ix_extractions_schema_id", table_name="extractions")
    op.drop_table("extractions")
    op.drop_table("extraction_schemas")
    op.drop_column("documents", "ocr_layout")
