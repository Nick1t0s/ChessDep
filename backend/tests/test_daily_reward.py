import asyncio
import uuid
from datetime import datetime, timedelta

import chess
from sqlalchemy import func, select

import app.core.clock as clock
from app.chess_engine import position_key
from app.db import SessionLocal
from app.models import Game, InventoryItem, Roll, User


async def _add_games(
    player_login: str,
    n: int,
    *,
    ply: int = 20,
    finished_at: datetime | None = None,
    as_black: bool = False,
    result: str | None = None,
) -> None:
    """Вставить n завершённых партий напрямую в БД (отдельная сессия).

    За игрока играют «зарегистрированным» логином, соперником всегда выступает
    другой зарегистрированный пользователь. По умолчанию партия —

    победа игрока (result = цвет игрока); result можно задать явно
    ("black"/"white"/"draw") для поражений и ничьих.
    """
    rival_login = "alice" if player_login == "bob" else "bob"
    async with SessionLocal() as db:
        async with db.begin():
            users = {
                u.login: u
                for u in (
                    await db.scalars(
                        select(User).where(User.login.in_([player_login, rival_login]))
                    )
                ).all()
            }
            player = users[player_login]
            rival = users[rival_login]
            now = finished_at if finished_at is not None else clock.now()
            board = chess.Board()
            fen = board.fen()
            repetition = {position_key(board): 1}
            base_ms, inc_ms = 180_000, 2_000  # контроль «3+2»
            outcome = result if result is not None else ("black" if as_black else "white")
            for _ in range(n):
                white_id = rival.id if as_black else player.id
                black_id = player.id if as_black else rival.id
                db.add(
                    Game(
                        id=uuid.uuid4(),
                        status="finished",
                        time_control="3+2",
                        base_ms=base_ms,
                        inc_ms=inc_ms,
                        white_id=white_id,
                        black_id=black_id,
                        fen=fen,
                        ply=ply,
                        repetition=repetition,
                        white_ms=base_ms,
                        black_ms=base_ms,
                        turn_started_at=now,
                        clock_running=False,
                        white_elo_before=player.elo if white_id == player.id else rival.elo,
                        black_elo_before=player.elo if black_id == player.id else rival.elo,
                        result=outcome,
                        end_reason="agreement" if outcome == "draw" else "resign",
                        finished_at=now,
                    )
                )


async def add_wins(user_login: str, n: int, *, ply: int = 20, finished_at: datetime | None = None, as_black: bool = False) -> None:
    """Вставить n побед игрока (result = цвет игрока)."""
    await _add_games(
        user_login,
        n,
        ply=ply,
        finished_at=finished_at,
        as_black=as_black,
    )


async def add_loss(user_login: str, *, ply: int = 20, finished_at: datetime | None = None, as_black: bool = False) -> None:
    result = "white" if as_black else "black"
    await _add_games(user_login, 1, ply=ply, finished_at=finished_at, as_black=as_black, result=result)


async def add_draw(user_login: str, *, ply: int = 20, finished_at: datetime | None = None) -> None:
    await _add_games(user_login, 1, ply=ply, finished_at=finished_at, result="draw")


async def test_status_initial(alice) -> None:
    resp = await alice.get("/api/v1/me/daily-reward")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "wins_today": 0,
        "wins_required": 3,
        "claimed_today": False,
        "available": False,
    }


async def test_not_ready(alice, bob) -> None:
    await add_wins("alice", 2)
    resp = await alice.post("/api/v1/me/daily-reward")
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"]["code"] == "DAILY_REWARD_NOT_READY"
    assert "3" in body["error"]["message"]


async def test_counting_rules(alice, bob) -> None:
    await add_wins("alice", 2)
    await add_wins("alice", 1, as_black=True)
    status = (await alice.get("/api/v1/me/daily-reward")).json()
    assert status["wins_today"] == 3
    assert status["available"] is True

    # Победа с коротким ply не считается.
    await add_wins("alice", 1, ply=5)
    # Победа вчера не считается.
    await add_wins("alice", 1, finished_at=clock.now() - timedelta(days=1))
    # Поражение не считается.
    await add_loss("alice")
    # Ничья не считается.
    await add_draw("alice")

    status = (await alice.get("/api/v1/me/daily-reward")).json()
    assert status == {
        "wins_today": 3,
        "wins_required": 3,
        "claimed_today": False,
        "available": True,
    }


