from __future__ import annotations

import hashlib
import json
import operator
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.domain.models import AgentRun
from app.llm.providers import (
    AgentModelProvider,
    DeterministicAgentModelProvider,
    get_agent_model_provider,
)
from app.rag.providers import RagProvider
from app.schemas.tools import (
    BaselineWorkflowRequest,
    CampaignDraftRequest,
    CampaignDraftResult,
    ComplianceRequest,
    ComplianceResult,
    DiscountSimulationRequest,
    DiscountSimulationResult,
    InventoryItem,
    InventoryQuery,
    ModelCallTrace,
    MultiAgentWorkflowResult,
    PolicyEvidence,
    PolicyQuery,
    SalesMetric,
    SalesQuery,
    TraceEvent,
)
from app.telemetry import get_tracer
from app.tools.campaigns import create_campaign_draft
from app.tools.compliance import check_compliance_rules
from app.tools.inventory import query_inventory
from app.tools.policy import retrieve_policy
from app.tools.pricing import simulate_discount
from app.tools.sales import query_sales_metrics

PARALLEL_WORKERS = ["business_analyst", "inventory_pricing", "policy_rag"]
WORKFLOW_VERSION = "multi-agent-v5-evaluated-rag-routing"
NODE_ORDER = [
    "supervisor",
    *PARALLEL_WORKERS,
    "strategy_planner",
    "compliance_reviewer",
    "execution_service",
]


class AgentAudit(TypedDict):
    node: str
    input_digest: str
    output_digest: str
    latency_ms: int
    status: str
    detail: str
    error: str | None


class MultiAgentState(TypedDict, total=False):
    request: BaselineWorkflowRequest
    task_id: str
    supervisor_plan: list[str]
    sales_evidence: list[SalesMetric]
    inventory_candidates: list[InventoryItem]
    pricing_candidates: list[DiscountSimulationResult]
    policies: list[PolicyEvidence]
    selected_products: list[int]
    selected_sales: list[SalesMetric]
    selected_inventory: list[InventoryItem]
    pricing: list[DiscountSimulationResult]
    candidate_count: int
    strategy: dict[str, Any]
    content: dict[str, str]
    compliance: ComplianceResult
    approval_decision: str
    approval_operator: str
    approval_reason: str
    terminal_status: str
    campaign_drafts: list[CampaignDraftResult]
    audit_events: Annotated[list[AgentAudit], operator.add]
    model_calls: Annotated[list[ModelCallTrace], operator.add]


@dataclass(frozen=True)
class WorkflowContext:
    session_factory: sessionmaker[Session]
    agent_provider: AgentModelProvider
    rag_provider: RagProvider | None = None
    write_enabled: bool = True


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _digest(value: Any) -> str:
    payload = json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _audit(
    node: str,
    input_value: Any,
    output: Any,
    started: float,
    *,
    detail: str | None = None,
) -> AgentAudit:
    size = len(output) if isinstance(output, list | dict) else 1
    return AgentAudit(
        node=node,
        input_digest=_digest(input_value),
        output_digest=_digest(output),
        latency_ms=int((time.monotonic() - started) * 1000),
        status="OK",
        detail=detail or f"output={size}",
        error=None,
    )


def supervisor(
    state: MultiAgentState, runtime: Runtime[WorkflowContext]
) -> dict[str, Any]:
    started = time.monotonic()
    decision, model_call = runtime.context.agent_provider.supervise(state["request"])
    output = {"supervisor_plan": decision.plan}
    detail = (
        f"provider={model_call.provider}; model={model_call.model}; "
        f"tokens={model_call.input_tokens + model_call.output_tokens}; "
        f"fallback={model_call.fallback_used}"
    )
    return {
        **output,
        "model_calls": [model_call],
        "audit_events": [
            _audit("supervisor", state["request"], decision, started, detail=detail)
        ],
    }


def business_analyst(
    state: MultiAgentState, runtime: Runtime[WorkflowContext]
) -> dict[str, Any]:
    started = time.monotonic()
    request = state["request"]
    query = SalesQuery(
        category=request.category,
        region=request.region,
        date_from=request.date_from,
        date_to=request.date_to,
        limit=200,
    )
    with runtime.context.session_factory() as db:
        sales = query_sales_metrics(db, query)
    return {
        "sales_evidence": sales,
        "audit_events": [_audit("business_analyst", query, sales, started)],
    }


