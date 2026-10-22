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


async def test_inventory_and_equip(alice, db) -> None:
    ids = await give_items("alice", ["genesis-knight-chalk", "genesis-board-paper"])

    resp = await alice.put("/api/v1/loadout/N", json={"inventory_item_id": ids[0]})
    assert resp.status_code == 200, resp.text

    inv = (await alice.get("/api/v1/inventory")).json()
    entry = next(i for i in inv if i["id"] == ids[0])
    assert entry["equipped_slot"] == "N"

    resp = await alice.put("/api/v1/loadout/B", json={"inventory_item_id": ids[0]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_SLOT_MISMATCH"

    resp = await alice.put("/api/v1/loadout/board", json={"inventory_item_id": ids[1]})
    assert resp.status_code == 200, resp.text
    loadout = resp.json()
    assert loadout["board"]["id"] == ids[1]

    resp = await alice.put("/api/v1/loadout/N", json={"inventory_item_id": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["N"] is None

    loadout = (await alice.get("/api/v1/loadout")).json()
    assert loadout["N"] is None
    assert loadout["board"]["id"] == ids[1]
    assert all(loadout[key] is None for key in ("P", "B", "R", "Q", "K"))


async def test_equip_foreign_or_burned(alice, bob) -> None:
    bob_ids = await give_items("bob", ["genesis-knight-chalk"])
    resp = await alice.put("/api/v1/loadout/N", json={"inventory_item_id": bob_ids[0]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"

    alice_ids = await give_items("alice", ["genesis-king-frost"])
    async with SessionLocal() as burn_db:
        async with burn_db.begin():
            item = await burn_db.get(InventoryItem, alice_ids[0])
            assert item is not None
            item.status = "burned"
            item.burned_at = clock.now()

    resp = await alice.put("/api/v1/loadout/N", json={"inventory_item_id": alice_ids[0]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"


async def test_loadout_snapshot_in_game(alice, bob, rng) -> None:
    ids = await give_items("alice", ["genesis-pawn-chalk"])
    resp = await alice.put("/api/v1/loadout/P", json={"inventory_item_id": ids[0]})
    assert resp.status_code == 200, resp.text

    game_id = await start_game(alice, bob, rng)
    state = (await alice.get(f"/api/v1/games/{game_id}")).json()
    assert state["you"] == "white"
    expected = {
        "code": "genesis-pawn-chalk",
        "name": "Пешка | Мел",
        "rarity": "common",
        "asset": {"type": "stub", "color": "#ffffff"},
    }
    assert state["players"]["white"]["loadout"] == {"P": expected}
    assert state["players"]["black"]["loadout"] == {}

    resp = await alice.put("/api/v1/loadout/P", json={"inventory_item_id": None})
    assert resp.status_code == 200
    state2 = (await alice.get(f"/api/v1/games/{game_id}")).json()
    assert state2["players"]["white"]["loadout"] == {"P": expected}


async def test_inventory_hides_burned(alice, db) -> None:
    ids = await give_items(
        "alice",
        ["genesis-pawn-chalk", "genesis-board-paper", "genesis-pawn-frost"],
    )
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
    ids = await give_items("alice", ["genesis-pawn-chalk"])
    item_id = ids[0]

    async def alice_id() -> int:
        from app.models import User

        async with SessionLocal() as db:
            return (
                await db.scalars(select(User.id).where(User.login == "alice"))
            ).one()

    responses = await asyncio.gather(
        *(
            alice.put("/api/v1/loadout/P", json={"inventory_item_id": item_id})
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
    assert rows[0].slot == "P"
    assert rows[0].inventory_item_id == item_id


async def test_inventory_query_count(alice) -> None:
    ids = await give_items("alice", ["genesis-pawn-chalk"] * 30)
    assert len(ids) == 30

    async with count_queries() as log:
        resp = await alice.get("/api/v1/inventory")
    assert resp.status_code == 200
    queries = [q for q in log if not q.lstrip().upper().startswith("COMMIT")]
    assert len(queries) <= 12, len(queries)
