from decimal import Decimal

from app.schemas.tools import DiscountSimulationRequest
from app.tools.pricing import simulate_discount


def test_discount_respects_margin_constraint() -> None:
    result = simulate_discount(
        DiscountSimulationRequest(
            product_id=1,
            cost_price=Decimal("80"),
            sale_price=Decimal("120"),
            max_discount_rate=Decimal("0.30"),
            min_margin_rate=Decimal("0.20"),
        )
    )

    assert result.eligible is True
    assert result.discount_rate <= Decimal("0.30")
    assert result.margin_rate >= Decimal("0.20")
    assert result.discounted_price < result.original_price


def test_discount_rejects_product_below_cost() -> None:
    result = simulate_discount(
        DiscountSimulationRequest(
            product_id=1,
            cost_price=Decimal("120"),
            sale_price=Decimal("100"),
            max_discount_rate=Decimal("0.10"),
            min_margin_rate=Decimal("0.15"),
        )
    )

    assert result.eligible is False
    assert result.discount_rate == 0
