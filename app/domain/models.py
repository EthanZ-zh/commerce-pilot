from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (Index("ix_products_sku", "sku"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(200))
    region: Mapped[str] = mapped_column(String(40), index=True)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    sale_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    sales: Mapped[list[SalesDaily]] = relationship(back_populates="product")
    inventory: Mapped[list[InventorySnapshot]] = relationship(back_populates="product")


class SalesDaily(Base):
    __tablename__ = "sales_daily"
    __table_args__ = (
        UniqueConstraint("date", "product_id", name="uq_sales_date_product"),
        Index("ix_sales_product_date", "product_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    views: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))

    product: Mapped[Product] = relationship(back_populates="sales")


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"
    __table_args__ = (
        UniqueConstraint("date", "product_id", name="uq_inventory_date_product"),
        Index("ix_inventory_product_date", "product_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    available_stock: Mapped[int] = mapped_column(Integer, default=0)
    inbound_stock: Mapped[int] = mapped_column(Integer, default=0)
    turnover_days: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped[Product] = relationship(back_populates="inventory")


class ProductReview(Base):
    __tablename__ = "product_reviews"
    __table_args__ = (Index("ix_reviews_product_created", "product_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    rating: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (Index("ix_policies_code", "code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80), index=True)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(30))
    forbidden_terms: Mapped[list[str]] = mapped_column(JSON, default=list)
    effective_from: Mapped[date] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    chunks: Mapped[list[PolicyChunk]] = relationship(
        back_populates="policy", cascade="all, delete-orphan"
    )


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"
    __table_args__ = (
        UniqueConstraint("policy_id", "chunk_index", name="uq_policy_chunk_index"),
        Index("ix_policy_chunks_policy_model", "policy_id", "embedding_model"),
        Index(
            "ix_policy_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(
        ForeignKey("policies.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float]] = mapped_column(Vector(256))
    embedding_model: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    policy: Mapped[Policy] = relationship(back_populates="chunks")


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (Index("ix_campaigns_idempotency_key", "idempotency_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    task_id: Mapped[str] = mapped_column(String(50), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    discount_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    budget: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    strategy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ApprovalRecord(Base):
    __tablename__ = "approval_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String(50), index=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    operator: Mapped[str] = mapped_column(String(100))
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_task_node", "task_id", "node"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String(50), index=True)
    node: Mapped[str] = mapped_column(String(80))
    input_digest: Mapped[str] = mapped_column(String(64))
    output_digest: Mapped[str] = mapped_column(String(64))
    latency_ms: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WorkflowTask(Base):
    __tablename__ = "workflow_tasks"
    __table_args__ = (Index("ix_workflow_tasks_thread_id", "thread_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(80), unique=True)
    task_id: Mapped[str] = mapped_column(String(50), index=True)
    workflow_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    request_json: Mapped[dict] = mapped_column(JSON)
    approval_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class WorkflowApproval(Base):
    __tablename__ = "workflow_approvals"
    __table_args__ = (Index("ix_workflow_approvals_thread_id", "thread_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_tasks.thread_id", ondelete="CASCADE"), unique=True
    )
    task_id: Mapped[str] = mapped_column(String(50), index=True)
    operator: Mapped[str] = mapped_column(String(100))
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
