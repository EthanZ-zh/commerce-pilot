"""Add pgvector-backed policy chunks for hybrid retrieval."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260825_0003"
down_revision: str | None = "20260825_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "policy_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "policy_id",
            sa.Integer(),
            sa.ForeignKey("policies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Vector(256), nullable=False),
        sa.Column("embedding_model", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("policy_id", "chunk_index", name="uq_policy_chunk_index"),
    )
    op.create_index("ix_policy_chunks_policy_id", "policy_chunks", ["policy_id"])
    op.create_index("ix_policy_chunks_embedding_model", "policy_chunks", ["embedding_model"])
    op.create_index(
        "ix_policy_chunks_policy_model", "policy_chunks", ["policy_id", "embedding_model"]
    )
    op.create_index(
        "ix_policy_chunks_embedding_hnsw",
        "policy_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_policy_chunks_embedding_hnsw", table_name="policy_chunks")
    op.drop_index("ix_policy_chunks_policy_model", table_name="policy_chunks")
    op.drop_index("ix_policy_chunks_embedding_model", table_name="policy_chunks")
    op.drop_index("ix_policy_chunks_policy_id", table_name="policy_chunks")
    op.drop_table("policy_chunks")
