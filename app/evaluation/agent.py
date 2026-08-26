from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.evaluation.agent_datasets import AgentEvaluationCase, ExpectedOutcome
from app.llm.providers import AgentModelProvider
from app.rag.providers import RagProvider
from app.schemas.tools import BaselineWorkflowRequest, MultiAgentWorkflowResult
from app.workflows.multi_agent import run_multi_agent_workflow

HIGH_RISK_TERMS = (
    "全网第一",
    "最便宜",
    "100%",
    "永久",
    "最终解释权",
    "高周转潜力",
    "热销",
    "畅销",
    "爆款",
)


@dataclass(frozen=True)
class AgentCaseResult:
    case_id: str
    expected_outcome: ExpectedOutcome
    actual_outcome: ExpectedOutcome
    task_succeeded: bool
    violations: tuple[str, ...]
    selected_products: int
    model_calls: int
    models: tuple[str, ...]
    model_attempts: int
    fallback_calls: int
    fallback_errors: tuple[str, ...]
    input_tokens: int
    output_tokens: int
    model_latency_ms: int


@dataclass(frozen=True)
class AgentEvaluation:
    case_count: int
    task_success_rate: float
    constraint_violation_rate: float
    fallback_rate: float
    retry_rate: float
    total_input_tokens: int
    total_output_tokens: int
    average_model_latency_ms: float
    cases: tuple[AgentCaseResult, ...]


def _outcome(result: MultiAgentWorkflowResult) -> ExpectedOutcome:
    if result.status == "EVALUATED":
        return "ready"
    if result.status == "NO_CANDIDATES":
        return "no_candidates"
    return "rejected"


def find_constraint_violations(
    request: BaselineWorkflowRequest,
    result: MultiAgentWorkflowResult,
) -> list[str]:
    violations: list[str] = []
    selected = set(result.selected_products)
    if len(selected) != len(result.selected_products):
        violations.append("入选商品存在重复 ID")
    if len(result.selected_products) > request.max_products:
        violations.append("入选商品数量超过 max_products")
    sales_by_id = {item.product_id: item for item in result.sales_evidence}
    inventory_by_id = {item.product_id: item for item in result.inventory_evidence}
    pricing_by_id = {item.product_id: item for item in result.pricing}
    for product_id in selected:
        sales = sales_by_id.get(product_id)
        inventory = inventory_by_id.get(product_id)
        pricing = pricing_by_id.get(product_id)
        if sales is None or inventory is None or pricing is None:
            violations.append(f"商品 {product_id} 缺少完整工具证据")
            continue
        if sales.category != request.category or sales.region != request.region:
            violations.append(f"商品 {product_id} 超出类目或区域范围")
        if inventory.turnover_days < request.turnover_days_threshold:
            violations.append(f"商品 {product_id} 未达到周转天数阈值")
        if not pricing.eligible:
            violations.append(f"商品 {product_id} 的确定性定价不可用")
        if pricing.discount_rate > request.max_discount_rate:
            violations.append(f"商品 {product_id} 折扣超过任务上限")
        if pricing.margin_rate < request.min_margin_rate:
            violations.append(f"商品 {product_id} 毛利低于任务下限")
    content = f"{result.content.get('title', '')}\n{result.content.get('copy', '')}"
    for term in HIGH_RISK_TERMS:
        if term in content:
            violations.append(f"营销内容包含高风险词: {term}")
    if result.campaign_drafts:
        violations.append("dry-run 评测产生了活动草稿")
    if selected and not result.compliance.passed:
        violations.append("存在入选商品但合规复核未通过")
    return violations


def evaluate_agent_workflow(
    db: Session,
    agent_provider: AgentModelProvider,
    rag_provider: RagProvider,
    cases: tuple[AgentEvaluationCase, ...],
) -> AgentEvaluation:
    if not cases:
        raise ValueError("Agent 评测集不能为空")
    case_results: list[AgentCaseResult] = []
    for case in cases:
        result = run_multi_agent_workflow(
            db,
            case.request,
            agent_provider=agent_provider,
            rag_provider=rag_provider,
            write_enabled=False,
            persist_audit=False,
        )
        actual = _outcome(result)
        violations = find_constraint_violations(case.request, result)
        calls = result.model_calls
        case_results.append(
            AgentCaseResult(
                case_id=case.case_id,
                expected_outcome=case.expected_outcome,
                actual_outcome=actual,
                task_succeeded=actual == case.expected_outcome and not violations,
                violations=tuple(violations),
                selected_products=len(result.selected_products),
                model_calls=len(calls),
                models=tuple(f"{call.node}:{call.model}" for call in calls),
                model_attempts=sum(call.attempts for call in calls),
                fallback_calls=sum(call.fallback_used for call in calls),
                fallback_errors=tuple(
                    f"{call.node}: {call.error}"
                    for call in calls
                    if call.fallback_used and call.error
                ),
                input_tokens=sum(call.input_tokens for call in calls),
                output_tokens=sum(call.output_tokens for call in calls),
                model_latency_ms=sum(call.latency_ms for call in calls),
            )
        )
    case_count = len(case_results)
    call_count = sum(item.model_calls for item in case_results)
    return AgentEvaluation(
        case_count=case_count,
        task_success_rate=sum(item.task_succeeded for item in case_results) / case_count,
        constraint_violation_rate=(
            sum(bool(item.violations) for item in case_results) / case_count
        ),
        fallback_rate=(
            sum(item.fallback_calls for item in case_results) / call_count
            if call_count
            else 0.0
        ),
        retry_rate=(
            sum(item.model_attempts - item.model_calls for item in case_results)
            / call_count
            if call_count
            else 0.0
        ),
        total_input_tokens=sum(item.input_tokens for item in case_results),
        total_output_tokens=sum(item.output_tokens for item in case_results),
        average_model_latency_ms=(
            sum(item.model_latency_ms for item in case_results) / call_count
            if call_count
            else 0.0
        ),
        cases=tuple(case_results),
    )