def inventory_pricing(
    state: MultiAgentState, runtime: Runtime[WorkflowContext]
) -> dict[str, Any]:
    started = time.monotonic()
    request = state["request"]
    query = InventoryQuery(
        category=request.category,
        region=request.region,
        turnover_days_threshold=request.turnover_days_threshold,
        limit=200,
    )
    with runtime.context.session_factory() as db:
        inventory = query_inventory(db, query)
    pricing = [
        simulate_discount(
            DiscountSimulationRequest(
                product_id=item.product_id,
                cost_price=item.cost_price,
                sale_price=item.sale_price,
                max_discount_rate=request.max_discount_rate,
                min_margin_rate=request.min_margin_rate,
            )
        )
        for item in inventory
    ]
    output = {"inventory_candidates": inventory, "pricing_candidates": pricing}
    return {
        **output,
        "audit_events": [_audit("inventory_pricing", query, output, started)],
    }


def policy_rag(state: MultiAgentState, runtime: Runtime[WorkflowContext]) -> dict[str, Any]:
    started = time.monotonic()
    request = state["request"]
    query = PolicyQuery(
        category="营销",
        query_text=(
            f"{request.goal}；{request.category}促销价格、最低毛利、营销文案和人工审批规则"
        ),
        as_of=request.date_to,
    )
    with runtime.context.session_factory() as db:
        policies = retrieve_policy(db, query, runtime.context.rag_provider)
    return {
        "policies": policies,
        "audit_events": [_audit("policy_rag", query, policies, started)],
    }


def strategy_planner(
    state: MultiAgentState, runtime: Runtime[WorkflowContext]
) -> dict[str, Any]:
    started = time.monotonic()
    request = state["request"]
    sales_by_product = {row.product_id: row for row in state["sales_evidence"]}
    pricing_by_product = {row.product_id: row for row in state["pricing_candidates"]}
    candidates = [
        row
        for row in state["inventory_candidates"]
        if row.product_id in sales_by_product
    ][: request.max_products]
    eligible_inventory = [
        row for row in candidates if pricing_by_product[row.product_id].eligible
    ]
    selected_ids = [row.product_id for row in eligible_inventory]
    pricing = [pricing_by_product[row.product_id] for row in candidates]
    evidence = {
        "task": {
            "goal": request.goal,
            "category": request.category,
            "region": request.region,
            "max_discount_rate": str(request.max_discount_rate),
            "min_margin_rate": str(request.min_margin_rate),
            "budget": str(request.budget),
        },
        "products": [
            {
                "product_id": row.product_id,
                "orders": sales_by_product[row.product_id].orders,
                "conversion_rate": str(
                    sales_by_product[row.product_id].conversion_rate
                ),
                "available_stock": row.available_stock,
                "turnover_days": row.turnover_days,
                "original_price": str(pricing_by_product[row.product_id].original_price),
                "discounted_price": str(
                    pricing_by_product[row.product_id].discounted_price
                ),
                "discount_rate": str(pricing_by_product[row.product_id].discount_rate),
                "margin_rate": str(pricing_by_product[row.product_id].margin_rate),
            }
            for row in eligible_inventory
        ],
        "policies": [
            {
                "code": policy.code,
                "rule": policy.content[:300],
                "forbidden_terms": policy.forbidden_terms,
            }
            for policy in state["policies"]
        ],
    }
    provider = (
        runtime.context.agent_provider
        if selected_ids
        else DeterministicAgentModelProvider()
    )
    decision, model_call = provider.plan_strategy(evidence)
    strategy = {
        "goal": request.goal,
        "method": decision.method,
        "rationale": decision.rationale,
        "selected_product_ids": selected_ids,
        "max_discount_rate": str(request.max_discount_rate),
        "min_margin_rate": str(request.min_margin_rate),
        "approval_required": True,
        "evidence_agents": PARALLEL_WORKERS,
        "generated_by": {
            "provider": model_call.provider,
            "model": model_call.model,
            "fallback_used": model_call.fallback_used,
        },
    }
    content = {
        "title": decision.title,
        "copy": decision.marketing_copy,
    }
    output = {
        "selected_products": selected_ids,
        "selected_sales": [sales_by_product[product_id] for product_id in selected_ids],
        "selected_inventory": eligible_inventory,
        "pricing": pricing,
        "candidate_count": len(candidates),
        "strategy": strategy,
        "content": content,
    }
    return {
        **output,
        "model_calls": [model_call],
        "audit_events": [
            _audit(
                "strategy_planner",
                evidence,
                output,
                started,
                detail=(
                    f"provider={model_call.provider}; model={model_call.model}; "
                    f"tokens={model_call.input_tokens + model_call.output_tokens}; "
                    f"fallback={model_call.fallback_used}"
                ),
            )
        ],
    }


