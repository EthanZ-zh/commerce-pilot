from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalCase:
    case_id: str
    query: str
    relevant_codes: frozenset[str]
    category: str = "营销"


POLICY_RETRIEVAL_CASES = (
    RetrievalCase(
        "price-margin",
        "促销折扣不能超过多少，最低毛利如何保证？",
        frozenset({"PROMO-PRICE-001"}),
    ),
    RetrievalCase(
        "copy-claims",
        "文案能写全网第一、永久有效和最终解释权吗？",
        frozenset({"AD-COPY-001"}),
    ),
    RetrievalCase(
        "human-approval",
        "Agent 能否自动发布活动，谁来审批？",
        frozenset({"APPROVAL-001"}),
    ),
    RetrievalCase("budget", "活动总预算和单商品预算应该怎样分配？", frozenset({"BUDGET-001"})),
    RetrievalCase(
        "turnover",
        "库存周转天数高是热销还是积压，选品阈值如何用？",
        frozenset({"INVENTORY-001"}),
    ),
    RetrievalCase("region", "华南区域优惠是否可以宣传为全国通用？", frozenset({"REGIONAL-001"})),
    RetrievalCase("audit", "Agent 节点和模型调用需要记录哪些审计字段？", frozenset({"AUDIT-001"})),
    RetrievalCase(
        "model-boundary",
        "大模型能否自己编造销量库存并修改商品选择？",
        frozenset({"DATA-001"}),
    ),
    RetrievalCase(
        "price-audit-fields",
        "活动价需要保存原价、折扣率和毛利计算过程吗？",
        frozenset({"PROMO-PRICE-001"}),
    ),
    RetrievalCase(
        "price-floor",
        "折后毛利低于任务底线时还能创建促销吗？",
        frozenset({"PROMO-PRICE-001"}),
    ),
    RetrievalCase(
        "copy-superlative",
        "广告标题使用最便宜或者百分百有效是否合规？",
        frozenset({"AD-COPY-001"}),
    ),
    RetrievalCase(
        "copy-conditions",
        "营销文案应该如何说明优惠范围和生效条件？",
        frozenset({"AD-COPY-001"}),
    ),
    RetrievalCase(
        "approval-draft-only",
        "自动化程序是否只能保存草稿而不能上线？",
        frozenset({"APPROVAL-001"}),
    ),
    RetrievalCase(
        "approval-audit",
        "人工批准需要记录审批人、结论、理由和时间吗？",
        frozenset({"APPROVAL-001"}),
    ),
    RetrievalCase(
        "budget-positive",
        "营销预算可以是零或负数吗？",
        frozenset({"BUDGET-001"}),
    ),
    RetrievalCase(
        "budget-cap",
        "单品预算相加能否突破任务总预算？",
        frozenset({"BUDGET-001"}),
    ),
    RetrievalCase(
        "inventory-slow-moving",
        "周转天数达到一百天说明卖得快还是消化缓慢？",
        frozenset({"INVENTORY-001"}),
    ),
    RetrievalCase(
        "inventory-snapshot",
        "清库存选品是否必须具有有效库存快照？",
        frozenset({"INVENTORY-001"}),
    ),
    RetrievalCase(
        "region-evidence",
        "区域活动能否引用其他地区的销量和库存数据？",
        frozenset({"REGIONAL-001"}),
    ),
    RetrievalCase(
        "region-copy",
        "地区专属活动的标题文案是否需要明确适用地区？",
        frozenset({"REGIONAL-001"}),
    ),
    RetrievalCase(
        "audit-node",
        "工作流每个关键节点要保存哪些输入输出审计信息？",
        frozenset({"AUDIT-001"}),
    ),
    RetrievalCase(
        "audit-model-cost",
        "模型降级后还要保留 token、耗时和失败原因吗？",
        frozenset({"AUDIT-001"}),
    ),
    RetrievalCase(
        "data-source",
        "价格毛利库存等数字应该由语言模型还是确定性工具提供？",
        frozenset({"DATA-001"}),
    ),
    RetrievalCase(
        "data-selection",
        "策略模型是否有权替换工具筛选出的商品集合？",
        frozenset({"DATA-001"}),
    ),
)
