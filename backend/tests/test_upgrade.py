import asyncio

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import InventoryItem, ItemDef, Roll, User
from app.seed_skins import seed_asset
from tests.conftest import give_cases, give_items


async def def_id_by_code(code: str) -> int:
    async with SessionLocal() as db:
        item_def = (await db.scalars(select(ItemDef).where(ItemDef.code == code))).one()
        return item_def.id


async def base_item_ids(login: str) -> list[int]:
    async with SessionLocal() as db:
        user_id = await db.scalar(select(User.id).where(User.login == login))
        return list(
            (
                await db.scalars(
                    select(InventoryItem.id).where(
                        InventoryItem.user_id == user_id,
                        InventoryItem.source == "base",
                    )
                )
            ).all()
        )


async def test_upgrade_preview(alice, admin) -> None:
    ids = await give_items("alice", ["genesis-wr", "genesis-br"])
    epic = await def_id_by_code("genesis-wq")

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

    common_ids = await give_items("alice", ["genesis-wp"])
    resp = await alice.post(
        "/api/v1/upgrade/preview", json={"input_ids": common_ids, "target_def_id": mythic}
    )
    body = resp.json()
    assert body["allowed"] is False
    assert body["reason"] == "UPGRADE_CHANCE_OUT_OF_RANGE"
    assert body["chance"] == pytest.approx(20 / 5000 * 0.95)

    epic_ids = await give_items("alice", ["genesis-bq"] * 10)
    resp = await alice.post(
        "/api/v1/upgrade/preview", json={"input_ids": epic_ids, "target_def_id": epic}
    )
    body = resp.json()
    assert body["allowed"] is False
    assert body["reason"] == "UPGRADE_CHANCE_OUT_OF_RANGE"
    assert body["chance"] == pytest.approx(10 * 500 / 500 * 0.95)


