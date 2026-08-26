from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Policy
from app.policies.catalog import POLICY_CATALOG, sync_policy_catalog


def test_policy_catalog_sync_is_idempotent_and_non_destructive(db: Session) -> None:
    custom = Policy(
        code="CUSTOM-001",
        title="自定义规则",
        category="营销",
        content="用户维护的规则不能被目录同步删除。",
        source="user",
        version="1",
        forbidden_terms=[],
        effective_from=POLICY_CATALOG[0].effective_from,
        is_active=True,
    )
    db.add(custom)
    first = sync_policy_catalog(db)
    db.commit()
    second = sync_policy_catalog(db)
    db.commit()

    assert first == {"created": len(POLICY_CATALOG), "updated": 0, "unchanged": 0}
    assert second == {"created": 0, "updated": 0, "unchanged": len(POLICY_CATALOG)}
    assert db.scalar(select(Policy).where(Policy.code == "CUSTOM-001")) is custom


def test_policy_catalog_sync_updates_drifted_managed_policy(db: Session) -> None:
    sync_policy_catalog(db)
    db.commit()
    policy = db.scalar(select(Policy).where(Policy.code == "DATA-001"))
    assert policy is not None
    policy.content = "drifted"
    db.commit()

    result = sync_policy_catalog(db)
    db.commit()

    assert result["updated"] == 1
    assert policy.content != "drifted"
