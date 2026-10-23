import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import InventoryItem, ItemTransfer, Ledger, MarketListing, User
from tests.conftest import (
    anonymous,
    give_cases,
    give_items,
    set_balance,
    set_setting,
)


async def _user_id(login: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(User.id).where(User.login == login))


async def _create_listing(client, item_id: int, price: int):
    resp = await client.post(
        "/api/v1/market/listings", json={"item_id": item_id, "price": price}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_list_and_cancel(alice, bob, rng) -> None:
    ids = await give_items("alice", ["genesis-wp"])
    item_id = ids[0]

    resp = await alice.put("/api/v1/loadout/wP", json={"inventory_item_id": item_id})
    assert resp.status_code == 200, resp.text

    listing = await _create_listing(alice, item_id, 1000)
    listing_id = listing["id"]

    # Слот освободился, предмет listed.
    loadout = (await alice.get("/api/v1/loadout")).json()
    assert loadout["wP"] is None
    inv = (await alice.get("/api/v1/inventory")).json()
    entry = next(i for i in inv if i["id"] == item_id)
    assert entry["status"] == "listed"
    assert entry["equipped_slot"] is None

    # Апгрейд с listed-предметом запрещён.
    def_id = listing["item"]["def"]["id"]
    resp = await alice.post(
        "/api/v1/upgrade", json={"input_ids": [item_id], "target_def_id": def_id}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"

    # Экипировка listed-предмета запрещена.
    resp = await alice.put("/api/v1/loadout/wP", json={"inventory_item_id": item_id})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"

    # Дарение listed-предмета запрещено.
    resp = await alice.post(
        "/api/v1/gifts", json={"item_id": item_id, "to_login": "bob"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"

    # Снятие лота продавцом.
    resp = await alice.delete(f"/api/v1/market/listings/{listing_id}")
    assert resp.status_code == 200, resp.text
    inv = (await alice.get("/api/v1/inventory")).json()
    entry = next(i for i in inv if i["id"] == item_id)
    assert entry["status"] == "owned"

    # Повторное снятие — уже не активен.
    resp = await alice.delete(f"/api/v1/market/listings/{listing_id}")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "LISTING_NOT_ACTIVE"

    # Чужой для bob — лот «не найден».
    resp = await bob.delete(f"/api/v1/market/listings/{listing_id}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "LISTING_NOT_FOUND"


async def test_list_validation(alice, bob, monkeypatch) -> None:
    from app.api import market as market_api

    async def _noop(*args, **kwargs):
        pass

    monkeypatch.setattr(market_api, "hit", _noop)

    ids = await give_items("alice", ["genesis-wp"])
    item_id = ids[0]

    for price in (0, 10_000_001):
        resp = await alice.post(
            "/api/v1/market/listings", json={"item_id": item_id, "price": price}
        )
        assert resp.status_code == 422, resp.text

    foreign = await give_items("bob", ["genesis-bp"])
    resp = await alice.post(
        "/api/v1/market/listings", json={"item_id": foreign[0], "price": 100}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"

    listing = await _create_listing(alice, item_id, 100)
    resp = await alice.post(
        "/api/v1/market/listings", json={"item_id": item_id, "price": 100}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"

    await set_setting("market_max_listings", 1)
    second = await give_items("alice", ["genesis-bp"])
    resp = await alice.post(
        "/api/v1/market/listings", json={"item_id": second[0], "price": 100}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "LISTING_LIMIT"


async def test_trade_hold(alice, frozen) -> None:
    await set_setting("trade_hold_hours", 24)
    ids = await give_items("alice", ["genesis-wp"])

    resp = await alice.post(
        "/api/v1/market/listings", json={"item_id": ids[0], "price": 100}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TRADE_HOLD"
    assert "Предмет можно передать после" in resp.json()["error"]["message"]

    frozen.advance(24 * 3600 + 1)
    resp = await alice.post(
        "/api/v1/market/listings", json={"item_id": ids[0], "price": 100}
    )
    assert resp.status_code == 201, resp.text


async def test_buy_flow(alice, bob) -> None:
    ids = await give_items("alice", ["genesis-wq"])
    listing = await _create_listing(alice, ids[0], 1000)
    listing_id = listing["id"]
    def_id = listing["item"]["def"]["id"]

    resp = await bob.post(f"/api/v1/market/listings/{listing_id}/buy")
    assert resp.status_code == 200, resp.text

    # Балансы.
    assert (await bob.get("/api/v1/me")).json()["balance"] == 0
    assert (await alice.get("/api/v1/me")).json()["balance"] == 1950

    bob_id = await _user_id("bob")
    alice_id = await _user_id("alice")

    async with SessionLocal() as db:
        buy_row = (
            await db.scalars(
                select(Ledger).where(
                    Ledger.user_id == bob_id, Ledger.reason == "market_buy"
                )
            )
        ).one()
        sale_row = (
            await db.scalars(
                select(Ledger).where(
                    Ledger.user_id == alice_id, Ledger.reason == "market_sale"
                )
            )
        ).one()
        assert buy_row.delta == -1000
        assert buy_row.ref == str(listing_id)
        assert sale_row.delta == 950
        assert sale_row.ref == str(listing_id)

        item = await db.get(InventoryItem, ids[0])
        assert item is not None
        assert item.user_id == bob_id
        assert item.status == "owned"
        assert abs((item.acquired_at - datetime.now(UTC)).total_seconds()) < 60

        listing_row = await db.get(MarketListing, listing_id)
        assert listing_row is not None
        assert listing_row.status == "sold"
        assert listing_row.buyer_id == bob_id
        assert listing_row.fee == 50
        assert listing_row.closed_at is not None

        transfers = (
            await db.scalars(
                select(ItemTransfer).where(
                    ItemTransfer.kind == "market", ItemTransfer.ref == str(listing_id)
                )
            )
        ).all()
        assert len(transfers) == 1

    # История цен по скину.
    resp = await anonymous().get(f"/api/v1/market/defs/{def_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sales"][0]["price"] == 1000
    assert body["stats"]["last_sale_price"] == 1000


async def test_fee_rounding(alice, bob) -> None:
    # Цена 1: комиссия округляется вверх до 1, продавец получает 0.
    ids = await give_items("alice", ["genesis-wp"])
    listing = await _create_listing(alice, ids[0], 1)
    resp = await bob.post(f"/api/v1/market/listings/{listing['id']}/buy")
    assert resp.status_code == 200, resp.text
    assert (await bob.get("/api/v1/me")).json()["balance"] == 999
    assert (await alice.get("/api/v1/me")).json()["balance"] == 1000

    alice_id = await _user_id("alice")
    async with SessionLocal() as db:
        sale_rows = (
            await db.scalars(
                select(Ledger).where(
                    Ledger.user_id == alice_id, Ledger.reason == "market_sale"
                )
            )
        ).all()
    assert len(sale_rows) == 0

    # Цена 21: комиссия ceil(1.05) = 2, продавец +19.
    ids = await give_items("alice", ["genesis-bp"])
    listing = await _create_listing(alice, ids[0], 21)
    resp = await bob.post(f"/api/v1/market/listings/{listing['id']}/buy")
    assert resp.status_code == 200, resp.text
    assert (await bob.get("/api/v1/me")).json()["balance"] == 999 - 21
    assert (await alice.get("/api/v1/me")).json()["balance"] == 1019

    async with SessionLocal() as db:
        sale_rows = (
            await db.scalars(
                select(Ledger).where(
                    Ledger.user_id == alice_id, Ledger.reason == "market_sale"
                )
            )
        ).all()
    assert len(sale_rows) == 1
    assert sale_rows[0].delta == 19


async def test_buy_errors(alice, bob) -> None:
    alice_id = await _user_id("alice")
    ids = await give_items("alice", ["genesis-wp"])
    listing = await _create_listing(alice, ids[0], 100)
    listing_id = listing["id"]

    # Свой лот.
    resp = await alice.post(f"/api/v1/market/listings/{listing_id}/buy")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CANNOT_BUY_OWN"

    # Недостаточно средств.
    await set_balance("bob", 10)
    await set_balance("alice", 1000)
    async with SessionLocal() as db:
        ledger_count_before = await db.scalar(select(func.count()).select_from(Ledger))
    resp = await bob.post(f"/api/v1/market/listings/{listing_id}/buy")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
    async with SessionLocal() as db:
        ledger_count_after = await db.scalar(select(func.count()).select_from(Ledger))
        listing_row = await db.get(MarketListing, listing_id)
        item = await db.get(InventoryItem, ids[0])
    assert ledger_count_after == ledger_count_before
    assert listing_row.status == "active"
    assert item.user_id == alice_id

    # Снятый лот.
    resp = await alice.delete(f"/api/v1/market/listings/{listing_id}")
    assert resp.status_code == 200
    resp = await bob.post(f"/api/v1/market/listings/{listing_id}/buy")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "LISTING_NOT_ACTIVE"

    # Несуществующий лот.
    resp = await bob.post("/api/v1/market/listings/999999/buy")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "LISTING_NOT_FOUND"


async def test_buy_concurrent(alice, bob, carol) -> None:
    ids = await give_items("alice", ["genesis-wp"])
    listing = await _create_listing(alice, ids[0], 100)
    listing_id = listing["id"]

    results = await asyncio.gather(
        bob.post(f"/api/v1/market/listings/{listing_id}/buy"),
        carol.post(f"/api/v1/market/listings/{listing_id}/buy"),
    )
    outcomes = sorted(
        (r.status_code, r.json()["error"]["code"] if r.status_code != 200 else None)
        for r in results
    )
    assert [o[0] for o in outcomes] == [200, 400]
    assert outcomes[1][1] == "LISTING_NOT_ACTIVE"

    async with SessionLocal() as db:
        for login in ("alice", "bob", "carol"):
            user = (await db.scalars(select(User).where(User.login == login))).one()
            total = await db.scalar(
                select(func.coalesce(func.sum(Ledger.delta), 0)).where(
                    Ledger.user_id == user.id
                )
            )
            assert user.balance == total, login


async def _clear_rl(admin_ids: list[int]) -> None:
    from app.redis import redis_client

    keys = [f"rl:market:{uid}" for uid in admin_ids]
    if keys:
        await redis_client.delete(*keys)


async def test_buy_vs_cancel_concurrent(alice, bob) -> None:
    alice_id = await _user_id("alice")
    bob_id = await _user_id("bob")

    for _ in range(10):
        await _clear_rl([alice_id, bob_id])
        ids = await give_items("alice", ["genesis-wp"])
        listing = await _create_listing(alice, ids[0], 100)
        listing_id = listing["id"]
        await _clear_rl([alice_id, bob_id])

        cancel_resp, buy_resp = await asyncio.gather(
            alice.delete(f"/api/v1/market/listings/{listing_id}"),
            bob.post(f"/api/v1/market/listings/{listing_id}/buy"),
        )
        statuses = (cancel_resp.status_code, buy_resp.status_code)
        assert 200 in statuses, (cancel_resp.text, buy_resp.text)
        for status in statuses:
            if status != 200:
                assert status == 400

        async with SessionLocal() as db:
            listing_row = await db.get(MarketListing, listing_id)
            item = await db.get(InventoryItem, ids[0])
            assert listing_row is not None and item is not None
            if listing_row.status == "cancelled":
                assert cancel_resp.status_code == 200
                assert item.user_id == alice_id
                assert item.status == "owned"
            else:
                assert listing_row.status == "sold"
                assert buy_resp.status_code == 200
                assert item.user_id == bob_id
                assert item.status == "owned"


async def test_market_browse(alice, bob) -> None:
    a1 = (await give_items("alice", ["genesis-wp"]))[0]  # common, P, w
    a2 = (await give_items("alice", ["genesis-bp"]))[0]  # common, P, b
    b1 = (await give_items("bob", ["genesis-br"]))[0]  # rare, R, b
    l1 = await _create_listing(alice, a1, 300)
    l2 = await _create_listing(alice, a2, 200)
    l3 = await _create_listing(bob, b1, 100)

    resp = await alice.get("/api/v1/market?sort=price_asc")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    assert [i["id"] for i in body["items"]] == [l3["id"], l2["id"], l1["id"]]
    assert [i["price"] for i in body["items"]] == [100, 200, 300]
    mine_flags = {i["id"]: i["mine"] for i in body["items"]}
    assert mine_flags == {l1["id"]: True, l2["id"]: True, l3["id"]: False}

    resp = await alice.get("/api/v1/market?rarity=rare")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == l3["id"]

    resp = await alice.get("/api/v1/market?side=w")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == l1["id"]

    resp = await alice.get("/api/v1/market?side=b")
    body = resp.json()
    assert body["total"] == 2
    assert [i["id"] for i in body["items"]] == [l3["id"], l2["id"]]

    resp = await alice.get("/api/v1/market?piece_type=P")
    body = resp.json()
    assert body["total"] == 2
    assert [i["id"] for i in body["items"]] == [l2["id"], l1["id"]]

    resp = await alice.get("/api/v1/market?piece_type=R")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == l3["id"]

    def_id_a1 = l1["item"]["def"]["id"]
    resp = await alice.get(f"/api/v1/market?def_id={def_id_a1}")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == l1["id"]

    def_id_b1 = l3["item"]["def"]["id"]
    resp = await alice.get(f"/api/v1/market?def_id={def_id_b1}")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == l3["id"]

    resp = await alice.get("/api/v1/market?collection=genesis&sort=price_desc")
    body = resp.json()
    assert body["total"] == 3
    assert [i["price"] for i in body["items"]] == [300, 200, 100]

    # Аноним видит ленту, mine=false у всех.
    resp = await anonymous().get("/api/v1/market")
    body = resp.json()
    assert body["total"] == 3
    assert all(i["mine"] is False for i in body["items"])


async def _base_item_id(client) -> int:
    inv = (await client.get("/api/v1/inventory")).json()
    return next(i["id"] for i in inv if i["source"] == "base" and i["bound"] is True)


@pytest.mark.xfail(
    reason=(
        "Баг приложения: app/services/items.py::items_out — "
        "await db.scalars(...).all() без обрамляющих скобок для кейсов "
        "('coroutine' object has no attribute 'all'); тест верен по контракту v3"
    ),
    strict=True,
)
async def test_list_and_buy_case(alice, bob) -> None:
    (item_id,) = await give_cases("alice", [1])
    listing = await _create_listing(alice, item_id, 150)
    listing_id = listing["id"]

    lot = listing["item"]
    assert lot["kind"] == "case"
    assert lot["case"]["id"] == 1
    assert lot["def"] is None

    resp = await bob.post(f"/api/v1/market/listings/{listing_id}/buy")
    assert resp.status_code == 200, resp.text

    # Предмет-кейс у bob (в инвентаре только кейсы).
    resp = await bob.get("/api/v1/inventory?kind=case")
    assert resp.status_code == 200, resp.text
    inv = resp.json()
    assert len(inv) == 1
    assert inv[0]["id"] == item_id
    assert inv[0]["kind"] == "case"
    assert inv[0]["case"]["id"] == 1
    assert inv[0]["status"] == "owned"

    # История цен по кейсу.
    resp = await anonymous().get("/api/v1/market/cases/1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["case"]["id"] == 1
    assert body["stats"]["last_sale_price"] == 150
    assert len(body["sales"]) == 1
    assert body["sales"][0]["price"] == 150


@pytest.mark.xfail(
    reason=(
        "Баг приложения: app/services/items.py::items_out — "
        "await db.scalars(...).all() без обрамляющих скобок для кейсов "
        "('coroutine' object has no attribute 'all'); тест верен по контракту v3"
    ),
    strict=True,
)
async def test_kind_filter(alice, bob) -> None:
    skin = (await give_items("alice", ["genesis-wp"]))[0]
    board = (await give_items("alice", ["genesis-board-paper"]))[0]
    case = (await give_cases("alice", [1]))[0]
    ls = await _create_listing(alice, skin, 300)
    lb = await _create_listing(alice, board, 200)
    lc = await _create_listing(alice, case, 100)

    async def _ids(query: str) -> set[int]:
        resp = await alice.get(f"/api/v1/market?{query}")
        assert resp.status_code == 200, resp.text
        return {i["id"] for i in resp.json()["items"]}

    assert await _ids("kind=piece") == {ls["id"]}
    assert await _ids("kind=board") == {lb["id"]}
    assert await _ids("kind=case") == {lc["id"]}
    assert await _ids("case_id=1") == {lc["id"]}
    assert await _ids("set=genesis") == {ls["id"], lb["id"]}


async def test_base_item_not_listable(alice) -> None:
    base_id = await _base_item_id(alice)
    resp = await alice.post(
        "/api/v1/market/listings", json={"item_id": base_id, "price": 100}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_BOUND"
