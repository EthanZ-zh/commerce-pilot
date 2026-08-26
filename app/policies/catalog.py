from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Policy


@dataclass(frozen=True)
class PolicyDefinition:
    code: str
    title: str
    category: str
    content: str
    forbidden_terms: tuple[str, ...] = ()
    version: str = "2026.2"
    source: str = "CommercePilot 模拟平台规则"
    effective_from: date = date(2026, 1, 1)


POLICY_CATALOG = (
    PolicyDefinition(
        code="PROMO-PRICE-001",
        title="促销价格与毛利规则",
        category="营销",
        content=(
            "促销活动必须保留可审计的原价、折扣率、活动价和毛利率计算。"
            "活动折扣不得超过任务设定的最大折扣率，活动后毛利率不得低于最低毛利率。"
        ),
    ),
    PolicyDefinition(
        code="AD-COPY-001",
        title="营销文案合规规则",
        category="营销",
        content=(
            "营销文案不得使用无法证明的绝对化、最高级或永久承诺，不得用平台保留最终解释权"
            "排除消费者权利。优惠范围和生效条件应以审批后的活动信息为准。"
        ),
        forbidden_terms=("全网第一", "最便宜", "100%", "永久", "最终解释权"),
    ),
    PolicyDefinition(
        code="APPROVAL-001",
        title="营销活动审批规则",
        category="审批",
        content=(
            "自动化系统只能创建活动草稿，不得自动发布。活动发布前必须由授权运营人员"
            "完成人工审批，并记录审批人、结论、理由和时间。"
        ),
    ),
    PolicyDefinition(
        code="BUDGET-001",
        title="营销预算分配规则",
        category="营销",
        content=(
            "营销活动预算必须为正数，并在入选商品之间采用可解释的分配方式。"
            "草稿应记录总预算和单商品预算，执行节点不得突破任务预算。"
        ),
    ),
    PolicyDefinition(
        code="INVENTORY-001",
        title="库存周转语义与选品规则",
        category="营销",
        content=(
            "库存周转天数越高表示库存消化越慢、积压风险越高，不代表热销或高周转潜力。"
            "清库存活动仅可选择达到任务周转天数阈值且具备有效库存快照的商品。"
        ),
        forbidden_terms=("高周转潜力", "热销", "畅销", "爆款"),
    ),
    PolicyDefinition(
        code="REGIONAL-001",
        title="区域营销适用范围规则",
        category="营销",
        content=(
            "区域营销活动只能使用任务指定区域内的商品、销量和库存证据。"
            "活动标题与文案应明确适用区域，不得将区域优惠表述为全国通用。"
        ),
    ),
    PolicyDefinition(
        code="AUDIT-001",
        title="Agent 执行审计规则",
        category="营销",
        content=(
            "Agent 工作流的关键节点必须记录输入摘要、输出摘要、耗时、状态和错误。"
            "模型调用还应记录供应商、模型、输入输出 token、延迟、降级状态与错误原因。"
        ),
    ),
    PolicyDefinition(
        code="DATA-001",
        title="业务证据与模型边界规则",
        category="营销",
        content=(
            "销量、库存、价格和毛利等业务数字必须来自数据库查询或确定性工具。"
            "大模型只负责计划和文案生成，不得捏造业务数字、替换工具结果或修改商品选择。"
        ),
    ),
)


def sync_policy_catalog(db: Session) -> dict[str, int]:
    """Idempotently insert or update catalog policies without deleting user data."""
    codes = [definition.code for definition in POLICY_CATALOG]
    existing = {
        policy.code: policy
        for policy in db.scalars(select(Policy).where(Policy.code.in_(codes))).all()
    }
    created = 0
    updated = 0
    unchanged = 0
    for definition in POLICY_CATALOG:
        values = {
            "title": definition.title,
            "category": definition.category,
            "content": definition.content,
            "source": definition.source,
            "version": definition.version,
            "forbidden_terms": list(definition.forbidden_terms),
            "effective_from": definition.effective_from,
            "expires_at": None,
            "is_active": True,
        }
        policy = existing.get(definition.code)
        if policy is None:
            db.add(Policy(code=definition.code, **values))
            created += 1
            continue
        changed = False
        for field, value in values.items():
            if getattr(policy, field) != value:
                setattr(policy, field, value)
                changed = True
        if changed:
            updated += 1
        else:
            unchanged += 1
    db.flush()
    return {"created": created, "updated": updated, "unchanged": unchanged}
