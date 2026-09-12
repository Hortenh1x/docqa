"""Daily spending reservations shared by guest IP and account identities.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spend_reservations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("ip_digest", sa.Text(), nullable=False),
        sa.Column("payer_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("reserved_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("actual_usd", sa.Numeric(18, 8)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("reserved_usd >= 0", name="reserved_nonnegative"),
        sa.CheckConstraint("actual_usd IS NULL OR actual_usd >= 0", name="actual_nonnegative"),
    )
    op.create_index(
        "ix_spend_reservations_guest", "spend_reservations", ["day", "ip_digest", "payer_user_id"]
    )
    op.create_table(
        "spend_allocations",
        sa.Column(
            "reservation_id",
            sa.Uuid(),
            sa.ForeignKey("spend_reservations.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("scope", sa.Text(), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
    )
    op.create_index("ix_spend_allocations_scope_day", "spend_allocations", ["scope", "day"])
    op.add_column(
        "documents",
        sa.Column("billing_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
    )
    op.add_column("documents", sa.Column("billing_ip_digest", sa.Text()))
    op.add_column(
        "queries", sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"))
    )
    op.add_column("queries", sa.Column("ip_digest", sa.Text()))
    op.create_index("ix_queries_user_created", "queries", ["user_id", "created_at"])
    op.create_index("ix_queries_ip_created", "queries", ["ip_digest", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_queries_ip_created", table_name="queries")
    op.drop_index("ix_queries_user_created", table_name="queries")
    op.drop_column("queries", "ip_digest")
    op.drop_column("queries", "user_id")
    op.drop_column("documents", "billing_ip_digest")
    op.drop_column("documents", "billing_user_id")
    op.drop_table("spend_allocations")
    op.drop_table("spend_reservations")
