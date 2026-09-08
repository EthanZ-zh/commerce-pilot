"""把选定平台的店铺数据同步到 CommercePilot 的规范业务表。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date

from app.config import get_settings
from app.infrastructure.database import SessionLocal
from app.platform.factory import demo_credentials, get_shop_gateway
from app.platform.sync import PlatformSyncReport, sync_shop_data


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("日期必须为 YYYY-MM-DD") from error


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="同步平台店铺数据到本地业务表")
    parser.add_argument("--date-from", required=True, type=_parse_date)
    parser.add_argument("--date-to", required=True, type=_parse_date)
    return parser


def _print_report(report: PlatformSyncReport) -> None:
    print(
        "platform sync: "
        f"products_updated={report.products_updated} "
        f"sales_rows_updated={report.sales_rows_updated} "
        f"inventory_rows_updated={report.inventory_rows_updated} "
        f"unknown_skus={len(report.unknown_skus)} "
        f"inventory_skipped_skus={len(report.inventory_skipped_skus)}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.date_from > args.date_to:
        _build_parser().error("--date-from must not be after --date-to")
    settings = get_settings()
    credentials = demo_credentials(settings)
    with SessionLocal() as db:
        report = sync_shop_data(
            db,
            get_shop_gateway(db, settings),
            credentials,
            date_from=args.date_from,
            date_to=args.date_to,
            snapshot_date=args.date_to,
        )
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
