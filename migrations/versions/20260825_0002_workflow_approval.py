"""Add durable workflow tasks and batch approvals."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0002"
down_revision: str | None = "20260825_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.String(80), nullable=False),
        sa.Column("task_id", sa.String(50), nullable=False),
        sa.Column("workflow_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("approval_payload", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("thread_id"),
    )
    op.create_index("ix_workflow_tasks_thread_id", "workflow_tasks", ["thread_id"])
    op.create_index("ix_workflow_tasks_task_id", "workflow_tasks", ["task_id"])
    op.create_index("ix_workflow_tasks_workflow_type", "workflow_tasks", ["workflow_type"])
    op.create_index("ix_workflow_tasks_status", "workflow_tasks", ["status"])

    op.create_table(
        "workflow_approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.String(80), nullable=False),
        sa.Column("task_id", sa.String(50), nullable=False),
        sa.Column("operator", sa.String(100), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["workflow_tasks.thread_id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("thread_id"),
    )
    op.create_index(
        "ix_workflow_approvals_thread_id", "workflow_approvals", ["thread_id"]
    )
    op.create_index("ix_workflow_approvals_task_id", "workflow_approvals", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_approvals_task_id", table_name="workflow_approvals")
    op.drop_index("ix_workflow_approvals_thread_id", table_name="workflow_approvals")
    op.drop_table("workflow_approvals")
    op.drop_index("ix_workflow_tasks_status", table_name="workflow_tasks")
    op.drop_index("ix_workflow_tasks_workflow_type", table_name="workflow_tasks")
    op.drop_index("ix_workflow_tasks_task_id", table_name="workflow_tasks")
    op.drop_index("ix_workflow_tasks_thread_id", table_name="workflow_tasks")
    op.drop_table("workflow_tasks")
