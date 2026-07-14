import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import REAL, BigInteger, ForeignKey, Index, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Query(Base):
    __tablename__ = "queries"
    __table_args__ = (Index("ix_queries_tenant_id_created_at", "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE")
    )
    question: Mapped[str]
    answer: Mapped[str | None]
    # refusals are recorded too: "how many questions miss the corpus" is a statistic
    # clients genuinely care about
    refused: Mapped[bool] = mapped_column(server_default=text("false"))
    confidence: Mapped[float | None] = mapped_column(REAL)
    latency_ms: Mapped[int | None]
    prompt_tokens: Mapped[int | None]
    completion_tokens: Mapped[int | None]
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    model: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class QueryCitation(Base):
    """Context blocks shown to the model, by rank — the ground truth behind [n] markers."""

    __tablename__ = "query_citations"

    query_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("queries.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chunks.id", ondelete="CASCADE"))
    score: Mapped[float | None] = mapped_column(REAL)
