from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.models import AgentRun, Campaign
from app.schemas.tools import BaselineWorkflowRequest
from app.workflows.multi_agent import (
    MULTI_AGENT_GRAPH,
    NODE_ORDER,
    PARALLEL_WORKERS,
    run_multi_agent_workflow,
)


def test_multi_agent_graph_has_parallel_fan_out_and_join() -> None:
    edges = {(edge.source, edge.target) for edge in MULTI_AGENT_GRAPH.get_graph().edges}

    for worker in PARALLEL_WORKERS:
        assert ("supervisor", worker) in edges
        assert (worker, "strategy_planner") in edges


def test_multi_agent_workflow_runs_supervisor_workers_and_is_idempotent(
    seeded_db: Session,
) -> None:
    request = BaselineWorkflowRequest(
        category="耳机",
        region="华南",
        turnover_days_threshold=1,
        max_discount_rate=Decimal("0.20"),
        min_margin_rate=Decimal("0.15"),
        max_products=3,
    )

    first = run_multi_agent_workflow(seeded_db, request)
    second = run_multi_agent_workflow(seeded_db, request)

    assert first.execution_mode == "langgraph_supervisor_worker"
    assert first.parallel_workers == PARALLEL_WORKERS
    assert [call.node for call in first.model_calls] == ["supervisor", "strategy_planner"]
    assert all(call.provider == "deterministic" for call in first.model_calls)
    assert [event.node for event in first.trace] == NODE_ORDER
    assert first.status == "DRAFT_CREATED"
    assert first.compliance.passed is True
    assert all(draft.status == "DRAFT" for draft in first.campaign_drafts)
    assert all(draft.created is False for draft in second.campaign_drafts)
    assert seeded_db.query(Campaign).count() == len(first.campaign_drafts)
    assert seeded_db.query(AgentRun).count() == len(NODE_ORDER) * 2


def test_multi_agent_workflow_handles_missing_candidates(seeded_db: Session) -> None:
    result = run_multi_agent_workflow(
        seeded_db,
        BaselineWorkflowRequest(category="不存在的类目", region="华南"),
    )

    assert result.status == "NO_CANDIDATES"
    assert result.campaign_drafts == []
    assert result.compliance.passed is False
    assert [event.node for event in result.trace] == NODE_ORDER
