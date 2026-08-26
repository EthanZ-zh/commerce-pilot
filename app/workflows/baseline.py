from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from functools import partial
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.domain.models import AgentRun
from app.schemas.tools import (
    BaselineWorkflowRequest,
    BaselineWorkflowResult,
    CampaignDraftRequest,
    ComplianceRequest,
    ComplianceResult,
    DiscountSimulationRequest,
    InventoryQuery,
    PolicyQuery,
    SalesQuery,
    TraceEvent,
)
from app.tools.campaigns import create_campaign_draft
from app.tools.compliance import check_compliance_rules
from app.tools.inventory import query_inventory
from app.tools.policy import retrieve_policy
from app.tools.pricing import simulate_discount
from app.tools.sales import query_sales_metrics

T = TypeVar("T")


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


def _execute_node(
    db: Session,
    task_id: str,
    trace: list[TraceEvent],
    node: str,
    input_value: Any,
    operation: Callable[[], T],
) -> T:
    started = time.monotonic()
    try:
        output = operation()
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        trace.append(TraceEvent(node=node, status="ERROR", latency_ms=latency_ms, detail=str(exc)))
        db.add(
            AgentRun(
                task_id=task_id,
                node=node,
                input_digest=_digest(input_value),
                output_digest=_digest({"error": str(exc)}),
                latency_ms=latency_ms,
                status="ERROR",
                error=str(exc),
            )
        )
        raise
    latency_ms = int((time.monotonic() - started) * 1000)
    size = len(output) if isinstance(output, list) else 1
    trace.append(TraceEvent(node=node, status="OK", latency_ms=latency_ms, detail=f"output={size}"))
    db.add(
        AgentRun(
            task_id=task_id,
            node=node,
            input_digest=_digest(input_value),
            output_digest=_digest(output),
            latency_ms=latency_ms,
            status="OK",
        )
    )
    return output


def run_baseline_workflow(db: Session, request: BaselineWorkflowRequest) -> BaselineWorkflowResult:
    request_payload = request.model_dump(mode="json")
    fingerprint = _digest(request_payload)
    task_id = f"task-{fingerprint[:16]}"
    trace: list[TraceEvent] = []

    sales_query = SalesQuery(
        category=request.category,
        region=request.region,
        date_from=request.date_from,
        date_to=request.date_to,
        limit=200,
    )
    sales = _execute_node(
        db,
        task_id,
        trace,
        "query_sales_metrics",
        sales_query,
        lambda: query_sales_metrics(db, sales_query),
    )

    inventory_query = InventoryQuery(
        category=request.category,
        region=request.region,
        turnover_days_threshold=request.turnover_days_threshold,
        limit=200,
    )
    inventory = _execute_node(
        db,
        task_id,
        trace,
        "query_inventory",
        inventory_query,
        lambda: query_inventory(db, inventory_query),
    )

    sales_by_product = {row.product_id: row for row in sales}
    candidate_inventory = [row for row in inventory if row.product_id in sales_by_product][
        : request.max_products
    ]
    candidate_sales = [sales_by_product[row.product_id] for row in candidate_inventory]

    pricing = []
    for item in candidate_inventory:
        pricing_request = DiscountSimulationRequest(
            product_id=item.product_id,
            cost_price=item.cost_price,
            sale_price=item.sale_price,
            max_discount_rate=request.max_discount_rate,
            min_margin_rate=request.min_margin_rate,
        )
        pricing.append(
            _execute_node(
                db,
                task_id,
                trace,
                "simulate_discount",
                pricing_request,
                partial(simulate_discount, pricing_request),
            )
        )

    policy_query = PolicyQuery(category="营销", as_of=request.date_to)
    policies = _execute_node(
        db,
        task_id,
        trace,
        "retrieve_policy",
        policy_query,
        lambda: retrieve_policy(db, policy_query),
    )

    eligible_ids = {row.product_id for row in pricing if row.eligible}
    selected_inventory = [row for row in candidate_inventory if row.product_id in eligible_ids]
    selected_sales = [row for row in candidate_sales if row.product_id in eligible_ids]
    selected_pricing = [row for row in pricing if row.eligible]

    strategy = {
        "goal": request.goal,
        "method": "优先处理高周转天数商品，在最低毛利约束内使用最大可行折扣",
        "selected_product_ids": [row.product_id for row in selected_inventory],
        "max_discount_rate": str(request.max_discount_rate),
        "min_margin_rate": str(request.min_margin_rate),
        "approval_required": True,
    }
    content = {
        "title": f"{request.region}{request.category}库存优化限时活动",
        "copy": (
            f"面向{request.region}地区精选{request.category}商品提供限时优惠，"
            "活动价格经过成本与毛利校验，具体优惠以活动草稿为准。"
        ),
    }

    if selected_pricing:
        compliance_request = ComplianceRequest(
            title=content["title"],
            marketing_copy=content["copy"],
            pricing=selected_pricing,
            policies=policies,
            max_discount_rate=request.max_discount_rate,
            min_margin_rate=request.min_margin_rate,
        )
        compliance = _execute_node(
            db,
            task_id,
            trace,
            "check_compliance_rules",
            compliance_request,
            lambda: check_compliance_rules(compliance_request),
        )
    else:
        compliance = ComplianceResult(
            passed=False,
            violations=["没有同时满足销量、库存和价格约束的候选商品"],
            checked_policy_codes=[policy.code for policy in policies],
        )
        trace.append(
            TraceEvent(
                node="check_compliance_rules",
                status="SKIPPED",
                latency_ms=0,
                detail="no eligible product",
            )
        )

    drafts = []
    if compliance.passed:
        per_product_budget = (request.budget / Decimal(len(selected_pricing))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        for price in selected_pricing:
            idempotency_key = _digest(
                {"task_id": task_id, "product_id": price.product_id, "action": "campaign-draft"}
            )
            draft_request = CampaignDraftRequest(
                task_id=task_id,
                product_id=price.product_id,
                name=content["title"],
                discount_rate=price.discount_rate,
                budget=per_product_budget,
                strategy=strategy,
                idempotency_key=idempotency_key,
            )
            drafts.append(
                _execute_node(
                    db,
                    task_id,
                    trace,
                    "create_campaign_draft",
                    draft_request,
                    partial(create_campaign_draft, db, draft_request),
                )
            )

    db.commit()
    if drafts:
        status = "DRAFT_CREATED"
    elif candidate_inventory:
        status = "REJECTED"
    else:
        status = "NO_CANDIDATES"
    return BaselineWorkflowResult(
        task_id=task_id,
        status=status,
        selected_products=[row.product_id for row in selected_inventory],
        sales_evidence=selected_sales,
        inventory_evidence=selected_inventory,
        pricing=pricing,
        policies=policies,
        strategy=strategy,
        content=content,
        compliance=compliance,
        campaign_drafts=drafts,
        trace=trace,
        created_at=datetime.now(UTC),
    )