async def test_claim(alice, bob, rng) -> None:
    await add_wins("alice", 3)
    rng.values = [0.0]
    resp = await alice.post("/api/v1/me/daily-reward")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["case"]["id"] == 1
    assert body["item"]["kind"] == "case"
    assert body["item"]["source"] == "daily_reward"
    item_id = body["item"]["id"]

    async with SessionLocal() as check:
        rolls = (await check.scalars(select(Roll).where(Roll.kind == "daily_reward"))).all()
        assert len(rolls) == 1
        assert rolls[0].outcome == {"case_id": 1, "item_id": item_id}

    status = (await alice.get("/api/v1/me/daily-reward")).json()
    assert status == {
        "wins_today": 3,
        "wins_required": 3,
        "claimed_today": True,
        "available": False,
    }

    second = await alice.post("/api/v1/me/daily-reward")
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "DAILY_REWARD_CLAIMED"

    inv = (await alice.get("/api/v1/inventory?kind=case")).json()
    assert [i["id"] for i in inv] == [item_id]
    assert inv[0]["case"]["id"] == 1


async def test_weighted_pool(alice, bob, admin, rng) -> None:
    resp = await admin.post(
        "/api/v1/admin/cases",
        json={"code": "custom", "name": "Custom", "price": 50, "kind": "custom"},
    )
    assert resp.status_code == 201, resp.text
    new_case_id = resp.json()["id"]

    resp = await admin.put(
        f"/api/v1/admin/cases/{new_case_id}/drops",
        json=[{"item_def_id": 14, "weight": 1}],  # genesis-wp
    )
    assert resp.status_code == 200, resp.text
    resp = await admin.post(f"/api/v1/admin/cases/{new_case_id}/publish")
    assert resp.status_code == 200, resp.text

    resp = await admin.put(
        "/api/v1/admin/daily-reward-pool",
        json=[{"case_id": 1, "weight": 1}, {"case_id": new_case_id, "weight": 3}],
    )
    assert resp.status_code == 200, resp.text
    pool = resp.json()
    assert [(p["case"]["id"], p["weight"]) for p in pool] == [(1, 1), (new_case_id, 3)]

    await add_wins("alice", 3)
    rng.values = [0.3]
    resp = await alice.post("/api/v1/me/daily-reward")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["case"]["id"] == new_case_id
    assert body["item"]["source"] == "daily_reward"


async def test_empty_pool(alice, bob, admin) -> None:
    resp = await admin.put("/api/v1/admin/daily-reward-pool", json=[])
    assert resp.status_code == 200, resp.text
    assert resp.json() == []

    await add_wins("alice", 3)
    resp = await alice.post("/api/v1/me/daily-reward")
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "DAILY_REWARD_EMPTY"


async def test_next_day(alice, bob, frozen) -> None:
    await add_wins("alice", 3)
    resp = await alice.post("/api/v1/me/daily-reward")
    assert resp.status_code == 200, resp.text

    frozen.advance(86400)
    status = (await alice.get("/api/v1/me/daily-reward")).json()
    assert status == {
        "wins_today": 0,
        "wins_required": 3,
        "claimed_today": False,
        "available": False,
    }


async def test_claim_concurrent(alice, bob, rng) -> None:
    await add_wins("alice", 3)
    rng.values = [0.0]
    responses = await asyncio.gather(
        *[alice.post("/api/v1/me/daily-reward") for _ in range(5)]
    )
    ok = [r for r in responses if r.status_code == 200]
    assert len(ok) == 1
    for r in responses:
        if r.status_code != 200:
            assert r.status_code in (400, 429), r.text

    async with SessionLocal() as check:
        roll_count = await check.scalar(
            select(func.count()).select_from(Roll).where(Roll.kind == "daily_reward")
        )
        items = (
            await check.scalars(
                select(InventoryItem).where(InventoryItem.source == "daily_reward")
            )
        ).all()
    assert roll_count == 1
    assert len(items) == 1
    assert items[0].case_id == 1


async def test_me_has_no_bonus_field(alice) -> None:
    resp = await alice.get("/api/v1/me")
    assert resp.status_code == 200, resp.text
    assert "daily_bonus_available_at" not in resp.json()

    resp = await alice.post("/api/v1/me/daily-bonus")
    assert resp.status_code in (404, 405), resp.text
