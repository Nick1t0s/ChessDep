import asyncio

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import CaseDrop, InventoryItem, Ledger, Roll, User
from app.services.cases import weighted_pick
from app.services.economy import apply_delta


def test_weighted_pick_boundaries() -> None:
    drops = [
        CaseDrop(case_id=1, item_def_id=item_def_id, weight=weight)
        for item_def_id, weight in ((1, 10), (2, 20), (3, 70))
    ]
    for r, expected in ((0.0, 1), (0.0999, 1), (0.1, 2), (0.2999, 2), (0.3, 3), (0.9999, 3)):
        assert weighted_pick(drops, r).item_def_id == expected, r


async def test_open_case_deterministic(alice, rng) -> None:
    rng.values = [0.0]
    resp = await alice.post("/api/v1/cases/1/open")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["balance"] == 900
    assert body["item"]["def"]["code"] == "genesis-pawn-chalk"
    assert body["item"]["def"]["id"] == 1
    assert body["win_index"] == 45
    assert body["strip"][45] == body["item"]["def"]["id"]
    assert len(body["strip"]) == 60
    assert all(str(def_id) in body["defs"] for def_id in body["strip"])
    assert body["item"]["wear"] == 0.0
    assert body["item"]["source"] == "case"

    async with SessionLocal() as check:
        ledger = (
            await check.scalars(select(Ledger).where(Ledger.reason == "case_purchase"))
        ).one()
        assert ledger.delta == -100
        assert ledger.balance_after == 900
        roll = (await check.scalars(select(Roll).where(Roll.kind == "case_open"))).one()
        assert roll.roll_value == 0.0
        assert float(roll.chance) == pytest.approx(1_332_000 / 8_375_994, abs=1e-7)
        assert roll.outcome == {"item_def_id": 1, "item_id": body["item"]["id"]}
        item = await check.get(InventoryItem, body["item"]["id"])
        assert item.wear == 0.0


async def test_open_case_insufficient_funds(alice, db) -> None:
    async with db.begin():
        user = (await db.scalars(select(User))).one()
        user.balance = 50

    resp = await alice.post("/api/v1/cases/1/open")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INSUFFICIENT_FUNDS"

    async with SessionLocal() as check:
        assert (await check.scalars(select(InventoryItem))).all() == []
        assert (
            await check.scalars(select(Ledger).where(Ledger.reason == "case_purchase"))
        ).all() == []
        assert (await check.scalars(select(Roll))).all() == []


async def test_open_case_concurrent(alice, rng, db) -> None:
    rng.values = [0.0]
    async with db.begin():
        user = (await db.scalars(select(User))).one()
        await apply_delta(db, user.id, -700, "admin_adjust")  # баланс → 300

    responses = await asyncio.gather(
        *[alice.post("/api/v1/cases/1/open") for _ in range(6)]
    )
    ok = [r for r in responses if r.status_code == 200]
    assert len(ok) == 3

    async with SessionLocal() as check:
        user = (await check.scalars(select(User))).one()
        assert user.balance == 0
        items = (await check.scalars(select(InventoryItem))).all()
        assert len(items) == 3
        deltas = (
            await check.scalars(select(Ledger.delta).where(Ledger.user_id == user.id))
        ).all()
        assert sum(deltas) == user.balance


async def test_open_unavailable_case(admin, db) -> None:
    resp = await admin.post(
        "/api/v1/admin/collections",
        json={"code": "winter", "name": "Winter", "description": "Зимняя коллекция"},
    )
    assert resp.status_code == 201, resp.text
    collection_id = resp.json()["id"]
    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/cases",
        json={"code": "winter-case", "name": "Winter: кейс", "price": 100, "sort": 0},
    )
    assert resp.status_code == 201, resp.text
    case_id = resp.json()["id"]

    # Кейс черновой коллекции публично не существует.
    resp = await admin.get(f"/api/v1/cases/{case_id}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CASE_NOT_FOUND"
    resp = await admin.post(f"/api/v1/cases/{case_id}/open")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CASE_NOT_FOUND"

    resp = await admin.post("/api/v1/admin/collections/1/retire")
    assert resp.status_code == 200, resp.text

    resp = await admin.get("/api/v1/cases")
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await admin.get("/api/v1/cases/1")
    assert resp.status_code == 404

    resp = await admin.post("/api/v1/cases/1/open")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_NOT_AVAILABLE"

    me = (await admin.get("/api/v1/me")).json()
    assert me["balance"] == 1000
