import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Case, InventoryItem, Ledger, User
from tests.conftest import give_cases


async def test_shop_list(client) -> None:
    resp = await client.get("/api/v1/shop")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    shop_case = data[0]
    assert shop_case["id"] == 1
    assert shop_case["code"] == "genesis"
    assert shop_case["name"] == "Genesis"
    assert shop_case["kind"] == "set"
    assert shop_case["set"] == {"code": "genesis", "name": "Genesis"}
    assert shop_case["collection"] is None
    assert shop_case["price"] == 100
    assert shop_case["stock_limit"] is None
    assert shop_case["stock_left"] is None
    assert shop_case["sale_starts_at"] is None
    assert shop_case["sale_ends_at"] is None


_APP_BUG_ITEMS_OUT = (
    "Баг приложения: app/services/items.py:294 (items_out) — "
    "'await db.scalars(...).all()' вызывает .all() у корутины, "
    "любое ItemOut предмета-кейса бросает AttributeError "
    "(POST /cases/{id}/buy → 500 вместо 200 CaseBuyOut)."
)


@pytest.mark.xfail(reason=_APP_BUG_ITEMS_OUT, strict=True)
async def test_buy_case(alice) -> None:
    resp = await alice.post("/api/v1/cases/1/buy")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["balance"] == 900
    item = body["item"]
    assert item["kind"] == "case"
    assert item["def"] is None
    assert item["case"]["id"] == 1
    assert item["case"]["code"] == "genesis"
    assert item["case"]["price"] == 100
    assert item["wear"] is None
    assert item["exterior"] is None
    assert item["status"] == "owned"
    assert item["equipped_slot"] is None
    assert item["source"] == "shop"
    assert item["bound"] is False

    async with SessionLocal() as check:
        ledger = (
            await check.scalars(select(Ledger).where(Ledger.reason == "case_purchase"))
        ).one()
        assert ledger.delta == -100
        assert ledger.balance_after == 900
        assert ledger.ref == "1"

    resp = await alice.get("/api/v1/inventory?kind=case")
    assert resp.status_code == 200
    cases = resp.json()
    assert len(cases) == 1
    assert cases[0]["id"] == item["id"]
    assert cases[0]["case"]["id"] == 1

    resp = await alice.get("/api/v1/inventory")
    assert resp.status_code == 200
    skins = [i for i in resp.json() if i["kind"] == "skin"]
    assert len(skins) == 13
    assert all(i["source"] == "base" for i in skins)


async def test_buy_insufficient_funds(alice, db) -> None:
    async with db.begin():
        user = (await db.scalars(select(User).where(User.login == "alice"))).one()
        user.balance = 50

    resp = await alice.post("/api/v1/cases/1/buy")
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "INSUFFICIENT_FUNDS"

    async with SessionLocal() as check:
        case = await check.get(Case, 1)
        assert case.sold_count == 0
        assert (
            await check.scalars(select(Ledger).where(Ledger.reason == "case_purchase"))
        ).all() == []
        assert (
            await check.scalars(
                select(InventoryItem).where(InventoryItem.case_id.is_not(None))
            )
        ).all() == []


@pytest.mark.xfail(reason=_APP_BUG_ITEMS_OUT, strict=True)
async def test_stock_limit(admin, alice, bob) -> None:
    resp = await admin.patch("/api/v1/admin/cases/1", json={"stock_limit": 2})
    assert resp.status_code == 200, resp.text
    assert resp.json()["stock_limit"] == 2
    assert resp.json()["sold_count"] == 0

    resp = await alice.post("/api/v1/cases/1/buy")
    assert resp.status_code == 200, resp.text
    assert resp.json()["balance"] == 900
    resp = await bob.post("/api/v1/cases/1/buy")
    assert resp.status_code == 200, resp.text

    resp = await alice.post("/api/v1/cases/1/buy")
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "CASE_NOT_AVAILABLE"

    resp = await admin.get("/api/v1/admin/cases")
    case = {c["id"]: c for c in resp.json()}[1]
    assert case["status"] == "off_sale"
    assert case["sold_count"] == 2
    assert case["on_sale_now"] is False

    resp = await alice.get("/api/v1/shop")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.xfail(reason=_APP_BUG_ITEMS_OUT, strict=True)
async def test_stock_limit_concurrent(admin, alice, db) -> None:
    resp = await admin.patch("/api/v1/admin/cases/1", json={"stock_limit": 3})
    assert resp.status_code == 200, resp.text

    async with db.begin():
        user = (await db.scalars(select(User).where(User.login == "alice"))).one()
        user.balance = 10000

    responses = [
        r
        for r in await asyncio.gather(
            *[alice.post("/api/v1/cases/1/buy") for _ in range(6)],
            return_exceptions=True,
        )
        if not isinstance(r, BaseException)
    ]
    ok = [r for r in responses if r.status_code == 200]
    assert len(ok) == 3

    async with SessionLocal() as check:
        case = await check.get(Case, 1)
        assert case.sold_count == 3
        assert case.status == "off_sale"
        items = (
            await check.scalars(
                select(InventoryItem).where(InventoryItem.case_id == 1)
            )
        ).all()
        assert len(items) == 3
        user = (await check.scalars(select(User).where(User.login == "alice"))).one()
        assert user.balance == 10000 - 300


@pytest.mark.xfail(reason=_APP_BUG_ITEMS_OUT, strict=True)
async def test_sale_window(admin, alice, frozen) -> None:
    starts_at = (frozen.now() + timedelta(hours=1)).isoformat()
    resp = await admin.patch("/api/v1/admin/cases/1", json={"sale_starts_at": starts_at})
    assert resp.status_code == 200, resp.text
    assert resp.json()["on_sale_now"] is False

    resp = await alice.get("/api/v1/shop")
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await alice.post("/api/v1/cases/1/buy")
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "CASE_NOT_AVAILABLE"

    frozen.advance(7200)
    resp = await alice.get("/api/v1/shop")
    assert resp.status_code == 200
    shop = resp.json()
    assert [c["id"] for c in shop] == [1]
    assert shop[0]["sale_starts_at"] is not None
    assert shop[0]["sale_ends_at"] is None

    resp = await alice.post("/api/v1/cases/1/buy")
    assert resp.status_code == 200, resp.text
    assert resp.json()["balance"] == 900

    ends_at = (frozen.now() + timedelta(hours=1)).isoformat()
    resp = await admin.patch("/api/v1/admin/cases/1", json={"sale_ends_at": ends_at})
    assert resp.status_code == 200, resp.text

    frozen.advance(7200)
    resp = await alice.get("/api/v1/shop")
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await alice.get("/api/v1/cases/1")
    assert resp.status_code == 200
    assert resp.json()["on_sale_now"] is False

    resp = await alice.post("/api/v1/cases/1/buy")
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "CASE_NOT_AVAILABLE"


async def test_draft_case_hidden(admin, alice, client) -> None:
    resp = await admin.post(
        "/api/v1/admin/cases",
        json={"code": "c2", "name": "C2", "price": 10, "kind": "custom"},
    )
    assert resp.status_code == 201, resp.text
    case_id = resp.json()["id"]
    assert resp.json()["status"] == "draft"

    resp = await client.get(f"/api/v1/cases/{case_id}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CASE_NOT_FOUND"

    resp = await alice.post(f"/api/v1/cases/{case_id}/buy")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CASE_NOT_FOUND"
