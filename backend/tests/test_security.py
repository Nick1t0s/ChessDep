from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.health import redis_client
from app.config import settings
from app.main import app
from app.models import User
from app.services.settings import DEFAULTS
from tests.conftest import register


async def _fresh_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_post_without_origin_forbidden() -> None:
    async with await _fresh_client() as client:
        resp = await client.post(
            "/api/v1/auth/register",
            json={"login": "alice", "email": "alice@example.com", "password": "password123"},
        )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "BAD_ORIGIN"


async def test_post_with_foreign_origin_forbidden(client) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"login": "alice", "email": "alice@example.com", "password": "password123"},
        headers={"Origin": "http://evil.example"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "BAD_ORIGIN"


async def test_get_without_origin_allowed() -> None:
    async with await _fresh_client() as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_me_requires_auth() -> None:
    async with await _fresh_client() as client:
        resp = await client.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_require_admin_endpoint(client, db) -> None:
    async with await _fresh_client() as anonymous:
        no_session = await anonymous.get("/api/v1/internal/require-admin")
    assert no_session.status_code == 401

    resp = await register(client)
    assert resp.status_code == 201
    forbidden = await client.get("/api/v1/internal/require-admin")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"

    async with db.begin():
        user = (await db.scalars(select(User))).one()
        user.role = "admin"
    allowed = await client.get("/api/v1/internal/require-admin")
    assert allowed.status_code == 204
    assert await allowed.aread() == b""


async def test_cookie_name_secure_mode(monkeypatch, client) -> None:
    monkeypatch.setattr(settings, "cookie_secure", True)
    resp = await register(client, login="carol", email="carol@example.com")
    assert resp.status_code == 201
    set_cookie = resp.headers["set-cookie"]
    assert "__Host-sid=" in set_cookie
    assert "secure" in set_cookie.lower()


async def test_error_format() -> None:
    async with await _fresh_client() as client:
        resp = await client.get("/api/v1/no-such-route")
    assert resp.status_code == 404
    error = resp.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert "message" in error


async def test_logout_cookie_secure_mode(monkeypatch, client) -> None:
    monkeypatch.setattr(settings, "cookie_secure", True)
    resp = await register(client, login="dave", email="dave@example.com")
    assert resp.status_code == 201
    set_cookie = resp.headers["set-cookie"]
    assert set_cookie.startswith("__Host-sid=")
    token = set_cookie.split(";", 1)[0].split("=", 1)[1]

    async with await _fresh_client() as fresh:
        logout = await fresh.post(
            "/api/v1/auth/logout",
            headers={"Origin": "http://test", "Cookie": f"__Host-sid={token}"},
        )
    assert logout.status_code == 204
    out_cookie = logout.headers["set-cookie"]
    assert "__Host-sid=" in out_cookie
    assert "Max-Age=0" in out_cookie
    assert "Secure" in out_cookie
    assert "HttpOnly" in out_cookie
    assert "SameSite=strict" in out_cookie


async def test_config_public() -> None:
    async with await _fresh_client() as client:
        resp = await client.get("/api/v1/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["time_controls"] == DEFAULTS["time_controls"]
    assert data["dep_limit"] == 10


async def test_health_503_when_redis_down(monkeypatch) -> None:
    async def failing_ping() -> None:
        raise ConnectionError

    monkeypatch.setattr(redis_client, "ping", failing_ping)
    async with await _fresh_client() as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "HTTP_ERROR"
