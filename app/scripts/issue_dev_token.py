from __future__ import annotations

import argparse
from typing import cast

from app.config import get_settings
from app.security import KNOWN_ROLES, Role, create_access_token


def main() -> None:
    parser = argparse.ArgumentParser(description="签发 CommercePilot 本地开发 JWT")
    parser.add_argument("--subject", required=True)
    parser.add_argument(
        "--roles",
        nargs="+",
        required=True,
        choices=sorted(KNOWN_ROLES),
    )
    args = parser.parse_args()
    settings = get_settings()
    if settings.app_env == "production":
        parser.error("生产环境禁止使用本地开发 Token 签发脚本")
    roles = {cast(Role, role) for role in args.roles}
    token = create_access_token(args.subject, roles, settings)
    print(token)


if __name__ == "__main__":
    main()
