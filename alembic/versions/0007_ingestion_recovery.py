"""Durable ingestion attempts and leases.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("ingestion_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("documents", sa.Column("processing_token", sa.Uuid(), nullable=True))
    for name in ("lease_expires_at", "next_attempt_at", "last_enqueued_at"):
        op.add_column("documents", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_documents_recovery", "documents", ["status", "next_attempt_at", "lease_expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_documents_recovery", "documents")
    for name in (
        "last_enqueued_at",
        "next_attempt_at",
        "lease_expires_at",
        "processing_token",
        "ingestion_attempts",
    ):
        op.drop_column("documents", name)
