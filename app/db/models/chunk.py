import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Computed, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base

# fixed by ADR: bge-m3 is natively 1024, OpenAI text-embedding-3-* truncates to 1024
# (matryoshka), Voyage 3.5 is 1024. Changing this means a migration + full reindex.
EMBEDDING_DIM = 1024


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index(
            "chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("chunks_tsv_gin", "tsv", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int]
    content: Mapped[str]
    token_count: Mapped[int]
    page_start: Mapped[int | None]  # None for formats without pages (md/txt/docx)
    page_end: Mapped[int | None]
    section_path: Mapped[str | None]  # heading breadcrumbs: "4. Travel > 4.2 Per-diems"
    # content label from the section's access marker ("all" when none) — retrieval filters
    # on it in the WHERE clause; never post-filter (see app/access)
    access_label: Mapped[str] = mapped_column(server_default=text("'all'"))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    # 'simple' config on purpose: the corpus is bilingual (EN+DE); language stemming
    # would break one of them. Vectors + reranking compensate for FTS recall.
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', content)", persisted=True)
    )
