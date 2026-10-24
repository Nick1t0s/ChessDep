from tests.conftest import give_items, set_balance


async def test_sale_notice_once(alice, bob) -> None:
    ids = await give_items("alice", ["genesis-wp"])
    resp = await alice.post("/api/v1/market/listings", json={"item_id": ids[0], "price": 1000})
    assert resp.status_code == 201, resp.text
    listing_id = resp.json()["id"]
    await set_balance("bob", 5000)
    resp = await bob.post(f"/api/v1/market/listings/{listing_id}/buy")
    assert resp.status_code == 200, resp.text

    resp = await alice.get("/api/v1/me/sales/unseen")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["sales"]) == 1
    sale = body["sales"][0]
    assert sale["listing_id"] == listing_id
    assert sale["price"] == 1000
    assert sale["payout"] == 950
    assert sale["buyer_login"] == "bob"
    assert sale["name"]
    me = (await alice.get("/api/v1/me")).json()
    assert body["balance"] == me["balance"]

    again = (await alice.get("/api/v1/me/sales/unseen")).json()
    assert again["sales"] == []
    assert (await bob.get("/api/v1/me/sales/unseen")).json()["sales"] == []


async def test_cancelled_listing_no_notice(alice) -> None:
    ids = await give_items("alice", ["genesis-wp"])
    resp = await alice.post("/api/v1/market/listings", json={"item_id": ids[0], "price": 1000})
    listing_id = resp.json()["id"]
    resp = await alice.delete(f"/api/v1/market/listings/{listing_id}")
    assert resp.status_code in (200, 204), resp.text
    assert (await alice.get("/api/v1/me/sales/unseen")).json()["sales"] == []
