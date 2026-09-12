"""Personal accounts and explicit public collection scope. Existing data stays private.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("kind", sa.Text(), nullable=False, server_default="service"))
    op.create_check_constraint(
        op.f("ck_tenants_kind"), "tenants", "kind IN ('service', 'personal')"
    )
    op.add_column(
        "collections",
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_check_constraint(
        op.f("ck_collections_public_read_only"), "collections", "NOT is_public OR read_only"
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "account_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("csrf_token", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "account_tokens",
        sa.Column("token_hash", sa.Text(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('verify', 'reset')", name="kind"),
    )
    op.create_table(
        "auth_attempts",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table in ("account_sessions", "account_tokens", "auth_attempts"):
        op.create_index(f"ix_{table}_expires_at", table, ["expires_at"])
    for table in ("account_sessions", "account_tokens"):
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])


def downgrade() -> None:
    for table in ("auth_attempts", "account_tokens", "account_sessions", "users"):
        op.drop_table(table)
    op.drop_constraint(op.f("ck_collections_public_read_only"), "collections", type_="check")
    op.drop_column("collections", "is_public")
    op.drop_constraint(op.f("ck_tenants_kind"), "tenants", type_="check")
    op.drop_column("tenants", "kind")