async def test_upgrade_validation(alice, bob, admin) -> None:
    epic = await def_id_by_code("genesis-wq")

    # Больше 10 предметов.
    many = await give_items("alice", ["genesis-bq"] * 11)
    resp = await alice.post(
        "/api/v1/upgrade/preview", json={"input_ids": many, "target_def_id": epic}
    )
    assert resp.status_code == 200
    assert resp.json()["reason"] == "TOO_MANY_INPUTS"

    # Дубликаты.
    dup = await give_items("alice", ["genesis-wr"])
    resp = await alice.post(
        "/api/v1/upgrade/preview",
        json={"input_ids": [dup[0], dup[0]], "target_def_id": epic},
    )
    assert resp.json()["reason"] == "DUPLICATE_INPUTS"

    # Чужой предмет — прямое 400.
    foreign = await give_items("bob", ["genesis-bq"])
    resp = await alice.post(
        "/api/v1/upgrade", json={"input_ids": foreign, "target_def_id": epic}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"

    inputs = await give_items("alice", ["genesis-wr", "genesis-br"])

    # Цель из чернового набора: создать набор и коллекцию (12 фигур).
    resp = await admin.post(
        "/api/v1/admin/sets",
        json={"code": "winter", "name": "Winter", "description": "Зимний набор"},
    )
    assert resp.status_code == 201, resp.text
    set_id = resp.json()["id"]
    resp = await admin.post(
        f"/api/v1/admin/sets/{set_id}/collections",
        json={
            "code": "winter",
            "name": "Winter",
            "description": "Зимняя коллекция",
            "pieces": [
                {
                    "side": side,
                    "piece_type": piece_type,
                    "rarity": "epic",
                    "value": 500,
                    "asset": seed_asset("base-wp"),
                }
                for side in ("w", "b")
                for piece_type in ("P", "N", "B", "R", "Q", "K")
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    draft_target = next(
        item["id"]
        for item in resp.json()["collections"][0]["items"]
        if item["code"] == "winter-wq"
    )
    resp = await alice.post(
        "/api/v1/upgrade/preview",
        json={"input_ids": inputs, "target_def_id": draft_target},
    )
    assert resp.json()["reason"] == "UPGRADE_TARGET_NOT_AVAILABLE"

    # Цель — базовый скин: базовый набор не бывает целью апгрейда.
    resp = await alice.post(
        "/api/v1/upgrade/preview", json={"input_ids": inputs, "target_def_id": 1}
    )
    assert resp.json()["reason"] == "UPGRADE_TARGET_NOT_AVAILABLE"

    # Цель с is_upgrade_target=false.
    resp = await admin.patch("/api/v1/admin/item-defs/18", json={"is_upgrade_target": False})
    assert resp.status_code == 200, resp.text
    resp = await alice.post(
        "/api/v1/upgrade/preview", json={"input_ids": inputs, "target_def_id": 18}
    )
    assert resp.json()["reason"] == "UPGRADE_TARGET_NOT_AVAILABLE"


async def test_upgrade_restricted_inputs(alice) -> None:
    epic = await def_id_by_code("genesis-wq")

    # Базовые предметы нельзя апгрейдить.
    base_ids = await base_item_ids("alice")
    assert len(base_ids) == 13
    resp = await alice.post(
        "/api/v1/upgrade", json={"input_ids": base_ids[:2], "target_def_id": epic}
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "ITEM_BOUND"

    # Предмет-кейс нельзя апгрейдить.
    case_ids = await give_cases("alice", [1])
    resp = await alice.post(
        "/api/v1/upgrade", json={"input_ids": case_ids, "target_def_id": epic}
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "ITEM_NOT_UPGRADABLE"


async def test_upgrade_to_board(alice, rng) -> None:
    ids = await give_items("alice", ["genesis-wr", "genesis-br"])
    resp = await alice.put("/api/v1/loadout/bR", json={"inventory_item_id": ids[1]})
    assert resp.status_code == 200, resp.text
    board = await def_id_by_code("genesis-board-albion")

    rng.values = [0.0, 0.3]
    resp = await alice.post(
        "/api/v1/upgrade", json={"input_ids": ids, "target_def_id": board}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["chance"] == pytest.approx(300 / 5000 * 0.95)
    assert body["roll_value"] == 0.0
    assert body["burned_ids"] == sorted(ids)
    assert body["item"] is not None
    assert body["item"]["source"] == "upgrade"
    assert body["item"]["wear"] == pytest.approx(0.3)
    assert body["item"]["def"]["kind"] == "board"
    assert body["item"]["def"]["code"] == "genesis-board-albion"

    loadout = (await alice.get("/api/v1/loadout")).json()
    assert loadout["bR"] is None


async def test_upgrade_success(alice, rng) -> None:
    ids = await give_items("alice", ["genesis-wr", "genesis-br"])
    resp = await alice.put("/api/v1/loadout/bR", json={"inventory_item_id": ids[1]})
    assert resp.status_code == 200, resp.text
    epic = await def_id_by_code("genesis-wq")

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
    assert body["item"]["def"]["code"] == "genesis-wq"

    loadout = (await alice.get("/api/v1/loadout")).json()
    assert loadout["bR"] is None

    async with SessionLocal() as check:
        for item_id in ids:
            item = await check.get(InventoryItem, item_id)
            assert item.status == "burned"
            assert item.burned_at is not None
        roll = (await check.scalars(select(Roll).where(Roll.kind == "upgrade"))).one()
        assert roll.outcome == {"success": True, "item_id": new_item_id}
        count = await check.scalar(select(func.count()).select_from(InventoryItem))
        # 16 строк: 13 базовых + 2 сгоревших входа + новый предмет.
        assert count == 16


async def test_upgrade_fail(alice, rng, db) -> None:
    ids = await give_items("alice", ["genesis-wr", "genesis-br"])
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
        # 15 строк: 13 базовых + 2 сгоревших входа.
        assert count == 15
        roll = (await check.scalars(select(Roll).where(Roll.kind == "upgrade"))).one()
        assert roll.outcome == {"success": False, "item_id": None}


async def test_upgrade_concurrent_same_inputs(alice, rng, db) -> None:
    ids = await give_items("alice", ["genesis-wr", "genesis-br"])
    epic = await def_id_by_code("genesis-wq")
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


async def test_upgrade_set_mismatch(alice, admin) -> None:
    # Второй выпущенный набор Winter (12 фигур).
    resp = await admin.post(
        "/api/v1/admin/sets",
        json={"code": "winter", "name": "Winter", "description": "Зимний набор"},
    )
    assert resp.status_code == 201, resp.text
    set_id = resp.json()["id"]
    resp = await admin.post(
        f"/api/v1/admin/sets/{set_id}/collections",
        json={
            "code": "winter",
            "name": "Winter",
            "description": "Зимняя коллекция",
            "pieces": [
                {
                    "side": side,
                    "piece_type": piece_type,
                    "rarity": "epic",
                    "value": 500,
                    "asset": seed_asset("base-wp"),
                }
                for side in ("w", "b")
                for piece_type in ("P", "N", "B", "R", "Q", "K")
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/release")
    assert resp.status_code == 200, resp.text
    winter_wq = await def_id_by_code("winter-wq")
    genesis_wk = await def_id_by_code("genesis-wk")

    # Входы Genesis -> цель Winter: preview запрещает.
    inputs = await give_items("alice", ["genesis-wr", "genesis-br"])
    resp = await alice.post(
        "/api/v1/upgrade/preview",
        json={"input_ids": inputs, "target_def_id": winter_wq},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["allowed"] is False
    assert resp.json()["reason"] == "UPGRADE_SET_MISMATCH"

    # То же через /upgrade — 400, предметы не сгорают.
    resp = await alice.post(
        "/api/v1/upgrade", json={"input_ids": inputs, "target_def_id": winter_wq}
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "UPGRADE_SET_MISMATCH"
    async with SessionLocal() as db:
        statuses = (
            await db.scalars(select(InventoryItem.status).where(InventoryItem.id.in_(inputs)))
        ).all()
    assert sorted(statuses) == ["owned", "owned"]

    # Смешанные входы (Genesis + Winter) -> цель Genesis: тоже запрещено.
    mixed = await give_items("alice", ["genesis-wr", "winter-wr"])
    resp = await alice.post(
        "/api/v1/upgrade/preview",
        json={"input_ids": mixed, "target_def_id": genesis_wk},
    )
    assert resp.json()["reason"] == "UPGRADE_SET_MISMATCH"
