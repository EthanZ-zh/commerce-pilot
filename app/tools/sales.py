from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import Product, SalesDaily
from app.schemas.tools import SalesMetric, SalesQuery


def query_sales_metrics(db: Session, request: SalesQuery) -> list[SalesMetric]:
    statement = (
        select(
            Product.id,
            Product.sku,
            Product.title,
            Product.category,
            Product.region,
            func.coalesce(func.sum(SalesDaily.views), 0).label("views"),
            func.coalesce(func.sum(SalesDaily.clicks), 0).label("clicks"),
            func.coalesce(func.sum(SalesDaily.orders), 0).label("orders"),
            func.coalesce(func.sum(SalesDaily.revenue), 0).label("revenue"),
        )
        .join(SalesDaily, SalesDaily.product_id == Product.id)
        .where(
            Product.category == request.category,
            Product.region == request.region,
            Product.status == "ACTIVE",
            SalesDaily.date >= request.date_from,
            SalesDaily.date <= request.date_to,
        )
        .group_by(Product.id)
        .order_by(func.sum(SalesDaily.orders).asc(), Product.id.asc())
        .limit(request.limit)
    )
    rows = db.execute(statement).all()
    metrics = []
    for row in rows:
        conversion = Decimal("0")
        if row.views:
            conversion = (Decimal(row.orders) / Decimal(row.views)).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        metrics.append(
            SalesMetric(
                product_id=row.id,
                sku=row.sku,
                title=row.title,
                category=row.category,
                region=row.region,
                views=row.views,
                clicks=row.clicks,
                orders=row.orders,
                revenue=Decimal(row.revenue).quantize(Decimal("0.01")),
                conversion_rate=conversion,
            )
        )
    return metrics
