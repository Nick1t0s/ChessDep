from sqlalchemy import select

from app.core.security import hash_password
from app.db import SessionLocal
from app.models import Ledger, User
from tests.conftest import set_balance


async def _make_user(login: str, elo: int, balance: int) -> int:
    async with SessionLocal() as db:
        async with db.begin():
            user = User(
                login=login,
                email=f"{login}@example.com",
                password_hash=hash_password("password123"),
                elo=elo,
                balance=balance,
            )
            db.add(user)
            await db.flush()
            db.add(
                Ledger(
                    user_id=user.id,
                    delta=balance,
                    balance_after=balance,
                    reason="signup_bonus",
                )
            )
            return user.id


async def _set_elos(elos: dict[str, int]) -> None:
    async with SessionLocal() as db:
        async with db.begin():
            for login, elo in elos.items():
                user = (await db.scalars(select(User).where(User.login == login))).one()
                user.elo = elo


async def _set_banned(login: str, banned: bool) -> None:
    async with SessionLocal() as db:
        async with db.begin():
            user = (await db.scalars(select(User).where(User.login == login))).one()
            user.is_banned = banned


async def test_leaderboard_order(alice, bob, carol) -> None:
    await _make_user("dave", 1300, 0)
    # elo: alice 1300, bob 1250, carol 1250, dave 1100 —
    # при равенстве выше меньший id (bob раньше carol).
    await _set_elos({"alice": 1300, "bob": 1250, "carol": 1250, "dave": 1100})

    resp = await alice.get("/api/v1/leaderboard")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [e["login"] for e in body] == ["alice", "bob", "carol", "dave"]
    assert [e["rank"] for e in body] == [1, 2, 3, 4]
    assert body[0]["elo"] == 1300

    # limit=2 → 2 строки, rank 1 и 2.
    resp = await alice.get("/api/v1/leaderboard?limit=2")
    body = resp.json()
    assert [e["login"] for e in body] == ["alice", "bob"]
    assert [e["rank"] for e in body] == [1, 2]

    # by=balance сортирует по балансу.
    await set_balance("alice", 100)
    await set_balance("bob", 900)
    await set_balance("carol", 500)
    await set_balance("dave", 700)
    resp = await alice.get("/api/v1/leaderboard?by=balance")
    body = resp.json()
    assert [e["login"] for e in body] == ["bob", "dave", "carol", "alice"]

    # Забаненные исключены.
    await _set_banned("carol", True)
    resp = await alice.get("/api/v1/leaderboard")
    body = resp.json()
    assert [e["login"] for e in body] == ["alice", "bob", "dave"]
    resp = await alice.get("/api/v1/leaderboard?by=balance")
    body = resp.json()
    assert [e["login"] for e in body] == ["bob", "dave", "alice"]

    # Без авторизации — публично.
    from tests.conftest import anonymous

    resp = await anonymous().get("/api/v1/leaderboard")
    assert resp.status_code == 200
