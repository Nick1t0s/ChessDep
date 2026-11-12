import pytest
from httpx import AsyncClient
from sqlalchemy import select

import app.core.clock as clock
from app.models import ItemDef, User
from app.models.market import MarketListing
from tests.conftest import anonymous, give_items


@pytest.mark.asyncio
async def test_trade_history_empty_and_auth(alice: AsyncClient):
    # Anonymous request rejected
    anon = anonymous()
    resp_anon = await anon.get("/api/v1/me/trades")
    assert resp_anon.status_code == 401

    # Empty user trade history
    resp = await alice.get("/api/v1/me/trades")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["items"] == []
    assert data["next_cursor"] is None
    assert data["summary"] == {
        "sold_count": 0,
        "bought_count": 0,
        "gross_sales": 0,
        "fees": 0,
        "net_sales": 0,
        "total_spent": 0,
    }


@pytest.mark.asyncio
async def test_trade_history_buys_sells_and_isolation(
    alice: AsyncClient, bob: AsyncClient, carol: AsyncClient, db, frozen
):
    alice_user = (await db.scalars(select(User).where(User.login == "alice"))).one()
    bob_user = (await db.scalars(select(User).where(User.login == "bob"))).one()
    carol_user = (await db.scalars(select(User).where(User.login == "carol"))).one()

    item_defs = (await db.scalars(select(ItemDef))).all()
    def1 = item_defs[0]
    def2 = item_defs[1]

    # Use real give_items to generate real InventoryItems
    alice_item_ids = await give_items("alice", [def1.code, def1.code])
    bob_item_ids = await give_items("bob", [def2.code])
    carol_item_ids = await give_items("carol", [def1.code])

    now = clock.now()
    # 1. Alice sells item to Bob (price: 1000, fee: 50, net: 950)
    listing1 = MarketListing(
        item_id=alice_item_ids[0],
        item_def_id=def1.id,
        seller_id=alice_user.id,
        buyer_id=bob_user.id,
        price=1000,
        fee=50,
        status="sold",
        created_at=now,
        closed_at=now,
    )
    # 2. Bob sells item to Alice (price: 600, fee: 30, net: 600 for buyer)
    listing2 = MarketListing(
        item_id=bob_item_ids[0],
        item_def_id=def2.id,
        seller_id=bob_user.id,
        buyer_id=alice_user.id,
        price=600,
        fee=30,
        status="sold",
        created_at=now,
        closed_at=now,
    )
    # 3. Alice cancelled listing (must be excluded)
    listing3 = MarketListing(
        item_id=alice_item_ids[1],
        item_def_id=def1.id,
        seller_id=alice_user.id,
        price=2000,
        status="cancelled",
        created_at=now,
    )
    # 4. Third party trade between Carol and Bob (must be isolated, not seen by Alice)
    listing_carol = MarketListing(
        item_id=carol_item_ids[0],
        item_def_id=def1.id,
        seller_id=carol_user.id,
        buyer_id=bob_user.id,
        price=5000,
        fee=250,
        status="sold",
        created_at=now,
        closed_at=now,
    )
    db.add_all([listing1, listing2, listing3, listing_carol])
    await db.commit()

    # Query Alice trades
    resp = await alice.get("/api/v1/me/trades")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["items"]) == 2
    # Verify summary isolation (Carol's 5000 is excluded)
    summary = data["summary"]
    assert summary["sold_count"] == 1
    assert summary["bought_count"] == 1
    assert summary["gross_sales"] == 1000
    assert summary["fees"] == 50
    assert summary["net_sales"] == 950
    assert summary["total_spent"] == 600

    # Direction filter sell
    resp_sell = await alice.get("/api/v1/me/trades?direction=sell")
    assert resp_sell.status_code == 200
    sell_data = resp_sell.json()
    assert len(sell_data["items"]) == 1
    assert sell_data["items"][0]["direction"] == "sell"
    assert sell_data["items"][0]["price"] == 1000
    assert sell_data["items"][0]["fee"] == 50
    assert sell_data["items"][0]["net"] == 950

    # Direction filter buy
    resp_buy = await alice.get("/api/v1/me/trades?direction=buy")
    assert resp_buy.status_code == 200
    buy_data = resp_buy.json()
    assert len(buy_data["items"]) == 1
    assert buy_data["items"][0]["direction"] == "buy"
    assert buy_data["items"][0]["price"] == 600
    assert buy_data["items"][0]["fee"] == 0
    assert buy_data["items"][0]["net"] == 600

    # Scoped item_def_id filter
    resp_def = await alice.get(f"/api/v1/me/trades?item_def_id={def1.id}")
    assert resp_def.status_code == 200
    def_data = resp_def.json()
    assert len(def_data["items"]) == 1
    assert def_data["summary"]["sold_count"] == 1
    assert def_data["summary"]["bought_count"] == 0
    assert def_data["summary"]["gross_sales"] == 1000

    # Pagination test: limit 1 returns next_cursor
    resp_page1 = await alice.get("/api/v1/me/trades?limit=1")
    assert resp_page1.status_code == 200
    page1 = resp_page1.json()
    assert len(page1["items"]) == 1
    assert page1["next_cursor"] is not None

    resp_page2 = await alice.get(f"/api/v1/me/trades?limit=1&before_id={page1['next_cursor']}")
    assert resp_page2.status_code == 200
    page2 = resp_page2.json()
    assert len(page2["items"]) == 1
    assert page2["items"][0]["id"] < page1["items"][0]["id"]
