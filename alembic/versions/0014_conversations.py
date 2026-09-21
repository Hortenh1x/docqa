"""Conversation ownership, transcript outcomes and source generations.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("source_generation", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "conversations",
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
        sa.Column("title", sa.Text(), nullable=False, server_default="New chat"),
        sa.Column("kind", sa.Text(), nullable=False, server_default="chat"),
        sa.Column("owner_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column(
            "owner_guest_session_id",
            sa.Uuid(),
            sa.ForeignKey("account_sessions.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "created_by_api_key_id",
            sa.Uuid(),
            sa.ForeignKey("api_keys.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('chat', 'legacy')", name=op.f("ck_conversations_kind")),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 120",
            name=op.f("ck_conversations_title_length"),
        ),
        sa.CheckConstraint(
            "(owner_user_id IS NOT NULL AND owner_guest_session_id IS NULL "
            "AND created_by_api_key_id IS NULL) OR "
            "(owner_user_id IS NULL AND owner_guest_session_id IS NOT NULL "
            "AND created_by_api_key_id IS NULL) OR "
            "(owner_user_id IS NULL AND owner_guest_session_id IS NULL "
            "AND created_by_api_key_id IS NOT NULL)",
            name=op.f("ck_conversations_one_owner"),
        ),
        sa.CheckConstraint(
            "kind <> 'legacy' OR archived_at IS NOT NULL",
            name=op.f("ck_conversations_legacy_archived"),
        ),
    )
    op.create_index(
        "ix_conversations_collection_archive_activity",
        "conversations",
        ["collection_id", "archived_at", sa.text("updated_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_conversations_owner_user", "conversations", ["owner_user_id", "collection_id"]
    )
    op.create_index(
        "ix_conversations_owner_guest",
        "conversations",
        ["owner_guest_session_id", "collection_id"],
    )

    op.add_column(
        "queries",
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
        ),
    )
    op.add_column(
        "queries",
        sa.Column("parent_query_id", sa.Uuid(), sa.ForeignKey("queries.id", ondelete="SET NULL")),
    )
    op.add_column("queries", sa.Column("outcome", sa.Text()))
    op.add_column("queries", sa.Column("outcome_reason", sa.Text()))
    op.add_column("queries", sa.Column("source_generation", sa.Integer()))
    op.add_column("queries", sa.Column("access_fingerprint", sa.Text()))
    op.add_column(
        "queries",
        sa.Column("context_reset", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_check_constraint(
        op.f("ck_queries_outcome"),
        "queries",
        "outcome IS NULL OR outcome IN "
        "('answered', 'refused', 'clarification', 'failed', 'cancelled')",
    )
    op.create_index(
        "ix_queries_conversation_created",
        "queries",
        ["conversation_id", "created_at", "id"],
    )

    # Only an account user is durable proof of ownership. Unowned guest/API-key rows
    # deliberately remain unattached and cannot be claimed by knowing their UUIDs.
    op.execute(
        """
        INSERT INTO conversations
            (tenant_id, collection_id, title, kind, owner_user_id,
             created_at, updated_at, archived_at)
        SELECT q.tenant_id, q.collection_id, 'Previous questions', 'legacy', q.user_id,
               min(q.created_at), max(q.created_at), now()
        FROM queries q
        WHERE q.user_id IS NOT NULL
        GROUP BY q.tenant_id, q.collection_id, q.user_id
        """
    )
    op.execute(
        """
        UPDATE queries q
        SET conversation_id = c.id
        FROM conversations c
        WHERE c.kind = 'legacy'
          AND c.tenant_id = q.tenant_id
          AND c.collection_id = q.collection_id
          AND c.owner_user_id = q.user_id
          AND q.user_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_queries_conversation_created", table_name="queries")
    op.drop_constraint(op.f("ck_queries_outcome"), "queries", type_="check")
    for column in (
        "context_reset",
        "access_fingerprint",
        "source_generation",
        "outcome_reason",
        "outcome",
        "parent_query_id",
        "conversation_id",
    ):
        op.drop_column("queries", column)
    op.drop_table("conversations")
    op.drop_column("collections", "source_generation")
