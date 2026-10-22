import asyncio

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import InventoryItem, ItemDef, Roll
from tests.conftest import give_items


async def def_id_by_code(code: str) -> int:
    async with SessionLocal() as db:
        item_def = (await db.scalars(select(ItemDef).where(ItemDef.code == code))).one()
        return item_def.id


async def test_upgrade_preview(alice, db) -> None:
    ids = await give_items("alice", ["genesis-pawn-frost", "genesis-knight-frost"])
    epic = await def_id_by_code("genesis-queen-snow")

    resp = await alice.post(
        "/api/v1/upgrade/preview", json={"input_ids": ids, "target_def_id": epic}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chance"] == pytest.approx(300 / 500 * 0.95)
    assert body["allowed"] is True
    assert body["reason"] is None

    mythic = await def_id_by_code("genesis-board-albion")
    resp = await alice.post(
        "/api/v1/upgrade/preview", json={"input_ids": ids, "target_def_id": mythic}
    )
    body = resp.json()
    assert body["chance"] == pytest.approx(300 / 5000 * 0.95)
    assert body["allowed"] is True

    common_ids = await give_items("alice", ["genesis-pawn-chalk"])
    resp = await alice.post(
        "/api/v1/upgrade/preview", json={"input_ids": common_ids, "target_def_id": mythic}
    )
    body = resp.json()
    assert body["allowed"] is False
    assert body["reason"] == "UPGRADE_CHANCE_OUT_OF_RANGE"
    assert body["chance"] == pytest.approx(20 / 5000 * 0.95)

    epic_ids = await give_items("alice", ["genesis-pawn-snow"] * 10)
    resp = await alice.post(
        "/api/v1/upgrade/preview", json={"input_ids": epic_ids, "target_def_id": epic}
    )
    body = resp.json()
    assert body["allowed"] is False
    assert body["reason"] == "UPGRADE_CHANCE_OUT_OF_RANGE"
    assert body["chance"] == pytest.approx(10 * 500 / 500 * 0.95)


async def test_upgrade_validation(alice, bob, admin) -> None:
    epic = await def_id_by_code("genesis-queen-snow")

    # Больше 10 предметов.
    many = await give_items("alice", ["genesis-pawn-snow"] * 11)
    resp = await alice.post(
        "/api/v1/upgrade/preview", json={"input_ids": many, "target_def_id": epic}
    )
    assert resp.status_code == 200
    assert resp.json()["reason"] == "TOO_MANY_INPUTS"

    # Дубликаты.
    dup = await give_items("alice", ["genesis-pawn-frost"])
    resp = await alice.post(
        "/api/v1/upgrade/preview",
        json={"input_ids": [dup[0], dup[0]], "target_def_id": epic},
    )
    assert resp.json()["reason"] == "DUPLICATE_INPUTS"

    # Чужой предмет — прямое 400.
    foreign = await give_items("bob", ["genesis-board-marble"])
    resp = await alice.post(
        "/api/v1/upgrade", json={"input_ids": foreign, "target_def_id": epic}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"

    inputs = await give_items("alice", ["genesis-pawn-frost", "genesis-knight-frost"])

    # Цель из черновой коллекции.
    resp = await admin.post(
        "/api/v1/admin/collections",
        json={"code": "winter", "name": "Winter", "description": "Зимняя коллекция"},
    )
    assert resp.status_code == 201, resp.text
    collection_id = resp.json()["id"]
    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/items",
        json={
            "code": "winter-queen-snow",
            "name": "Зимний ферзь",
            "kind": "piece_skin",
            "piece_type": "Q",
            "rarity": "epic",
            "value": 500,
            "asset": {"type": "stub", "color": "#ffffff"},
        },
    )
    assert resp.status_code == 201, resp.text
    draft_target = resp.json()["id"]
    resp = await alice.post(
        "/api/v1/upgrade/preview",
        json={"input_ids": inputs, "target_def_id": draft_target},
    )
    assert resp.json()["reason"] == "UPGRADE_TARGET_NOT_AVAILABLE"

    # Цель с is_upgrade_target=false.
    resp = await admin.patch("/api/v1/admin/item-defs/1", json={"is_upgrade_target": False})
    assert resp.status_code == 200, resp.text
    resp = await alice.post(
        "/api/v1/upgrade/preview", json={"input_ids": inputs, "target_def_id": 1}
    )
    assert resp.json()["reason"] == "UPGRADE_TARGET_NOT_AVAILABLE"


async def test_upgrade_success(alice, rng) -> None:
    ids = await give_items("alice", ["genesis-pawn-frost", "genesis-knight-frost"])
    resp = await alice.put("/api/v1/loadout/N", json={"inventory_item_id": ids[1]})
    assert resp.status_code == 200, resp.text
    epic = await def_id_by_code("genesis-queen-snow")

    rng.values = [0.0, 0.3]
    resp = await alice.post("/api/v1/upgrade", json={"input_ids": ids, "target_def_id": epic})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["chance"] == pytest.approx(0.57)
    assert body["roll_value"] == 0.0
    assert body["burned_ids"] == sorted(ids)
    assert body["item"] is not None
    new_item_id = body["item"]["id"]
    assert body["item"]["source"] == "upgrade"
    assert body["item"]["wear"] == pytest.approx(0.3)
    assert body["item"]["def"]["code"] == "genesis-queen-snow"

    loadout = (await alice.get("/api/v1/loadout")).json()
    assert loadout["N"] is None

    async with SessionLocal() as check:
        for item_id in ids:
            item = await check.get(InventoryItem, item_id)
            assert item.status == "burned"
            assert item.burned_at is not None
        roll = (await check.scalars(select(Roll).where(Roll.kind == "upgrade"))).one()
        assert roll.outcome == {"success": True, "item_id": new_item_id}
        count = await check.scalar(select(func.count()).select_from(InventoryItem))
        assert count == 3


async def test_upgrade_fail(alice, rng, db) -> None:
    ids = await give_items("alice", ["genesis-pawn-frost", "genesis-knight-frost"])
    mythic = await def_id_by_code("genesis-board-albion")
    rng.values = [0.99]
    resp = await alice.post(
        "/api/v1/upgrade", json={"input_ids": ids, "target_def_id": mythic}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    assert body["item"] is None
    assert body["roll_value"] == 0.99

    async with SessionLocal() as check:
        for item_id in ids:
            item = await check.get(InventoryItem, item_id)
            assert item.status == "burned"
        count = await check.scalar(select(func.count()).select_from(InventoryItem))
        assert count == 2
        roll = (await check.scalars(select(Roll).where(Roll.kind == "upgrade"))).one()
        assert roll.outcome == {"success": False, "item_id": None}


async def test_upgrade_concurrent_same_inputs(alice, rng, db) -> None:
    ids = await give_items("alice", ["genesis-pawn-frost", "genesis-knight-frost"])
    epic = await def_id_by_code("genesis-queen-snow")
    payload = {"input_ids": ids, "target_def_id": epic}
    responses = await asyncio.gather(
        alice.post("/api/v1/upgrade", json=payload),
        alice.post("/api/v1/upgrade", json=payload),
    )
    ok = [r for r in responses if r.status_code == 200]
    failed = [r for r in responses if r.status_code == 400]
    assert len(ok) == 1
    assert len(failed) == 1
    assert failed[0].json()["error"]["code"] == "ITEM_NOT_OWNED"
