import asyncio

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import CaseDrop, InventoryItem, Roll, User
from app.services.cases import weighted_pick
from tests.conftest import give_cases, give_items


def test_weighted_pick_boundaries() -> None:
    drops = [
        CaseDrop(case_id=1, item_def_id=item_def_id, weight=weight)
        for item_def_id, weight in ((1, 10), (2, 20), (3, 70))
    ]
    for r, expected in ((0.0, 1), (0.0999, 1), (0.1, 2), (0.2999, 2), (0.3, 3), (0.9999, 3)):
        assert weighted_pick(drops, r).item_def_id == expected, r


async def test_open_case_item_deterministic(alice, rng) -> None:
    [item] = await give_cases("alice", [1])
    rng.values = [0.0]
    async with SessionLocal() as s:
        drops = list(
            (
                await s.scalars(
                    select(CaseDrop)
                    .where(CaseDrop.case_id == 1)
                    .order_by(CaseDrop.item_def_id)
                )
            ).all()
        )
    total = sum(d.weight for d in drops)
    assert [d.item_def_id for d in drops] == list(range(14, 28))
    winner = weighted_pick(drops, rng.values[0])

    resp = await alice.post(f"/api/v1/inventory/{item}/open")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["item"]["kind"] == "skin"
    assert body["item"]["case"] is None
    assert body["item"]["def"]["id"] == winner.item_def_id
    assert body["item"]["def"]["code"] == "genesis-wp"
    assert body["item"]["wear"] == 0.0
    assert body["item"]["source"] == "case"
    assert body["item"]["status"] == "owned"
    assert body["item"]["equipped_slot"] is None
    assert body["win_index"] == 45
    assert 45 <= body["win_index"] <= 54
    assert body["strip"][45] == body["item"]["def"]["id"]
    assert len(body["strip"]) == 60
    assert all(str(def_id) in body["defs"] for def_id in body["strip"])

    async with SessionLocal() as check:
        case_item = await check.get(InventoryItem, item)
        assert case_item.status == "burned"
        assert case_item.burned_at is not None
        skin = await check.get(InventoryItem, body["item"]["id"])
        assert skin.user_id == case_item.user_id
        assert skin.status == "owned"
        assert skin.source == "case"
        assert skin.source_ref == "1"
        assert skin.wear == 0.0
        user = (await check.scalars(select(User).where(User.login == "alice"))).one()
        assert user.balance == 1000
        roll = (await check.scalars(select(Roll).where(Roll.kind == "case_open"))).one()
        assert roll.roll_value == 0.0
        assert float(roll.chance) == pytest.approx(winner.weight / total, abs=1e-7)
        assert roll.input == {"case_id": 1, "inventory_item_id": item}
        assert roll.outcome == {"item_def_id": winner.item_def_id, "item_id": body["item"]["id"]}


async def test_open_errors(alice, bob, admin, rng) -> None:
    rng.values = [0.0]

    [foreign] = await give_cases("bob", [1])
    resp = await alice.post(f"/api/v1/inventory/{foreign}/open")
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"

    [skin] = await give_items("alice", ["genesis-wp"])
    resp = await alice.post(f"/api/v1/inventory/{skin}/open")
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "ITEM_NOT_CASE"

    [own] = await give_cases("bob", [1])
    resp = await bob.post(f"/api/v1/inventory/{own}/open")
    assert resp.status_code == 200, resp.text
    resp = await bob.post(f"/api/v1/inventory/{own}/open")
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"

    resp = await admin.post("/api/v1/admin/cases/1/unpublish")
    assert resp.status_code == 200, resp.text
    [fresh] = await give_cases("alice", [1])
    resp = await alice.post(f"/api/v1/inventory/{fresh}/open")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["item"]["source"] == "case"
    async with SessionLocal() as check:
        case_item = await check.get(InventoryItem, fresh)
        assert case_item.status == "burned"


async def test_open_concurrent(alice, rng) -> None:
    rng.values = [0.0]
    [item] = await give_cases("alice", [1])
    responses = [
        r
        for r in await asyncio.gather(
            *[alice.post(f"/api/v1/inventory/{item}/open") for _ in range(2)],
            return_exceptions=True,
        )
        if not isinstance(r, BaseException)
    ]
    ok = [r for r in responses if r.status_code == 200]
    bad = [r for r in responses if r.status_code == 400]
    assert len(ok) == 1
    assert len(bad) == 1
    assert bad[0].json()["error"]["code"] == "ITEM_NOT_OWNED"
