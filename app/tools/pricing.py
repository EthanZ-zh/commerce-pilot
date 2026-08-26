from decimal import ROUND_HALF_UP, Decimal

from app.schemas.tools import DiscountSimulationRequest, DiscountSimulationResult

RATE_QUANT = Decimal("0.0001")
MONEY_QUANT = Decimal("0.01")


def simulate_discount(request: DiscountSimulationRequest) -> DiscountSimulationResult:
    if request.cost_price >= request.sale_price:
        return DiscountSimulationResult(
            product_id=request.product_id,
            original_price=request.sale_price,
            discounted_price=request.sale_price,
            discount_rate=Decimal("0"),
            margin_rate=((request.sale_price - request.cost_price) / request.sale_price).quantize(
                RATE_QUANT, rounding=ROUND_HALF_UP
            ),
            eligible=False,
            reason="原价不高于成本价，无法在正毛利下促销",
        )

    margin_denominator = request.sale_price * (Decimal("1") - request.min_margin_rate)
    max_discount_by_margin = Decimal("1") - request.cost_price / margin_denominator
    applied_discount = max(
        Decimal("0"), min(request.max_discount_rate, max_discount_by_margin)
    ).quantize(RATE_QUANT, rounding=ROUND_HALF_UP)
    discounted_price = (request.sale_price * (Decimal("1") - applied_discount)).quantize(
        MONEY_QUANT, rounding=ROUND_HALF_UP
    )
    margin_rate = ((discounted_price - request.cost_price) / discounted_price).quantize(
        RATE_QUANT, rounding=ROUND_HALF_UP
    )
    eligible = discounted_price > request.cost_price and margin_rate >= request.min_margin_rate
    reason = "满足折扣和最低毛利约束" if eligible else "无法同时满足折扣和最低毛利约束"
    return DiscountSimulationResult(
        product_id=request.product_id,
        original_price=request.sale_price,
        discounted_price=discounted_price,
        discount_rate=applied_discount,
        margin_rate=margin_rate,
        eligible=eligible,
        reason=reason,
    )
