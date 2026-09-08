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
    # ---- 以下为真实电商平台规范摘录（区别于上方自研模拟规则） ----
    # 语义定位于"平台合规知识"，独立 category（平台规范）使营销/审批检索不受影响；
    # 调用方可按 category="平台规范" 单独检索以做真实合规核对。摘录自官方公示文本，
    # 仅供开发运行与检索验证，不代表平台官方口径的完整条文。
    PolicyDefinition(
        code="TAOBAO-PRICE-001",
        title="淘宝平台价格发布规范（摘录）",
        category="平台规范",
        content=(
            "商家发布商品填写的所有价格应严格遵守法律规定、遵循市场规律，"
            "可提供合法依据或可比较的出处，不得实施价格欺诈。未销售过的商品"
            "不得使用“原售价/成交价/折/新品折”等暗示已有成交记录的概念；"
            "不得在商品标题、图片、描述及其他宣传中出现“原价”字样，违者平台"
            "将对该商品或信息做下架处理。参加平台促销活动须标示真实有效的"
            "被比较价格与真实优惠的促销价；促销承诺有效期内不得擅自提价或"
            "提前结束，有数量限制的须明示参加促销的商品数量。"
        ),
        source="《淘宝平台价格发布规范》rule.taobao.com/detail-4829.htm",
    ),
    PolicyDefinition(
        code="TAOBAO-AD-001",
        title="淘宝绝对化用语与夸大宣传规范（摘录）",
        category="平台规范",
        content=(
            "商品标题、导购标题、SKU 名称、卖点及主图等信息应与实际情况相符，"
            "不得杜撰或夸大商品功能、参数、效果，不得虚构销量或认证信息。"
            "不得使用“最好/第一/国家级/全网唯一/史上最强/100%/永久有效”等"
            "《广告法》禁止的绝对化用语与极限词，亦不得使用谐音、变体等方式"
            "规避审查。平台对不实宣传与夸大承诺按规则采取扣分、降权、下架、"
            "限制发布乃至屏蔽店铺等处置措施。"
        ),
        source="淘宝商家服务大厅违规词治理 helpcenter.taobao.com/learn/knowledge?id=20119776",
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
