"""Админка кейсов v3, пул ежедневной награды и выдача предметов (контракт v3)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AdminAudit, User

SLOTS = [s + p for s in "wb" for p in "PNBRQK"]


def pieces_body(rarity: str = "common", value: int = 20) -> list[dict]:
    return [
        {"side": s[0], "piece_type": s[1], "rarity": rarity, "value": value,
         "asset": {"type": "stub", "color": "#ffffff"}}
        for s in SLOTS
    ]


def collection_body(code: str, name: str) -> dict:
    return {"code": code, "name": name, "description": "", "pieces": pieces_body()}


async def create_case(admin, code: str, kind: str, **extra) -> dict:
    resp = await admin.post(
        "/api/v1/admin/cases",
        json={"code": code, "name": "Case", "price": 50, "kind": kind, **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def create_set_with_collection(
    admin, code: str = "winter", name: str = "Winter"
) -> dict:
    """Черновой набор с одной коллекцией: {"set_id", "collection_id", "skin_id"}."""
    resp = await admin.post(
        "/api/v1/admin/sets",
        json={"code": code, "name": name, "description": ""},
    )
    assert resp.status_code == 201, resp.text
    set_id = resp.json()["id"]
    resp = await admin.post(
        f"/api/v1/admin/sets/{set_id}/collections", json=collection_body(code, name)
    )
    assert resp.status_code == 201, resp.text
    detail = resp.json()
    collection = detail["collections"][0]
    return {
        "set_id": set_id,
        "collection_id": collection["id"],
        "skin_id": collection["items"][0]["id"],
    }


async def test_case_kinds_validation(admin) -> None:
    base = {"code": "v1", "name": "Case", "price": 50}

    resp = await admin.post("/api/v1/admin/cases", json={**base, "kind": "set"})
    assert resp.status_code == 422

    resp = await admin.post(
        "/api/v1/admin/cases", json={**{"code": "v2", "name": "Case", "price": 50}, "kind": "custom", "set_id": 2}
    )
    assert resp.status_code == 422

    now = datetime.now(UTC)
    resp = await admin.post(
        "/api/v1/admin/cases",
        json={
            **{"code": "v3", "name": "Case", "price": 50, "kind": "custom"},
            "sale_starts_at": now.isoformat(),
            "sale_ends_at": now.isoformat(),
        },
    )
    assert resp.status_code == 422

    resp = await admin.post(
        "/api/v1/admin/cases",
        json={**{"code": "v4", "name": "Case", "price": 50}, "kind": "set", "set_id": 1},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SET_IS_BASE"

    resp = await admin.post(
        "/api/v1/admin/cases",
        json={**{"code": "v5", "name": "Case", "price": 50}, "kind": "set", "set_id": 999},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SET_NOT_FOUND"

    case = await create_case(admin, "v6", "collection", collection_id=2)
    assert case["status"] == "draft"
    assert case["sold_count"] == 0
    assert case["collection"] == {"code": "genesis", "name": "Genesis"}
    assert case["drops"] == []


async def test_auto_drops_by_kind(admin) -> None:
    case_set = await create_case(admin, "set-case", "set", set_id=2)
    resp = await admin.post(f"/api/v1/admin/cases/{case_set['id']}/drops/auto", json={})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["drops"]) == 14

    case_coll = await create_case(admin, "coll-case", "collection", collection_id=2)
    resp = await admin.post(f"/api/v1/admin/cases/{case_coll['id']}/drops/auto", json={})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["drops"]) == 12

    resp = await admin.post(
        "/api/v1/admin/cases",
        json={"code": "custom-case", "name": "Custom", "price": 50, "kind": "custom"},
    )
    assert resp.status_code == 201, resp.text
    case_custom = resp.json()

    resp = await admin.post(f"/api/v1/admin/cases/{case_custom['id']}/drops/auto", json={})
    assert resp.status_code == 422

    resp = await admin.post(
        f"/api/v1/admin/cases/{case_custom['id']}/drops/auto", json={"set_ids": [2]}
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["drops"]) == 14

    resp = await admin.post(
        f"/api/v1/admin/cases/{case_custom['id']}/drops/auto",
        json={"collection_ids": [2]},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["drops"]) == 12

    resp = await admin.post(
        f"/api/v1/admin/cases/{case_custom['id']}/drops/auto", json={"set_ids": [1]}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SET_IS_BASE"


async def test_manual_drops_scope(admin) -> None:
    case_coll = await create_case(admin, "coll-manual", "collection", collection_id=2)

    resp = await admin.put(
        f"/api/v1/admin/cases/{case_coll['id']}/drops",
        json=[{"item_def_id": 26, "weight": 1}],
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DROP_ITEM_NOT_AVAILABLE"

    resp = await admin.put(
        f"/api/v1/admin/cases/{case_coll['id']}/drops",
        json=[{"item_def_id": 14, "weight": 10}],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["drops"] == [{"item_def_id": 14, "weight": 10}]

    case_custom = await create_case(admin, "custom-manual", "custom")

    resp = await admin.put(
        f"/api/v1/admin/cases/{case_custom['id']}/drops",
        json=[{"item_def_id": 1, "weight": 1}],
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DROP_ITEM_NOT_AVAILABLE"

    resp = await admin.put(
        f"/api/v1/admin/cases/{case_custom['id']}/drops",
        json=[
            {"item_def_id": 26, "weight": 5},
            {"item_def_id": 14, "weight": 10},
        ],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["drops"] == [
        {"item_def_id": 14, "weight": 10},
        {"item_def_id": 26, "weight": 5},
    ]


async def test_publish_unpublish(admin, client) -> None:
    case = await create_case(admin, "life-case", "set", set_id=2)
    case_id = case["id"]

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/publish")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_NOT_READY"

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/drops/auto", json={})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["drops"]) == 14

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/publish")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "on_sale"
    assert body["on_sale_now"] is True

    resp = await client.get("/api/v1/shop")
    assert resp.status_code == 200
    assert case_id in [c["id"] for c in resp.json()]

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/publish")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_NOT_READY"

    resp = await admin.put(
        f"/api/v1/admin/cases/{case_id}/drops", json=[{"item_def_id": 14, "weight": 1}]
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_LOCKED"

    resp = await admin.delete(f"/api/v1/admin/cases/{case_id}")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_LOCKED"

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/unpublish")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "off_sale"

    resp = await client.get("/api/v1/shop")
    assert case_id not in [c["id"] for c in resp.json()]

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/unpublish")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_NOT_ON_SALE"

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/publish")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "on_sale"


async def test_publish_requires_released_sets(admin) -> None:
    created = await create_set_with_collection(admin)
    set_id = created["set_id"]
    collection_id = created["collection_id"]

    resp = await admin.post(
        "/api/v1/admin/cases",
        json={"code": "winter-case", "name": "Winter", "price": 50, "kind": "custom"},
    )
    assert resp.status_code == 201, resp.text
    case_id = resp.json()["id"]

    resp = await admin.post(
        f"/api/v1/admin/cases/{case_id}/drops/auto",
        json={"collection_ids": [collection_id]},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["drops"]) == 12

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/publish")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_NOT_READY"

    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/release")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "released"

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/publish")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "on_sale"


async def test_retire_set_unpublishes(admin, db, client) -> None:
    created = await create_set_with_collection(admin, code="aurora", name="Aurora")
    set_id = created["set_id"]
    collection_id = created["collection_id"]

    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/release")
    assert resp.status_code == 200, resp.text

    resp = await admin.post(
        "/api/v1/admin/cases",
        json={"code": "aurora-case", "name": "Aurora", "price": 50, "kind": "custom"},
    )
    assert resp.status_code == 201, resp.text
    case_id = resp.json()["id"]

    resp = await admin.post(
        f"/api/v1/admin/cases/{case_id}/drops/auto",
        json={"collection_ids": [collection_id]},
    )
    assert resp.status_code == 200, resp.text

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/publish")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "on_sale"

    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/retire")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "retired"

    resp = await admin.get("/api/v1/admin/cases")
    case = {c["id"]: c for c in resp.json()}[case_id]
    assert case["status"] == "off_sale"

    audits = (await db.scalars(select(AdminAudit).order_by(AdminAudit.id))).all()
    retire_audit = [a for a in audits if a.action == "set.retire"][-1]
    assert retire_audit.target == f"set:{set_id}"
    assert retire_audit.payload == {"unpublished_case_ids": [case_id]}

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/publish")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_NOT_READY"

    resp = await client.get(f"/api/v1/cases/{case_id}")
    assert resp.status_code == 200
    assert resp.json()["on_sale_now"] is False


async def test_patch_limits(admin, alice) -> None:
    sold = 0

    def _iso(days: float) -> str:
        return (datetime.now(UTC) + timedelta(days=days)).isoformat()

    ends = datetime.now(UTC) + timedelta(days=1)
    resp = await admin.patch(
        "/api/v1/admin/cases/1",
        json={"stock_limit": 5, "sale_ends_at": ends.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stock_limit"] == 5
    assert datetime.fromisoformat(body["sale_ends_at"]) == ends

    resp = await admin.patch("/api/v1/admin/cases/1", json={"stock_limit": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["stock_limit"] is None

    resp = await admin.patch(
        "/api/v1/admin/cases/1", json={"sale_starts_at": _iso(2)}
    )
    assert resp.status_code == 422

    for _ in range(2):
        resp = await alice.post("/api/v1/cases/1/buy")
        assert resp.status_code == 200, resp.text
        sold += 1

    resp = await admin.patch("/api/v1/admin/cases/1", json={"stock_limit": 1})
    assert resp.status_code == 422
    assert sold == 2


async def test_daily_pool_admin(admin) -> None:
    resp = await admin.get("/api/v1/admin/daily-reward-pool")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) == 1
    assert data[0]["case"] == {
        "id": 1, "code": "genesis", "name": "Genesis", "kind": "set", "price": 100,
    }
    assert data[0]["weight"] == 1

    resp = await admin.put(
        "/api/v1/admin/daily-reward-pool", json=[{"case_id": 1, "weight": 3}]
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()[0]["weight"] == 3

    draft = await create_case(admin, "pool-draft", "custom")
    resp = await admin.put(
        "/api/v1/admin/daily-reward-pool",
        json=[{"case_id": 1, "weight": 1}, {"case_id": draft["id"], "weight": 1}],
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_NOT_AVAILABLE"

    resp = await admin.put(
        "/api/v1/admin/daily-reward-pool",
        json=[{"case_id": 1, "weight": 1}, {"case_id": 1, "weight": 2}],
    )
    assert resp.status_code == 422

    resp = await admin.put("/api/v1/admin/daily-reward-pool", json=[])
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_grant_item_and_case(admin, alice, db) -> None:
    alice_id = (await db.scalars(select(User).where(User.login == "alice"))).one().id

    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/grant-item", json={"item_def_id": 14}
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()
    assert item["kind"] == "skin"
    assert item["def"]["id"] == 14
    assert item["source"] == "admin_grant"

    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/grant-item", json={"case_id": 1}
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()
    assert item["kind"] == "case"
    assert item["case"]["id"] == 1
    assert item["wear"] is None

    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/grant-item", json={"item_def_id": 1}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_DEF_NOT_AVAILABLE"

    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/grant-item",
        json={"item_def_id": 14, "case_id": 1},
    )
    assert resp.status_code == 422

    draft = await create_case(admin, "grant-draft", "custom")
    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/grant-item", json={"case_id": draft["id"]}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_DEF_NOT_AVAILABLE"

    audits = (await db.scalars(select(AdminAudit).order_by(AdminAudit.id))).all()
    grants = [a for a in audits if a.action == "user.grant_item"]
    assert len(grants) == 2
