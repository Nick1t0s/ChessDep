import asyncio

import app.core.clock as clock
from sqlalchemy import select
from tests.conftest import (
    SessionLocal,
    count_queries,
    give_items,
    start_game,
)
from app.models import InventoryItem, Loadout

SLOTS = ("wP", "wN", "wB", "wR", "wQ", "wK", "bP", "bN", "bB", "bR", "bQ", "bK")


async def test_inventory_and_equip(alice, db) -> None:
    ids = await give_items("alice", ["genesis-wn", "genesis-wp", "genesis-bq"])

    resp = await alice.put("/api/v1/loadout/wN", json={"inventory_item_id": ids[0]})
    assert resp.status_code == 200, resp.text
    loadout = resp.json()
    assert set(loadout) == set(SLOTS)
    assert loadout["wN"]["id"] == ids[0]

    inv = (await alice.get("/api/v1/inventory")).json()
    entry = next(i for i in inv if i["id"] == ids[0])
    assert entry["equipped_slot"] == "wN"

    resp = await alice.put("/api/v1/loadout/bP", json={"inventory_item_id": ids[1]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_SLOT_MISMATCH"

    resp = await alice.put("/api/v1/loadout/board", json={"inventory_item_id": ids[2]})
    assert resp.status_code == 422

    inv_w = (await alice.get("/api/v1/inventory?side=w")).json()
    assert [i["def"]["code"] for i in inv_w] == ["genesis-wn", "genesis-wp"]

    inv_bq = (await alice.get("/api/v1/inventory?slot=bQ")).json()
    assert [i["def"]["code"] for i in inv_bq] == ["genesis-bq"]

    resp = await alice.put("/api/v1/loadout/wN", json={"inventory_item_id": None})
    assert resp.status_code == 200, resp.text
    loadout = resp.json()
    assert set(loadout) == set(SLOTS)
    assert all(loadout[key] is None for key in SLOTS)

    loadout = (await alice.get("/api/v1/loadout")).json()
    assert set(loadout) == set(SLOTS)
    assert all(loadout[key] is None for key in SLOTS)


async def test_equip_foreign_or_burned(alice, bob) -> None:
    bob_ids = await give_items("bob", ["genesis-wn"])
    resp = await alice.put("/api/v1/loadout/wN", json={"inventory_item_id": bob_ids[0]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"

    alice_ids = await give_items("alice", ["genesis-wr"])
    async with SessionLocal() as burn_db:
        async with burn_db.begin():
            item = await burn_db.get(InventoryItem, alice_ids[0])
            assert item is not None
            item.status = "burned"
            item.burned_at = clock.now()

    resp = await alice.put("/api/v1/loadout/wN", json={"inventory_item_id": alice_ids[0]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"


async def test_loadout_snapshot_in_game(alice, bob, rng) -> None:
    alice_ids = await give_items("alice", ["genesis-wq", "genesis-bq"])
    resp = await alice.put("/api/v1/loadout/wQ", json={"inventory_item_id": alice_ids[0]})
    assert resp.status_code == 200, resp.text
    resp = await alice.put("/api/v1/loadout/bQ", json={"inventory_item_id": alice_ids[1]})
    assert resp.status_code == 200, resp.text

    bob_ids = await give_items("bob", ["genesis-wr"])
    resp = await bob.put("/api/v1/loadout/wR", json={"inventory_item_id": bob_ids[0]})
    assert resp.status_code == 200, resp.text

    wq = {
        "code": "genesis-wq",
        "name": "Genesis | Белый ферзь",
        "rarity": "epic",
        "asset": {"type": "stub", "color": "#ffffff"},
    }
    bq = {
        "code": "genesis-bq",
        "name": "Genesis | Чёрный ферзь",
        "rarity": "epic",
        "asset": {"type": "stub", "color": "#ffc93c"},
    }
    wr = {
        "code": "genesis-wr",
        "name": "Genesis | Белая ладья",
        "rarity": "rare",
        "asset": {"type": "stub", "color": "#ffffff"},
    }

    game_id = await start_game(alice, bob, rng)
    state = (await alice.get(f"/api/v1/games/{game_id}")).json()
    if state["you"] == "white":
        assert state["players"]["white"]["loadout"] == {"Q": wq}
        assert state["players"]["black"]["loadout"] == {}
        slot = "wQ"
    else:
        assert state["players"]["white"]["loadout"] == {"R": wr}
        assert state["players"]["black"]["loadout"] == {"Q": bq}
        slot = "bQ"

    resp = await alice.put(f"/api/v1/loadout/{slot}", json={"inventory_item_id": None})
    assert resp.status_code == 200
    state2 = (await alice.get(f"/api/v1/games/{game_id}")).json()
    if state["you"] == "white":
        assert state2["players"]["white"]["loadout"] == {"Q": wq}
        assert state2["players"]["black"]["loadout"] == {}
    else:
        assert state2["players"]["white"]["loadout"] == {"R": wr}
        assert state2["players"]["black"]["loadout"] == {"Q": bq}


async def test_inventory_hides_burned(alice, db) -> None:
    ids = await give_items("alice", ["genesis-wp", "genesis-bp", "genesis-wr"])
    async with SessionLocal() as burn_db:
        async with burn_db.begin():
            item = await burn_db.get(InventoryItem, ids[1])
            item.status = "burned"
            item.burned_at = clock.now()

    resp = await alice.get("/api/v1/inventory?sort=value")
    assert resp.status_code == 200
    inv = resp.json()
    assert [i["id"] for i in inv] == [ids[2], ids[0]]
    for entry in inv:
        assert entry["status"] == "owned"


async def test_loadout_concurrent_put(alice) -> None:
    ids = await give_items("alice", ["genesis-wp"])
    item_id = ids[0]

    async def alice_id() -> int:
        from app.models import User

        async with SessionLocal() as db:
            return (
                await db.scalars(select(User.id).where(User.login == "alice"))
            ).one()

    responses = await asyncio.gather(
        *(
            alice.put("/api/v1/loadout/wP", json={"inventory_item_id": item_id})
            for _ in range(5)
        )
    )
    for resp in responses:
        assert resp.status_code == 200, resp.text

    async with SessionLocal() as db:
        rows = (
            await db.scalars(select(Loadout).where(Loadout.user_id == await alice_id()))
        ).all()
    assert len(rows) == 1
    assert rows[0].slot == "wP"
    assert rows[0].inventory_item_id == item_id


async def test_inventory_query_count(alice) -> None:
    ids = await give_items("alice", ["genesis-wp"] * 30)
    assert len(ids) == 30

    async with count_queries() as log:
        resp = await alice.get("/api/v1/inventory")
    assert resp.status_code == 200
    queries = [q for q in log if not q.lstrip().upper().startswith("COMMIT")]
    assert len(queries) <= 12, len(queries)
