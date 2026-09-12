"""Optional Google identities and one-time browser-bound authorization state.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_identities",
        sa.Column("issuer", sa.Text(), primary_key=True),
        sa.Column("subject", sa.Text(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "google_auth_states",
        sa.Column("state_hash", sa.Text(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("account_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nonce", sa.Text(), nullable=False),
        sa.Column("code_verifier", sa.Text(), nullable=False),
        sa.Column("link_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_google_auth_states_session_id", "google_auth_states", ["session_id"])
    op.create_index("ix_google_auth_states_expires_at", "google_auth_states", ["expires_at"])


def downgrade() -> None:
    op.drop_table("google_auth_states")
    op.drop_table("google_identities")
