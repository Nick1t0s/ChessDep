import asyncio
import uuid

import pytest
from sqlalchemy import select

import app.core.clock as clock
import app.core.clock as clock_module
from app.db import SessionLocal
from app.models import ActivePlayer, InventoryItem, ItemDef, Loadout, User
from app.redis import redis_client
from app.seed_data import BASE_COLORS, item_name
from app.services import matchmaking
from tests.conftest import (
    count_queries,
    give_cases,
    give_items,
    start_game,
)

LOADOUT = ("wP", "wN", "wB", "wR", "wQ", "wK", "bP", "bN", "bB", "bR", "bQ", "bK", "board")
SNAPSHOT_KEYS = ("P", "N", "B", "R", "Q", "K", "board")


def _base_skin(slot: str) -> dict:
    side, piece_type = slot[0], slot[1:]
    return {
        "code": f"base-{side}{piece_type.lower()}",
        "name": item_name("Базовая", side, piece_type),
        "rarity": "common",
        "asset": {"type": "stub", "color": BASE_COLORS[side]},
    }


def base_snapshot(side: str) -> dict:
    snap = {}
    for piece_type in ("P", "N", "B", "R", "Q", "K"):
        snap[piece_type] = _base_skin(side + piece_type)
    snap["board"] = dict(BASE_BOARD)
    return snap


BASE_BOARD = {
    "code": "base-board",
    "name": "Базовая доска",
    "rarity": "common",
    "asset": {"type": "stub", "light": "#454f77", "dark": "#262e4d"},
}

GENESIS_BOARD_PAPER = {
    "code": "genesis-board-paper",
    "name": "Genesis | Бумага",
    "rarity": "uncommon",
    "asset": {"type": "stub", "light": "#ffffff", "dark": "#e5e5e5"},
}


async def _def_id(code: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(ItemDef.id).where(ItemDef.code == code))


async def _user_id(login: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(User.id).where(User.login == login))


async def _base_ids(login: str) -> list[int]:
    async with SessionLocal() as db:
        user_id = await db.scalar(select(User.id).where(User.login == login))
        return list(
            (
                await db.scalars(
                    select(InventoryItem.id)
                    .where(InventoryItem.user_id == user_id, InventoryItem.source == "base")
                    .order_by(InventoryItem.id)
                )
            ).all()
        )


def _user_key(user_id: int) -> str:
    return f"mm:user:{user_id}"


def _queue_key(tc: str) -> str:
    return f"mm:queue:{tc}"


async def test_base_items_on_register(alice, db) -> None:
    inv = (await alice.get("/api/v1/inventory")).json()
    assert len(inv) == 13, inv
    slot_by_code = {}
    for slot in LOADOUT:
        code = f"base-{slot.lower()}"
        slot_by_code[code] = slot
    for entry in inv:
        assert entry["kind"] == "skin"
        assert entry["source"] == "base"
        assert entry["bound"] is True
        assert entry["wear"] == 0.0
        assert entry["status"] == "owned"
        assert entry["def"]["code"] in slot_by_code
        assert entry["equipped_slot"] == slot_by_code[entry["def"]["code"]]

    resp = await alice.get("/api/v1/loadout")
    assert resp.status_code == 200, resp.text
    loadout = resp.json()
    assert set(loadout) == set(LOADOUT) | {"complete"}
    assert loadout["complete"] is True
    for slot in LOADOUT:
        assert loadout[slot] is not None, slot
        assert loadout[slot]["def"]["code"] == f"base-{slot.lower()}"


