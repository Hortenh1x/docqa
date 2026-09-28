"""External sources (Notion) and the document ↔ source link.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("credentials", sa.Text(), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("auto_sync_interval_s", sa.Integer()),
        sa.Column("sync_status", sa.Text(), nullable=False, server_default="idle"),
        sa.Column("sync_token", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_sync_started_at", sa.DateTime(timezone=True)),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_sync_error", sa.Text()),
        sa.Column("last_sync_stats", postgresql.JSONB()),
        sa.Column("billing_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("billing_ip_digest", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("kind IN ('notion', 'stub')", name=op.f("ck_sources_kind")),
        sa.CheckConstraint(
            "sync_status IN ('idle', 'queued', 'syncing', 'partial', 'failed')",
            name=op.f("ck_sources_sync_status"),
        ),
    )
    op.create_index("ix_sources_collection_id", "sources", ["collection_id"])
    op.create_index("ix_sources_auto_sync", "sources", ["auto_sync_interval_s", "last_sync_at"])

    op.add_column(
        "documents",
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("sources.id", ondelete="SET NULL")),
    )
    op.add_column("documents", sa.Column("external_id", sa.Text()))
    op.add_column("documents", sa.Column("external_url", sa.Text()))
    op.add_column("documents", sa.Column("external_version", sa.Text()))
    op.create_index(
        "uq_documents_source_external",
        "documents",
        ["source_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("source_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_documents_source_external", table_name="documents")
    for column in ("external_version", "external_url", "external_id", "source_id"):
        op.drop_column("documents", column)
    op.drop_index("ix_sources_auto_sync", table_name="sources")
    op.drop_index("ix_sources_collection_id", table_name="sources")
    op.drop_table("sources")
