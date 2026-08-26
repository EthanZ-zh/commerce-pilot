from sqlalchemy.orm import Session

from app.domain.models import AgentRun, Campaign
from app.evaluation.agent import evaluate_agent_workflow, find_constraint_violations
from app.evaluation.agent_datasets import AGENT_EVALUATION_CASES
from app.llm.providers import DeterministicAgentModelProvider
from app.rag.providers import DeterministicRagProvider
from app.schemas.tools import BaselineWorkflowRequest
from app.workflows.multi_agent import run_multi_agent_workflow


def test_agent_evaluation_scores_scenarios_without_business_writes(
    seeded_db: Session,
) -> None:
    campaign_count = seeded_db.query(Campaign).count()
    audit_count = seeded_db.query(AgentRun).count()

    report = evaluate_agent_workflow(
        seeded_db,
        DeterministicAgentModelProvider(),
        DeterministicRagProvider(),
        AGENT_EVALUATION_CASES,
    )

    assert report.case_count == 6
    assert report.task_success_rate == 1.0
    assert report.constraint_violation_rate == 0.0
    assert report.fallback_rate == 0.0
    assert report.retry_rate == 0.0
    assert report.total_input_tokens == 0
    assert report.total_output_tokens == 0
    assert all(case.task_succeeded for case in report.cases)
    assert seeded_db.query(Campaign).count() == campaign_count
    assert seeded_db.query(AgentRun).count() == audit_count


def test_agent_evaluation_detects_tampered_output(seeded_db: Session) -> None:
    request = BaselineWorkflowRequest(turnover_days_threshold=1, max_products=2)
    result = run_multi_agent_workflow(
        seeded_db,
        request,
        agent_provider=DeterministicAgentModelProvider(),
        rag_provider=DeterministicRagProvider(),
        write_enabled=False,
        persist_audit=False,
    )
    tampered = result.model_copy(
        update={
            "selected_products": [*result.selected_products, result.selected_products[0]],
            "content": {"title": "全网第一", "copy": result.content["copy"]},
        }
    )

    violations = find_constraint_violations(request, tampered)

    assert "入选商品存在重复 ID" in violations
    assert "入选商品数量超过 max_products" in violations
    assert "营销内容包含高风险词: 全网第一" in violations
