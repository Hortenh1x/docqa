"""Pinpoint quote spans on recorded citations.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # [{"start": int, "end": int}] character spans into chunks.content for cited blocks;
    # NULL for uncited context blocks and for rows recorded before this release
    op.add_column(
        "query_citations",
        sa.Column("quotes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("query_citations", "quotes")
