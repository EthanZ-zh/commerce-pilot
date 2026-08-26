from decimal import Decimal

from app.schemas.tools import (
    ComplianceRequest,
    DiscountSimulationResult,
    PolicyEvidence,
)
from app.tools.compliance import check_compliance_rules


def compliant_price() -> DiscountSimulationResult:
    return DiscountSimulationResult(
        product_id=1,
        original_price=Decimal("100"),
        discounted_price=Decimal("80"),
        discount_rate=Decimal("0.20"),
        margin_rate=Decimal("0.25"),
        eligible=True,
        reason="ok",
    )


def policy() -> PolicyEvidence:
    return PolicyEvidence(
        policy_id=1,
        code="AD-1",
        title="广告规则",
        content="不得使用绝对化用语",
        source="test",
        version="1",
        forbidden_terms=["全网第一"],
    )


def test_compliance_rejects_forbidden_term() -> None:
    result = check_compliance_rules(
        ComplianceRequest(
            title="全网第一耳机",
            marketing_copy="限时活动",
            pricing=[compliant_price()],
            policies=[policy()],
            max_discount_rate=Decimal("0.20"),
            min_margin_rate=Decimal("0.15"),
        )
    )

    assert result.passed is False
    assert any("禁用词" in item for item in result.violations)


def test_compliance_accepts_grounded_copy() -> None:
    result = check_compliance_rules(
        ComplianceRequest(
            title="耳机限时活动",
            marketing_copy="具体优惠以活动草稿为准",
            pricing=[compliant_price()],
            policies=[policy()],
            max_discount_rate=Decimal("0.20"),
            min_margin_rate=Decimal("0.15"),
        )
    )

    assert result.passed is True


def test_compliance_rejects_final_interpretation_rights_claim() -> None:
    result = check_compliance_rules(
        ComplianceRequest(
            title="耳机限时活动",
            marketing_copy="最终解释权归平台所有，具体优惠以活动草稿为准。",
            pricing=[compliant_price()],
            policies=[policy()],
            max_discount_rate=Decimal("0.20"),
            min_margin_rate=Decimal("0.15"),
        )
    )

    assert result.passed is False
    assert any("最终解释权" in item for item in result.violations)


def test_compliance_rejects_unsupported_hot_selling_claim() -> None:
    result = check_compliance_rules(
        ComplianceRequest(
            title="高周转潜力爆款耳机",
            marketing_copy="具体优惠以活动草稿为准。",
            pricing=[compliant_price()],
            policies=[policy()],
            max_discount_rate=Decimal("0.20"),
            min_margin_rate=Decimal("0.15"),
        )
    )

    assert result.passed is False
    assert any("高周转潜力" in item for item in result.violations)
    assert any("爆款" in item for item in result.violations)