async def test_inventory_and_equip(alice) -> None:
    base_board_id = ((await alice.get("/api/v1/loadout")).json())["board"]["id"]
    ids = await give_items("alice", ["genesis-wq", "genesis-board-paper"])

    resp = await alice.put("/api/v1/loadout/wQ", json={"inventory_item_id": ids[0]})
    assert resp.status_code == 200, resp.text
    loadout = resp.json()
    assert set(loadout) == set(LOADOUT) | {"complete"}
    assert loadout["complete"] is True
    assert loadout["wQ"]["id"] == ids[0]

    resp = await alice.put("/api/v1/loadout/board", json={"inventory_item_id": ids[1]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["board"]["id"] == ids[1]

    inv = (await alice.get("/api/v1/inventory")).json()
    entry = next(i for i in inv if i["id"] == ids[0])
    assert entry["equipped_slot"] == "wQ"

    case_ids = await give_cases("alice", [1])

    # genesis-wq в bQ — не тот слот.
    resp = await alice.put("/api/v1/loadout/bQ", json={"inventory_item_id": ids[0]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_SLOT_MISMATCH"

    # доска в wP.
    resp = await alice.put("/api/v1/loadout/wP", json={"inventory_item_id": ids[1]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_SLOT_MISMATCH"

    # предмет-кейс никуда не годится.
    resp = await alice.put("/api/v1/loadout/wQ", json={"inventory_item_id": case_ids[0]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_SLOT_MISMATCH"
    resp = await alice.put("/api/v1/loadout/board", json={"inventory_item_id": case_ids[0]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_SLOT_MISMATCH"

    # несуществующий слот.
    resp = await alice.put("/api/v1/loadout/x", json={"inventory_item_id": ids[0]})
    assert resp.status_code == 422

    # Фильтры.
    boards = (await alice.get("/api/v1/inventory?kind=board")).json()
    assert [i["id"] for i in boards] == [ids[1], base_board_id]
    assert all(i["kind"] == "skin" for i in boards)

    slot_boards = (await alice.get("/api/v1/inventory?slot=board")).json()
    assert [i["id"] for i in slot_boards] == [ids[1], base_board_id]

    whites = (await alice.get("/api/v1/inventory?side=w")).json()
    assert [i["def"]["code"] for i in whites] == [
        "genesis-wq",
        "base-wp",
        "base-wn",
        "base-wb",
        "base-wr",
        "base-wq",
        "base-wk",
    ]

    # Очистка слота базовой доски.
    resp = await alice.put("/api/v1/loadout/board", json={"inventory_item_id": None})
    assert resp.status_code == 200, resp.text
    loadout = resp.json()
    assert set(loadout) == set(LOADOUT) | {"complete"}
    assert loadout["board"] is None
    assert loadout["complete"] is False


@pytest.mark.xfail(
    strict=True,
    reason=(
        "app/services/items.py::items_out — отсутствует await db.scalars(...) при загрузке "
        "кейсов: любой вывод предмета-кейса через GET /inventory падает с AttributeError → 500"
    ),
)
async def test_case_item_in_inventory(alice) -> None:
    case_ids = await give_cases("alice", [1])
    resp = await alice.get("/api/v1/inventory?kind=case")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert [i["id"] for i in items] == [case_ids[0]]
    assert items[0]["kind"] == "case"
    assert items[0]["item_def"] is None
    assert items[0]["case"]["code"] == "genesis"


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


async def test_loadout_incomplete_blocks_play(alice, bob) -> None:
    base_wk_id = ((await alice.get("/api/v1/loadout")).json())["wK"]["id"]

    # Инвайт создаётся ДО снятия слота.
    resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    assert resp.status_code == 200, resp.text
    alice_code = resp.json()["code"]

    resp = await alice.put("/api/v1/loadout/wK", json={"inventory_item_id": None})
    assert resp.status_code == 200, resp.text
    loadout = resp.json()
    assert loadout["wK"] is None
    assert loadout["complete"] is False

    resp = await alice.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "LOADOUT_INCOMPLETE"

    resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "LOADOUT_INCOMPLETE"

    # bob создаёт инвайт, alice-приёмник некомплект → отказ.
    resp = await bob.post("/api/v1/invites", json={"time_control": "3+2"})
    assert resp.status_code == 200, resp.text
    bob_code = resp.json()["code"]
    resp = await alice.post(f"/api/v1/invites/{bob_code}/accept")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "LOADOUT_INCOMPLETE"

    # bob принимает инвайт владельца без экипировки — create_game создаёт игру.
    resp = await bob.post(f"/api/v1/invites/{alice_code}/accept")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "LOADOUT_INCOMPLETE"

    # Возвращаем базовый скин — игра стартует.
    resp = await alice.put("/api/v1/loadout/wK", json={"inventory_item_id": base_wk_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["complete"] is True

    resp = await bob.post(f"/api/v1/invites/{alice_code}/accept")
    assert resp.status_code == 200, resp.text
    game_id = resp.json()["game_id"]
    assert uuid.UUID(game_id)
    resp = await alice.get(f"/api/v1/games/{game_id}")
    assert resp.status_code == 200, resp.text


@pytest.mark.xfail(
    strict=True,
    reason=(
        "app/services/matchmaking.py::_match_pair — исключение LOADOUT_INCOMPLETE уходит в `raise` "
        "(проверяется только ALREADY_IN_GAME, ветка удаления игроков из очереди, стр. 105–116, "
        "недостижима): по контракту незавершённый игрок должен быть удалён из очереди, но "
        "приложение возвращает его в очередь и бросает AppError наружу tick"
    ),
)
async def test_matchmaking_drops_incomplete(alice, bob) -> None:
    resp = await alice.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202, resp.text
    resp = await bob.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202, resp.text
    alice_id, bob_id = await _user_id("alice"), await _user_id("bob")

    base_wk_id = ((await alice.get("/api/v1/loadout")).json())["wK"]["id"]
    resp = await alice.put("/api/v1/loadout/wK", json={"inventory_item_id": None})
    assert resp.status_code == 200, resp.text

    await matchmaking.tick(clock_module.now())

    resp = await alice.get("/api/v1/matchmaking/status")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "idle", resp.text
    assert await redis_client.get(_user_key(alice_id)) is None

    resp = await bob.get("/api/v1/matchmaking/status")
    assert resp.json()["status"] == "queued", resp.text
    assert await redis_client.lindex(_queue_key("3+2"), 0) == str(bob_id)
    assert await redis_client.llen(_queue_key("3+2")) == 1

    async with SessionLocal() as db:
        assert (await db.scalars(select(ActivePlayer))).all() == []


async def test_loadout_snapshot_in_game(alice, bob, rng) -> None:
    alice_ids = await give_items(
        "alice", ["genesis-wq", "genesis-bq", "genesis-board-paper"]
    )
    resp = await alice.put("/api/v1/loadout/wQ", json={"inventory_item_id": alice_ids[0]})
    assert resp.status_code == 200, resp.text
    resp = await alice.put("/api/v1/loadout/bQ", json={"inventory_item_id": alice_ids[1]})
    assert resp.status_code == 200, resp.text
    resp = await alice.put("/api/v1/loadout/board", json={"inventory_item_id": alice_ids[2]})
    assert resp.status_code == 200, resp.text

    genesis_q = {
        "code": "genesis-wq",
        "name": "Genesis | Белый ферзь",
        "rarity": "epic",
        "asset": {"type": "stub", "color": "#ffffff"},
    }
    genesis_q_black = {
        "code": "genesis-bq",
        "name": "Genesis | Чёрный ферзь",
        "rarity": "epic",
        "asset": {"type": "stub", "color": "#ffc93c"},
    }

    game_id = await start_game(alice, bob, rng)
    state = (await alice.get(f"/api/v1/games/{game_id}")).json()
    if state["you"] == "white":
        my_color, other_color = "white", "black"
        my_side, other_side = "w", "b"
        my_q = genesis_q
    else:
        my_color, other_color = "black", "white"
        my_side, other_side = "b", "w"
        my_q = genesis_q_black

    my_base = base_snapshot(my_side)
    my_expected = dict(my_base)
    my_expected["Q"] = my_q
    my_expected["board"] = GENESIS_BOARD_PAPER
    other_base = base_snapshot(other_side)

    my_loadout = state["players"][my_color]["loadout"]
    assert len(my_loadout) == 7, my_loadout
    assert set(my_loadout) == set(SNAPSHOT_KEYS)
    assert my_loadout == my_expected

    their_loadout = state["players"][other_color]["loadout"]
    assert len(their_loadout) == 7, their_loadout
    assert their_loadout == other_base
    assert their_loadout["board"] == BASE_BOARD

    # Смена экипировки после начала партии не меняет снапшот.
    resp = await alice.put("/api/v1/loadout/bQ", json={"inventory_item_id": None})
    assert resp.status_code == 200, resp.text
    state2 = (await alice.get(f"/api/v1/games/{game_id}")).json()
    assert state2["players"][my_color]["loadout"] == my_expected


async def test_bound_items_rules(alice, bob) -> None:
    loadout = (await alice.get("/api/v1/loadout")).json()
    base_item_id = loadout["wP"]["id"]
    target_id = await _def_id("genesis-wq")

    resp = await alice.post(
        "/api/v1/market/listings", json={"item_id": base_item_id, "price": 1}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_BOUND"

    resp = await alice.post(
        "/api/v1/gifts", json={"item_id": base_item_id, "to_login": "bob", "note": None}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_BOUND"

    resp = await alice.post(
        "/api/v1/upgrade/preview",
        json={"input_ids": [base_item_id], "target_def_id": target_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["allowed"] is False
    assert body["reason"] == "ITEM_BOUND"

    # Кейс во входах апгрейда.
    case_id = (await give_cases("alice", [1]))[0]
    resp = await alice.post(
        "/api/v1/upgrade/preview",
        json={"input_ids": [case_id], "target_def_id": target_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["allowed"] is False
    assert body["reason"] == "ITEM_NOT_UPGRADABLE"

    # Апгрейд напрямую — 400.
    resp = await alice.post(
        "/api/v1/upgrade", json={"input_ids": [base_item_id], "target_def_id": target_id}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_BOUND"

    resp = await alice.post(
        "/api/v1/upgrade", json={"input_ids": [case_id], "target_def_id": target_id}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_NOT_UPGRADABLE"


async def test_inventory_hides_burned(alice, db) -> None:
    ids = await give_items("alice", ["genesis-wp", "genesis-bp", "genesis-wr"])
    async with SessionLocal() as burn_db:
        async with burn_db.begin():
            item = await burn_db.get(InventoryItem, ids[1])
            item.status = "burned"
            item.burned_at = clock.now()

    base_ids = await _base_ids("alice")
    resp = await alice.get("/api/v1/inventory?sort=value")
    assert resp.status_code == 200
    inv = resp.json()
    assert [i["id"] for i in inv] == [ids[2], ids[0]] + base_ids
    for entry in inv:
        assert entry["status"] == "owned"


async def test_loadout_concurrent_put(alice) -> None:
    ids = await give_items("alice", ["genesis-wp"])
    item_id = ids[0]

    async def alice_id() -> int:
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
    # 12 базовых слотов + слот wP.
    assert len(rows) == 13
    wp = [row for row in rows if row.slot == "wP"]
    assert len(wp) == 1
    assert wp[0].inventory_item_id == item_id


async def test_inventory_query_count(alice) -> None:
    ids = await give_items("alice", ["genesis-wp"] * 30)
    assert len(ids) == 30

    async with count_queries() as log:
        resp = await alice.get("/api/v1/inventory")
    assert resp.status_code == 200
    queries = [q for q in log if not q.lstrip().upper().startswith("COMMIT")]
    assert len(queries) <= 12, len(queries)
