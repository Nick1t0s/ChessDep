import asyncio
import json
import uuid

from sqlalchemy import func, select, update

from app.db import SessionLocal
from app.models import ActivePlayer, Game, GameEvent, Ledger, Roll, Setting, User
from app.redis import redis_client
from app.services import settings as settings_service
from app.services.pubsub import game_channel
from tests.conftest import register, set_fen, start_game


async def test_invite_creates_game(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    for client, you, legal_count in ((alice, "white", 20), (bob, "black", 0)):
        resp = await client.get(f"/api/v1/games/{game_id}")
        assert resp.status_code == 200, resp.text
        state = resp.json()
        assert state["id"] == game_id
        assert state["you"] == you
        assert len(state["legal_moves"]) == legal_count
        active = await client.get("/api/v1/me/active-game")
        assert active.status_code == 200
        assert active.json()["game_id"] == game_id


async def test_stranger_cannot_see_game(alice, bob, rng, client) -> None:
    game_id = await start_game(alice, bob, rng)
    resp = await register(client, "carol")
    assert resp.status_code == 201

    resp = await client.get(f"/api/v1/games/{game_id}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GAME_NOT_FOUND"

    resp = await client.post(f"/api/v1/games/{game_id}/move", json={"uci": "e2e4"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GAME_NOT_FOUND"


async def test_invite_errors(alice, bob, frozen) -> None:
    resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    assert resp.status_code == 200
    code = resp.json()["code"]

    resp = await alice.post(f"/api/v1/invites/{code}/accept")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVITE_OWN"

    resp = await alice.post("/api/v1/invites/zzzzzzzzzz/accept")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "INVITE_NOT_FOUND"

    resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    assert resp.status_code == 200
    code = resp.json()["code"]
    frozen.advance(601)
    resp = await bob.post(f"/api/v1/invites/{code}/accept")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVITE_EXPIRED"

    resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    assert resp.status_code == 200
    code = resp.json()["code"]
    resp = await bob.post(f"/api/v1/invites/{code}/accept")
    assert resp.status_code == 200, resp.text
    resp = await bob.post(f"/api/v1/invites/{code}/accept")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVITE_EXPIRED"

    resp = await alice.post("/api/v1/invites", json={"time_control": "1+0"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_TIME_CONTROL"


async def test_one_active_game_per_user(alice, bob, rng, client) -> None:
    game_id = await start_game(alice, bob, rng)

    resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ALREADY_IN_GAME"

    resp = await alice.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ALREADY_IN_GAME"

    resp = await register(client, "carol")
    assert resp.status_code == 201
    resp = await client.post("/api/v1/invites", json={"time_control": "3+2"})
    code = resp.json()["code"]
    resp = await alice.post(f"/api/v1/invites/{code}/accept")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ALREADY_IN_GAME"


async def test_move_flow(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    url = f"/api/v1/games/{game_id}/move"

    resp = await alice.post(url, json={"uci": "e2e4"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["version"] == 1

    resp = await alice.post(url, json={"uci": "e2e4"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NOT_YOUR_TURN"

    resp = await bob.post(url, json={"uci": "e7e5"})
    assert resp.status_code == 200, resp.text

    resp = await alice.post(url, json={"uci": "e1e8"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ILLEGAL_MOVE"


async def test_move_version_conflict(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    resp = await alice.post(
        f"/api/v1/games/{game_id}/move", json={"uci": "e2e4", "expected_version": 5}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "VERSION_CONFLICT"


async def test_concurrent_moves(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    url = f"/api/v1/games/{game_id}/move"

    async def one() -> tuple[int, dict]:
        resp = await alice.post(url, json={"uci": "e2e4"})
        return resp.status_code, resp.json()

    results = await asyncio.gather(*[one() for _ in range(5)])
    ok = [r for r in results if r[0] == 200]
    failed = [r for r in results if r[0] == 400]
    assert len(ok) == 1
    assert len(failed) == 4
    assert all(r[1]["error"]["code"] == "NOT_YOUR_TURN" for r in failed)

    async with SessionLocal() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(GameEvent)
            .where(GameEvent.game_id == uuid.UUID(game_id), GameEvent.kind == "move")
        )
    assert count == 1


async def test_fools_mate_finishes_game(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    moves = ((alice, "f2f3"), (bob, "e7e5"), (alice, "g2g4"), (bob, "d8h4"))
    for client, uci in moves:
        resp = await client.post(
            f"/api/v1/games/{game_id}/move", json={"uci": uci}
        )
        assert resp.status_code == 200, resp.text

    state = (await alice.get(f"/api/v1/games/{game_id}")).json()
    assert state["status"] == "finished"
    assert state["result"] == "black"
    assert state["end_reason"] == "checkmate"

    async with SessionLocal() as db:
        gid = uuid.UUID(game_id)
        ap_count = await db.scalar(
            select(func.count()).select_from(ActivePlayer).where(ActivePlayer.game_id == gid)
        )
        game = await db.get(Game, gid)
        ledger_count = await db.scalar(
            select(func.count())
            .select_from(Ledger)
            .where(Ledger.reason.in_(("game_win", "game_draw")))
        )
        assert game is not None
        assert game.white_elo_before == 1200
        assert game.black_elo_before == 1200
        assert game.white_elo_after == 1184
        assert game.black_elo_after == 1216
        assert game.white_reward == 0
        assert game.black_reward == 0
        white = await db.get(User, game.white_id)
        black = await db.get(User, game.black_id)
        assert white.elo == 1184
        assert black.elo == 1216
    assert ap_count == 0
    assert ledger_count == 0


async def test_threefold(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    sequence = ["g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1", "f6g8"]
    url = f"/api/v1/games/{game_id}/move"
    for index, uci in enumerate(sequence):
        client = alice if index % 2 == 0 else bob
        resp = await client.post(url, json={"uci": uci})
        assert resp.status_code == 200, resp.text

    state = (await alice.get(f"/api/v1/games/{game_id}")).json()
    assert state["status"] == "finished"
    assert state["result"] == "draw"
    assert state["end_reason"] == "threefold"


async def test_dep_success_and_fail(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    rng.values = [0.0]
    dep_url = f"/api/v1/games/{game_id}/dep"
    resp = await alice.post(dep_url, json={"square": "b1", "target": "Q"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["chance_text"] == "33.33%"
    state = data["state"]
    assert {"square": "b1", "piece": "Q", "color": "white"} in state["board"]
    assert state["deps"]["white_used"] == 1

    async with SessionLocal() as db:
        roll = (await db.scalars(select(Roll).where(Roll.kind == "dep"))).one()
        assert roll.roll_value == 0.0
        assert abs(float(roll.chance) - 1.0 / 3.0) < 1e-6
        assert roll.ref == game_id
        assert roll.input["from"] == "N"
        assert roll.outcome["success"] is True

    # Завершаем партию (после депа обязателен ход), чтобы начать новую.
    resp = await alice.post(f"/api/v1/games/{game_id}/move", json={"uci": "e2e4"})
    assert resp.status_code == 200, resp.text
    resp = await bob.post(f"/api/v1/games/{game_id}/resign")
    assert resp.status_code == 200, resp.text

    game_id2 = await start_game(alice, bob, rng)
    rng.values = [0.99]
    resp = await alice.post(f"/api/v1/games/{game_id2}/dep", json={"square": "b1", "target": "Q"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is False
    board_squares = {(sq["square"], sq["piece"]) for sq in data["state"]["board"]}
    assert ("b1", "N") not in board_squares
    assert ("b1", "Q") not in board_squares


async def test_dep_once_per_turn_and_limit(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    dep_url = f"/api/v1/games/{game_id}/dep"
    move_url = f"/api/v1/games/{game_id}/move"

    rng.values = [0.99]
    resp = await alice.post(dep_url, json={"square": "b1", "target": "Q"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is False

    resp = await alice.post(dep_url, json={"square": "b1", "target": "Q"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DEP_ALREADY_USED_THIS_TURN"

    resp = await alice.post(move_url, json={"uci": "e2e4"})
    assert resp.status_code == 200
    resp = await bob.post(move_url, json={"uci": "e7e5"})
    assert resp.status_code == 200

    rng.values = [0.0]
    resp = await alice.post(dep_url, json={"square": "b2", "target": "N"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True
    assert {"square": "b2", "piece": "N", "color": "white"} in resp.json()["state"]["board"]

    resp = await alice.post(move_url, json={"uci": "b2d3"})
    assert resp.status_code == 200, resp.text

    # Ход чёрных: депить нельзя.
    resp = await alice.post(dep_url, json={"square": "d3", "target": "Q"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NOT_YOUR_TURN"

    resp = await bob.post(move_url, json={"uci": "d7d6"})
    assert resp.status_code == 200

    async with SessionLocal() as db:
        gid = uuid.UUID(game_id)
        fen = (await db.get(Game, gid)).fen
    await set_fen(game_id, fen, white_deps=10)
    resp = await alice.post(dep_url, json={"square": "d3", "target": "Q"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DEP_LIMIT_REACHED"

    await set_fen(game_id, fen, white_deps=1)


async def test_dep_engine_errors(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    await set_fen(game_id, "4k3/8/4P3/8/8/8/8/4K3 w - - 0 1")
    dep_url = f"/api/v1/games/{game_id}/dep"

    resp = await alice.post(dep_url, json={"square": "e6", "target": "Q"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "WOULD_CHECK_OPPONENT"

    resp = await alice.post(dep_url, json={"square": "e1", "target": "Q"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DEP_INVALID_PIECE"

    async with SessionLocal() as check_db:
        count = await check_db.scalar(select(func.count()).select_from(Roll))
    assert count == 0


async def test_dep_selfmate_finishes_game(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    await set_fen(game_id, "k7/8/8/8/8/8/6PP/r2N3K w - - 0 1", ply=20)
    rng.values = [0.99]
    resp = await alice.post(f"/api/v1/games/{game_id}/dep", json={"square": "d1", "target": "R"})
    assert resp.status_code == 200, resp.text
    state = resp.json()["state"]
    assert state["status"] == "finished"
    assert state["result"] == "black"
    assert state["end_reason"] == "checkmate"

    async with SessionLocal() as db:
        gid = uuid.UUID(game_id)
        game = await db.get(Game, gid)
        win_rows = (await db.scalars(select(Ledger).where(Ledger.reason == "game_win"))).all()
        white = await db.get(User, game.white_id)
        black = await db.get(User, game.black_id)
    assert game.white_elo_after == 1184
    assert game.black_elo_after == 1216
    assert game.white_reward == 0
    assert game.black_reward == 100
    assert len(win_rows) == 1
    assert win_rows[0].user_id == game.black_id
    assert win_rows[0].delta == 100
    assert white.elo == 1184
    assert black.elo == 1216


async def test_dep_options_endpoint(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    url = f"/api/v1/games/{game_id}/dep-options"

    resp = await alice.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["unavailable_reason"] is None
    assert data["deps_left"] == 10
    assert len(data["pieces"]) == 14

    resp = await bob.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["unavailable_reason"] == "NOT_YOUR_TURN"
    assert len(data["pieces"]) == 14

    rng.values = [0.0]
    resp = await alice.post(f"/api/v1/games/{game_id}/dep", json={"square": "b1", "target": "Q"})
    assert resp.status_code == 200, resp.text

    resp = await alice.get(url)
    data = resp.json()
    assert data["available"] is False
    assert data["unavailable_reason"] == "DEP_ALREADY_USED_THIS_TURN"
    assert data["deps_left"] == 9
    # После конверсии коня b1 в ферзя депо-способных белых фигур осталось 13.
    assert len(data["pieces"]) == 13


async def test_dep_resets_repetition(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    rng.values = [0.0]
    resp = await alice.post(f"/api/v1/games/{game_id}/dep", json={"square": "b1", "target": "Q"})
    assert resp.status_code == 200, resp.text

    async with SessionLocal() as db:
        game = await db.get(Game, uuid.UUID(game_id))
        repetition = game.repetition
    assert len(repetition) == 1
    assert list(repetition.values()) == [1]


async def test_resign(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    resp = await bob.post(f"/api/v1/games/{game_id}/resign")
    assert resp.status_code == 200, resp.text
    state = resp.json()
    assert state["status"] == "finished"
    assert state["result"] == "white"
    assert state["end_reason"] == "resign"


async def test_draw_flow(alice, bob, rng, db) -> None:
    game_id = await start_game(alice, bob, rng)
    gid = uuid.UUID(game_id)
    offer_url = f"/api/v1/games/{game_id}/draw/offer"
    accept_url = f"/api/v1/games/{game_id}/draw/accept"
    decline_url = f"/api/v1/games/{game_id}/draw/decline"
    move_url = f"/api/v1/games/{game_id}/move"

    async def draw_offer_by() -> str | None:
        await db.rollback()
        return (await db.get(Game, gid)).draw_offer_by

    resp = await alice.post(offer_url)
    assert resp.status_code == 200, resp.text
    assert await draw_offer_by() == "white"

    resp = await alice.post(offer_url)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DRAW_OFFER_NOT_ALLOWED"

    resp = await bob.post(decline_url)
    assert resp.status_code == 200, resp.text
    assert await draw_offer_by() is None

    # Сразу после отклонения повторный оффер блокируется cooldown'ом.
    resp = await alice.post(offer_url)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DRAW_OFFER_NOT_ALLOWED"

    resp = await alice.post(move_url, json={"uci": "e2e4"})
    assert resp.status_code == 200
    resp = await bob.post(move_url, json={"uci": "e7e5"})
    assert resp.status_code == 200

    resp = await alice.post(offer_url)
    assert resp.status_code == 200, resp.text
    assert await draw_offer_by() == "white"

    resp = await bob.post(accept_url)
    assert resp.status_code == 200, resp.text
    state = resp.json()
    assert state["status"] == "finished"
    assert state["result"] == "draw"
    assert state["end_reason"] == "agreement"


async def test_draw_offer_cleared_by_opponent_move(alice, bob, rng, db) -> None:
    game_id = await start_game(alice, bob, rng)
    gid = uuid.UUID(game_id)
    move_url = f"/api/v1/games/{game_id}/move"

    async def draw_offer_by() -> str | None:
        await db.rollback()
        return (await db.get(Game, gid)).draw_offer_by

    resp = await alice.post(move_url, json={"uci": "e2e4"})
    assert resp.status_code == 200
    resp = await alice.post(f"/api/v1/games/{game_id}/draw/offer")
    assert resp.status_code == 200, resp.text
    assert await draw_offer_by() == "white"

    resp = await bob.post(move_url, json={"uci": "e7e5"})
    assert resp.status_code == 200
    assert await draw_offer_by() is None

    resp = await bob.post(f"/api/v1/games/{game_id}/draw/accept")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NO_DRAW_OFFER"


async def test_abort(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    resp = await bob.post(f"/api/v1/games/{game_id}/abort")
    assert resp.status_code == 200, resp.text
    state = resp.json()
    assert state["status"] == "aborted"
    assert state["end_reason"] == "abort"
    assert state["result"] is None

    async with SessionLocal() as db:
        game = await db.get(Game, uuid.UUID(game_id))
        white = await db.get(User, game.white_id)
        black = await db.get(User, game.black_id)
    assert game.white_elo_after is None
    assert game.black_elo_after is None
    assert white.elo == 1200
    assert black.elo == 1200
    assert game.white_reward is None
    assert game.black_reward is None

    game_id2 = await start_game(alice, bob, rng)
    resp = await alice.post(f"/api/v1/games/{game_id2}/move", json={"uci": "e2e4"})
    assert resp.status_code == 200
    resp = await bob.post(f"/api/v1/games/{game_id2}/move", json={"uci": "e7e5"})
    assert resp.status_code == 200
    resp = await alice.post(f"/api/v1/games/{game_id2}/abort")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ABORT_NOT_ALLOWED"


async def _set_setting(key: str, value) -> None:
    async with SessionLocal() as db:
        async with db.begin():
            await db.execute(update(Setting).where(Setting.key == key).values(value=value))
    settings_service.clear_cache()


async def test_rewards_daily_cap(alice, bob, rng) -> None:
    await _set_setting("reward_games_per_day", 1)

    game_id = await start_game(alice, bob, rng)
    await set_fen(game_id, "4k3/8/8/8/8/8/8/4K3 w - - 0 1", ply=20)
    resp = await bob.post(f"/api/v1/games/{game_id}/resign")
    assert resp.status_code == 200, resp.text

    async with SessionLocal() as db:
        game1 = await db.get(Game, uuid.UUID(game_id))
    assert game1.white_reward == 100
    assert game1.black_reward == 0

    game_id2 = await start_game(alice, bob, rng)
    await set_fen(game_id2, "4k3/8/8/8/8/8/8/4K3 w - - 0 1", ply=20)
    resp = await bob.post(f"/api/v1/games/{game_id2}/resign")
    assert resp.status_code == 200, resp.text

    async with SessionLocal() as db:
        game2 = await db.get(Game, uuid.UUID(game_id2))
        win_rows = (await db.scalars(select(Ledger).where(Ledger.reason == "game_win"))).all()
    assert game2.white_reward == 0
    assert game2.black_reward == 0
    assert len(win_rows) == 1


async def test_me_games_history(alice, bob, rng, frozen) -> None:
    game_id = await start_game(alice, bob, rng)
    await set_fen(game_id, "4k3/8/8/8/8/8/8/4K3 w - - 0 1", ply=20)
    resp = await bob.post(f"/api/v1/games/{game_id}/resign")
    assert resp.status_code == 200, resp.text
    frozen.advance(60)

    game_id2 = await start_game(alice, bob, rng)
    await set_fen(game_id2, "4k3/8/8/8/8/8/8/4K3 w - - 0 1", ply=20)
    resp = await bob.post(f"/api/v1/games/{game_id2}/resign")
    assert resp.status_code == 200, resp.text

    resp = await alice.get("/api/v1/me/games")
    assert resp.status_code == 200
    page = resp.json()
    assert len(page["items"]) == 2
    assert page["next_before"] is None
    newest, oldest = page["items"]
    assert newest["id"] == game_id2
    assert oldest["id"] == game_id
    for item in page["items"]:
        assert item["color"] == "white"
        assert item["opponent_login"] == "bob"
        assert item["result"] == "white"
        assert item["end_reason"] == "resign"
        assert item["time_control"] == "3+2"
        assert item["finished_at"] is not None
    # После первой победы alice 1200 -> 1216 (дельта +16), после второй
    # 1216 -> 1231 (дельта +15).
    assert oldest["elo_delta"] == 16
    assert newest["elo_delta"] == 15

    resp = await alice.get("/api/v1/me/games?limit=1")
    page = resp.json()
    assert [item["id"] for item in page["items"]] == [game_id2]
    next_before = page["next_before"]
    assert next_before is not None

    resp = await alice.get("/api/v1/me/games", params={"limit": 10, "before": next_before})
    page2 = resp.json()
    assert [item["id"] for item in page2["items"]] == [game_id]

    alice_me = (await alice.get("/api/v1/me")).json()
    bob_me = (await bob.get("/api/v1/me")).json()
    assert alice_me["elo"] == 1231
    assert bob_me["elo"] == 1169


async def _next_message(pubsub, attempts: int = 30) -> dict:
    for _ in range(attempts):
        raw = await asyncio.wait_for(pubsub.get_message(timeout=0.1), timeout=2.0)
        if raw is not None and raw.get("type") == "message":
            return json.loads(raw["data"])
    raise AssertionError("no pubsub message")


async def test_publish_after_commit(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(game_channel(uuid.UUID(game_id)))

    resp = await alice.post(f"/api/v1/games/{game_id}/move", json={"uci": "e2e4"})
    assert resp.status_code == 200, resp.text
    message = await _next_message(pubsub)
    state = (await alice.get(f"/api/v1/games/{game_id}")).json()
    assert message["version"] == state["version"]

    move_url = f"/api/v1/games/{game_id}/move"
    for client, uci in ((bob, "e7e5"), (alice, "g1f3")):
        resp = await client.post(move_url, json={"uci": uci})
        assert resp.status_code == 200, resp.text
        message = await _next_message(pubsub)
    assert message["game_over"] is None

    resp = await bob.post(f"/api/v1/games/{game_id}/resign")
    assert resp.status_code == 200, resp.text
    message = await _next_message(pubsub)
    assert message["game_over"] is not None
    assert message["game_over"]["result"] == "white"
    assert message["game_over"]["end_reason"] == "resign"
    await pubsub.unsubscribe(game_channel(uuid.UUID(game_id)))
    await pubsub.aclose()