def compliance_reviewer(state: MultiAgentState) -> dict[str, Any]:
    started = time.monotonic()
    eligible_ids = set(state["selected_products"])
    eligible_pricing = [row for row in state["pricing"] if row.product_id in eligible_ids]
    compliance_input: ComplianceRequest | dict[str, list[int]]
    if eligible_pricing:
        request = state["request"]
        compliance_input = ComplianceRequest(
            title=state["content"]["title"],
            marketing_copy=state["content"]["copy"],
            pricing=eligible_pricing,
            policies=state["policies"],
            max_discount_rate=request.max_discount_rate,
            min_margin_rate=request.min_margin_rate,
        )
        compliance = check_compliance_rules(compliance_input)
    else:
        compliance_input = {"selected_products": []}
        compliance = ComplianceResult(
            passed=False,
            violations=["没有同时满足销量、库存和价格约束的候选商品"],
            checked_policy_codes=[policy.code for policy in state["policies"]],
        )
    return {
        "compliance": compliance,
        "audit_events": [
            _audit("compliance_reviewer", compliance_input, compliance, started)
        ],
    }


def execution_service(
    state: MultiAgentState, runtime: Runtime[WorkflowContext]
) -> dict[str, Any]:
    started = time.monotonic()
    request = state["request"]
    drafts: list[CampaignDraftResult] = []
    if (
        runtime.context.write_enabled
        and state["compliance"].passed
        and state["selected_products"]
    ):
        pricing_by_product = {row.product_id: row for row in state["pricing"]}
        per_product_budget = (request.budget / Decimal(len(state["selected_products"]))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        with runtime.context.session_factory() as db:
            for product_id in state["selected_products"]:
                price = pricing_by_product[product_id]
                idempotency_key = _digest(
                    {
                        "task_id": state["task_id"],
                        "product_id": product_id,
                        "action": "multi-agent-campaign-draft",
                    }
                )
                draft_request = CampaignDraftRequest(
                    task_id=state["task_id"],
                    product_id=product_id,
                    name=state["content"]["title"],
                    discount_rate=price.discount_rate,
                    budget=per_product_budget,
                    strategy=state["strategy"],
                    idempotency_key=idempotency_key,
                )
                drafts.append(create_campaign_draft(db, draft_request))
            db.commit()
    return {
        "campaign_drafts": drafts,
        "audit_events": [
            _audit("execution_service", state["compliance"], drafts, started)
        ],
    }


def build_multi_agent_graph():
    builder = StateGraph(MultiAgentState, context_schema=WorkflowContext)
    builder.add_node("supervisor", supervisor)
    builder.add_node("business_analyst", business_analyst)
    builder.add_node("inventory_pricing", inventory_pricing)
    builder.add_node("policy_rag", policy_rag)
    builder.add_node("strategy_planner", strategy_planner)
    builder.add_node("compliance_reviewer", compliance_reviewer)
    builder.add_node("execution_service", execution_service)
    builder.add_edge(START, "supervisor")
    for worker in PARALLEL_WORKERS:
        builder.add_edge("supervisor", worker)
    builder.add_edge(PARALLEL_WORKERS, "strategy_planner")
    builder.add_edge("strategy_planner", "compliance_reviewer")
    builder.add_edge("compliance_reviewer", "execution_service")
    builder.add_edge("execution_service", END)
    return builder.compile(name="commerce-pilot-supervisor-worker")


MULTI_AGENT_GRAPH = build_multi_agent_graph()


def _run_multi_agent_workflow(
    db: Session,
    request: BaselineWorkflowRequest,
    *,
    agent_provider: AgentModelProvider | None = None,
    rag_provider: RagProvider | None = None,
    write_enabled: bool = True,
    persist_audit: bool = True,
) -> MultiAgentWorkflowResult:
    fingerprint_input = {
        "workflow": WORKFLOW_VERSION,
        **request.model_dump(mode="json"),
    }
    if not write_enabled:
        fingerprint_input["evaluation"] = True
    fingerprint = _digest(fingerprint_input)
    task_id = f"agent-{fingerprint[:16]}"
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    state = cast(
        MultiAgentState,
        MULTI_AGENT_GRAPH.invoke(
            {
                "request": request,
                "task_id": task_id,
                "audit_events": [],
                "model_calls": [],
            },
            context=WorkflowContext(
                session_factory=factory,
                agent_provider=agent_provider or get_agent_model_provider(),
                rag_provider=rag_provider,
                write_enabled=write_enabled,
            ),
        ),
    )
    order = {node: index for index, node in enumerate(NODE_ORDER)}
    audits = sorted(state["audit_events"], key=lambda item: order[item["node"]])
    if persist_audit:
        for event in audits:
            db.add(
                AgentRun(
                    task_id=task_id,
                    node=event["node"],
                    input_digest=event["input_digest"],
                    output_digest=event["output_digest"],
                    latency_ms=event["latency_ms"],
                    status=event["status"],
                    error=event["error"],
                )
            )
        db.commit()
    drafts = state["campaign_drafts"]
    if not write_enabled and state["compliance"].passed and state["selected_products"]:
        status = "EVALUATED"
    elif drafts:
        status = "DRAFT_CREATED"
    elif state["candidate_count"]:
        status = "REJECTED"
    else:
        status = "NO_CANDIDATES"
    return MultiAgentWorkflowResult(
        task_id=task_id,
        status=status,
        execution_mode="langgraph_supervisor_worker",
        supervisor_plan=state["supervisor_plan"],
        parallel_workers=PARALLEL_WORKERS,
        model_calls=state["model_calls"],
        selected_products=state["selected_products"],
        sales_evidence=state["selected_sales"],
        inventory_evidence=state["selected_inventory"],
        pricing=state["pricing"],
        policies=state["policies"],
        strategy=state["strategy"],
        content=state["content"],
        compliance=state["compliance"],
        campaign_drafts=drafts,
        trace=[
            TraceEvent(
                node=event["node"],
                status=event["status"],
                latency_ms=event["latency_ms"],
                detail=event["detail"],
            )
            for event in audits
        ],
        created_at=datetime.now(UTC),
    )


def run_multi_agent_workflow(
    db: Session,
    request: BaselineWorkflowRequest,
    *,
    agent_provider: AgentModelProvider | None = None,
    rag_provider: RagProvider | None = None,
    write_enabled: bool = True,
    persist_audit: bool = True,
) -> MultiAgentWorkflowResult:
    with get_tracer().start_as_current_span(
        "commerce_pilot.workflow.multi_agent",
        attributes={
            "commerce_pilot.workflow.version": WORKFLOW_VERSION,
            "commerce_pilot.workflow.category": request.category,
            "commerce_pilot.workflow.region": request.region,
            "commerce_pilot.workflow.max_products": request.max_products,
            "commerce_pilot.workflow.write_enabled": write_enabled,
        },
    ) as span:
        try:
            result = _run_multi_agent_workflow(
                db,
                request,
                agent_provider=agent_provider,
                rag_provider=rag_provider,
                write_enabled=write_enabled,
                persist_audit=persist_audit,
            )
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise
        span.set_attribute("commerce_pilot.task_id", result.task_id)
        span.set_attribute("commerce_pilot.workflow.status", result.status)
        span.set_attribute(
            "commerce_pilot.workflow.selected_products", len(result.selected_products)
        )
        span.set_attribute(
            "commerce_pilot.workflow.input_tokens",
            sum(call.input_tokens for call in result.model_calls),
        )
        span.set_attribute(
            "commerce_pilot.workflow.output_tokens",
            sum(call.output_tokens for call in result.model_calls),
        )
        span.set_attribute(
            "commerce_pilot.workflow.fallback_count",
            sum(call.fallback_used for call in result.model_calls),
        )
        span.set_attribute(
            "commerce_pilot.workflow.retry_count",
            sum(call.attempts - 1 for call in result.model_calls),
        )
        return result
