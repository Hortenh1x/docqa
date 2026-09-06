"""access labels on chunks, role on queries

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # every existing chunk is open: legacy documents carry no access markers
    op.add_column(
        "chunks",
        sa.Column("access_label", sa.String(), nullable=False, server_default="all"),
    )
    op.add_column("queries", sa.Column("role", sa.String(), nullable=True))
    # suggested questions gain a min_role: ["q", …] → [{"question": "q", "min_role": …}];
    # everything generated so far came from open content, so the default role applies
    op.execute(
        """
        UPDATE collections
        SET suggested_questions = (
            SELECT jsonb_agg(jsonb_build_object('question', q, 'min_role', 'employee'))
            FROM jsonb_array_elements_text(suggested_questions) AS q
        )
        WHERE suggested_questions IS NOT NULL
          AND jsonb_typeof(suggested_questions) = 'array'
          AND jsonb_array_length(suggested_questions) > 0
          AND jsonb_typeof(suggested_questions->0) = 'string'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        UPDATE collections
        SET suggested_questions = (
            SELECT jsonb_agg(item->'question')
            FROM jsonb_array_elements(suggested_questions) AS item
        )
        WHERE suggested_questions IS NOT NULL
          AND jsonb_typeof(suggested_questions) = 'array'
          AND jsonb_array_length(suggested_questions) > 0
          AND jsonb_typeof(suggested_questions->0) = 'object'
        """
    )
    op.drop_column("queries", "role")
    op.drop_column("chunks", "access_label")
