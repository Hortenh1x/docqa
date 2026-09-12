"""Preserve the actual triggering identity for background suggestions.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column(
            "suggestion_billing_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")
        ),
    )
    op.add_column("collections", sa.Column("suggestion_billing_ip_digest", sa.Text()))
    op.add_column(
        "collections",
        sa.Column("suggestion_revision", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("collections", "suggestion_revision")
    op.drop_column("collections", "suggestion_billing_ip_digest")
    op.drop_column("collections", "suggestion_billing_user_id")
