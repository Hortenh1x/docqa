"""Fence results against collection cleanup.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections", sa.Column("data_version", sa.Integer(), nullable=False, server_default="0")
    )

    # Legacy suggestions may quote non-numeric restricted facts; discard them.
    op.execute("UPDATE collections SET suggested_questions = NULL")


def downgrade() -> None:
    op.drop_column("collections", "data_version")
