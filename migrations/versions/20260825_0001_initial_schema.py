"""Initial CommercePilot schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sku", sa.String(40), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("region", sa.String(40), nullable=False),
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("sale_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("sku"),
    )
    op.create_index("ix_products_sku", "products", ["sku"])
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_region", "products", ["region"])
    op.create_index("ix_products_status", "products", ["status"])

    op.create_table(
        "policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("version", sa.String(30), nullable=False),
        sa.Column("forbidden_terms", sa.JSON(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_policies_code", "policies", ["code"])
    op.create_index("ix_policies_category", "policies", ["category"])
    op.create_index("ix_policies_is_active", "policies", ["is_active"])

    op.create_table(
        "sales_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.Column("orders", sa.Integer(), nullable=False),
        sa.Column("revenue", sa.Numeric(14, 2), nullable=False),
        sa.UniqueConstraint("date", "product_id", name="uq_sales_date_product"),
    )
    op.create_index("ix_sales_daily_date", "sales_daily", ["date"])
    op.create_index("ix_sales_product_date", "sales_daily", ["product_id", "date"])

    op.create_table(
        "inventory_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("available_stock", sa.Integer(), nullable=False),
        sa.Column("inbound_stock", sa.Integer(), nullable=False),
        sa.Column("turnover_days", sa.Integer(), nullable=False),
        sa.UniqueConstraint("date", "product_id", name="uq_inventory_date_product"),
    )
    op.create_index("ix_inventory_snapshots_date", "inventory_snapshots", ["date"])
    op.create_index("ix_inventory_product_date", "inventory_snapshots", ["product_id", "date"])

    op.create_table(
        "product_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reviews_product_created", "product_reviews", ["product_id", "created_at"])

    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("task_id", sa.String(50), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("discount_rate", sa.Numeric(6, 4), nullable=False),
        sa.Column("budget", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("strategy_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_campaigns_idempotency_key", "campaigns", ["idempotency_key"])
    op.create_index("ix_campaigns_task_id", "campaigns", ["task_id"])
    op.create_index("ix_campaigns_product_id", "campaigns", ["product_id"])
    op.create_index("ix_campaigns_status", "campaigns", ["status"])

    op.create_table(
        "approval_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(50), nullable=False),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("operator", sa.String(100), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_approval_records_task_id", "approval_records", ["task_id"])
    op.create_index("ix_approval_records_campaign_id", "approval_records", ["campaign_id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(50), nullable=False),
        sa.Column("node", sa.String(80), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("output_digest", sa.String(64), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_runs_task_id", "agent_runs", ["task_id"])
    op.create_index("ix_agent_runs_task_node", "agent_runs", ["task_id", "node"])


def downgrade() -> None:
    op.drop_table("agent_runs")
    op.drop_table("approval_records")
    op.drop_table("campaigns")
    op.drop_table("product_reviews")
    op.drop_table("inventory_snapshots")
    op.drop_table("sales_daily")
    op.drop_table("policies")
    op.drop_table("products")
