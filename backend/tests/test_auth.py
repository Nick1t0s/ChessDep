from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models import Ledger, Session as SessionModel, User
from app.core.security import hash_token
from app.services.settings import DEFAULTS
from tests.conftest import register


async def test_register_sets_httponly_cookie_and_signup_bonus(client, db) -> None:
    resp = await register(client)
    assert resp.status_code == 201
    set_cookie = resp.headers["set-cookie"].lower()
    assert "sid=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "path=/" in set_cookie
    token = resp.cookies.get("sid")
    assert token is not None
    assert "." not in token

    me = (await client.get("/api/v1/me")).json()
    assert me["balance"] == DEFAULTS["starting_balance"]

    async with db.begin():
        total = await db.scalar(select(func.count()).select_from(Ledger))
        signup = await db.scalar(
            select(func.count()).select_from(Ledger).where(Ledger.reason == "signup_bonus")
        )
    assert total == 1
    assert signup == 1


async def test_session_token_stored_hashed(client, db) -> None:
    resp = await register(client)
    token = resp.cookies.get("sid")

    async with db.begin():
        rows = (await db.scalars(select(SessionModel))).all()

    assert len(rows) == 1
    saved = rows[0].token_hash
    assert saved == hash_token(token)
    assert saved != token.encode()
    assert token.encode() not in saved


async def test_register_duplicate_login_and_email(client) -> None:
    resp = await register(client, login="alice")
    assert resp.status_code == 201

    resp = await register(client, login="alice", email="other@example.com")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "LOGIN_TAKEN"

    resp = await register(client, login="Alice", email="second@example.com")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "LOGIN_TAKEN"

    resp = await register(client, login="bob", email="alice@example.com")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "EMAIL_TAKEN"

    resp = await register(client, login="bob", email="ALICE@example.com")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_register_validation(client, db) -> None:
    payloads: list[dict[str, str]] = [
        {"login": "ab", "email": "a@example.com", "password": "password123"},
        {"login": "a b", "email": "a@example.com", "password": "password123"},
        {"login": "bad!login", "email": "a@example.com", "password": "password123"},
        {"login": "okuser", "email": "a@example.com", "password": "short"},
        {"login": "okuser", "email": "not-an-email", "password": "password123"},
        {"login": "okuser", "email": "a@example.com", "password": "password123", "role": "admin"},
    ]
    for payload in payloads:
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 422, payload
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(User)) == 0


async def test_login_ok_and_wrong_password(client) -> None:
    resp = await register(client, login="alice")
    assert resp.status_code == 201

    unknown = await client.post(
        "/api/v1/auth/login", json={"login": "ghost", "password": "password123"}
    )
    wrong = await client.post(
        "/api/v1/auth/login", json={"login": "alice", "password": "wrong-password"}
    )
    assert unknown.status_code == 401
    assert wrong.status_code == 401
    assert unknown.json() == wrong.json()

    ok = await client.post(
        "/api/v1/auth/login", json={"login": "alice", "password": "password123"}
    )
    assert ok.status_code == 200
    assert ok.json()["login"] == "alice"


async def test_login_fail_lockout(client) -> None:
    resp = await register(client, login="alice")
    assert resp.status_code == 201
    for _ in range(5):
        resp = await client.post(
            "/api/v1/auth/login", json={"login": "alice", "password": "wrong-password"}
        )
        assert resp.status_code == 401
    resp = await client.post(
        "/api/v1/auth/login", json={"login": "alice", "password": "password123"}
    )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"


async def test_logout_revokes_session(client) -> None:
    resp = await register(client)
    token = resp.cookies.get("sid")

    logout = await client.post("/api/v1/auth/logout")
    assert logout.status_code == 204

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as fresh:
        me = await fresh.get("/api/v1/me", headers={"Cookie": f"sid={token}"})
    assert me.status_code == 401
    assert me.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_password_change_revokes_other_sessions(client) -> None:
    resp = await register(client)
    old_token = resp.cookies.get("sid")

    login = await client.post(
        "/api/v1/auth/login", json={"login": "alice", "password": "password123"}
    )
    assert login.status_code == 200

    changed = await client.post(
        "/api/v1/me/password",
        json={"old_password": "password123", "new_password": "new-password-8"},
    )
    assert changed.status_code == 204

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as fresh:
        me_old = await fresh.get("/api/v1/me", headers={"Cookie": f"sid={old_token}"})
    assert me_old.status_code == 401

    me_new = await client.get("/api/v1/me")
    assert me_new.status_code == 200


async def test_banned_user_rejected(client, db) -> None:
    resp = await register(client)
    assert resp.status_code == 201
    async with db.begin():
        user = (await db.scalars(select(User))).one()
        user.is_banned = True

    me = await client.get("/api/v1/me")
    assert me.status_code == 403
    assert me.json()["error"]["code"] == "USER_BANNED"

    login = await client.post(
        "/api/v1/auth/login", json={"login": "alice", "password": "password123"}
    )
    assert login.status_code == 403
    assert login.json()["error"]["code"] == "USER_BANNED"


async def test_expired_session_rejected(client, db) -> None:
    resp = await register(client)
    assert resp.status_code == 201
    async with db.begin():
        row = (await db.scalars(select(SessionModel))).one()
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    me = await client.get("/api/v1/me")
    assert me.status_code == 401
