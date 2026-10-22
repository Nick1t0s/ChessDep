import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.db import SessionLocal
from app.models import (
    AdminAudit,
    Game,
    InventoryItem,
    Ledger,
    MarketListing,
    User,
)
from app.redis import redis_client
from app.services.settings import DEFAULTS
from tests.conftest import anonymous, give_items, start_game


async def _user_id(login: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(User.id).where(User.login == login))


async def test_admin_endpoints_require_admin(alice, admin, rng) -> None:
    alice_id = await _user_id("alice")
    game_id = await start_game(alice, admin, rng)
    paths = [
        "/api/v1/admin/users",
        f"/api/v1/admin/users/{alice_id}",
        "/api/v1/admin/settings",
        "/api/v1/admin/rolls",
        f"/api/v1/admin/games/{game_id}/events",
        "/api/v1/admin/market",
        "/api/v1/admin/audit",
    ]
    for path in paths:
        resp = await alice.get(path)
        assert resp.status_code == 403, (path, resp.text)
        assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_users_search(alice, bob, admin) -> None:
    resp = await admin.get("/api/v1/admin/users?q=ali")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["login"] == "alice"

    resp = await admin.get("/api/v1/admin/users?q=@example")
    body = resp.json()
    assert body["total"] == 3
    assert {i["login"] for i in body["items"]} == {"alice", "bob", "admin"}

    # Пагинация: limit=2 → 2 из 3.
    resp = await admin.get("/api/v1/admin/users?q=@example&limit=2")
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2

    alice_id = await _user_id("alice")
    resp = await admin.get(f"/api/v1/admin/users/{alice_id}")
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert "ledger" in detail
    assert detail["items_owned"] == 0
    assert detail["active_listings"] == 0


async def test_ban_flow(alice, bob, admin, rng) -> None:
    alice_id = await _user_id("alice")
    bob_id = await _user_id("bob")
    admin_id = await _user_id("admin")

    ids = await give_items("bob", ["genesis-pawn-chalk"])
    resp = await bob.post(
        "/api/v1/market/listings", json={"item_id": ids[0], "price": 10}
    )
    assert resp.status_code == 201, resp.text
    listing_id = resp.json()["id"]

    game_id = await start_game(alice, bob, rng)

    # «Зависший» в очереди bob имитируется напрямую в Redis.
    await redis_client.set(f"mm:user:{bob_id}", "3+2")
    await redis_client.rpush("mm:queue:3+2", str(bob_id))

    resp = await admin.post(
        f"/api/v1/admin/users/{bob_id}/ban", json={"reason": "тест"}
    )
    assert resp.status_code == 200, resp.text

    # Партия finished, побеждает alice, resign.
    async with SessionLocal() as db:
        game = await db.get(Game, uuid.UUID(game_id))
        assert game is not None
        alice_color = "white" if game.white_id == alice_id else "black"
        assert game.status == "finished"
        assert game.result == alice_color
        assert game.end_reason == "resign"

        listing = await db.get(MarketListing, listing_id)
        assert listing is not None
        assert listing.status == "cancelled"
        item = await db.get(InventoryItem, ids[0])
        assert item is not None
        assert item.user_id == bob_id
        assert item.status == "owned"

        audit_rows = (
            await db.scalars(
                select(AdminAudit).where(
                    AdminAudit.action == "user.ban", AdminAudit.target == f"user:{bob_id}"
                )
            )
        ).all()
        assert len(audit_rows) == 1
        assert audit_rows[0].admin_id == admin_id
        assert audit_rows[0].payload == {"reason": "тест"}

    # Очередь матчмейкинга очищена.
    assert await redis_client.get(f"mm:user:{bob_id}") is None
    assert await redis_client.llen("mm:queue:3+2") == 0

    # Старая cookie bob отозвана, логин заблокирован.
    resp = await bob.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"

    async with anonymous() as fresh:
        resp = await fresh.post(
            "/api/v1/auth/login", json={"login": "bob", "password": "password123"}
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["error"]["code"] == "USER_BANNED"

    # Разбан: логин успешен.
    resp = await admin.post(f"/api/v1/admin/users/{bob_id}/unban")
    assert resp.status_code == 200, resp.text
    async with anonymous() as fresh:
        resp = await fresh.post(
            "/api/v1/auth/login", json={"login": "bob", "password": "password123"}
        )
        assert resp.status_code == 200, resp.text


async def test_ban_restrictions(alice, admin) -> None:
    admin_id = await _user_id("admin")

    resp = await admin.post(
        f"/api/v1/admin/users/{admin_id}/ban", json={"reason": "себя"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CANNOT_BAN_SELF"

    async with SessionLocal() as db:
        async with db.begin():
            boss = User(
                login="boss",
                email="boss@example.com",
                password_hash=hash_password("password123"),
                role="admin",
            )
            db.add(boss)
            await db.flush()
            boss_id = boss.id

    resp = await admin.post(
        f"/api/v1/admin/users/{boss_id}/ban", json={"reason": "админ"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CANNOT_BAN_ADMIN"

    resp = await admin.post(
        "/api/v1/admin/users/999999/ban", json={"reason": "нет такого"}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "USER_NOT_FOUND"


async def test_admin_balance(alice, admin) -> None:
    alice_id = await _user_id("alice")
    admin_id = await _user_id("admin")

    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/balance",
        json={"delta": 500, "comment": "выдача за тесты"},
    )
    assert resp.status_code == 200, resp.text
    assert (await alice.get("/api/v1/me")).json()["balance"] == 1500

    async with SessionLocal() as db:
        row = (
            await db.scalars(
                select(Ledger).where(
                    Ledger.user_id == alice_id, Ledger.reason == "admin_adjust"
                )
            )
        ).one()
        assert row.delta == 500
        assert row.actor_id == admin_id
        assert row.ref == "выдача за тесты"

    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/balance",
        json={"delta": -1_000_000, "comment": "штраф"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INSUFFICIENT_FUNDS"

    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/balance",
        json={"delta": 0, "comment": "ноль"},
    )
    assert resp.status_code == 422


async def test_admin_settings(alice, bob, admin, rng) -> None:
    resp = await admin.get("/api/v1/admin/settings")
    assert resp.status_code == 200, resp.text
    body = {row["key"]: row for row in resp.json()}
    assert set(body) == set(DEFAULTS)
    for key, entry in body.items():
        assert entry["default"] == DEFAULTS[key]
        assert entry["value"] == DEFAULTS[key]

    game_id = await start_game(alice, bob, rng)

    resp = await admin.put(
        "/api/v1/admin/settings/dep_multiplier", json={"value": 0.5}
    )
    assert resp.status_code == 200, resp.text

    # Шанс N→Q у ходящего = 3/9 * 0.5 = 1/6.
    resp = await alice.get(f"/api/v1/games/{game_id}/dep-options")
    assert resp.status_code == 200, resp.text
    options = resp.json()
    n_options = [p for p in options["pieces"] if p["piece"] == "N"]
    assert n_options
    q_target = next(t for t in n_options[0]["targets"] if t["piece"] == "Q")
    assert abs(q_target["chance"] - 1 / 6) < 1e-9

    resp = await admin.put(
        "/api/v1/admin/settings/dep_multiplier", json={"value": "abc"}
    )
    assert resp.status_code == 422
    resp = await admin.put("/api/v1/admin/settings/dep_multiplier", json={"value": 0})
    assert resp.status_code == 422

    resp = await admin.put(
        "/api/v1/admin/settings/unknown_key", json={"value": 1}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SETTING_NOT_FOUND"

    resp = await admin.put(
        "/api/v1/admin/settings/upgrade_min_chance", json={"value": 0.9}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SETTINGS_INCONSISTENT"

    resp = await admin.put(
        "/api/v1/admin/settings/time_controls", json={"value": ["3+2", "bad"]}
    )
    assert resp.status_code == 422

    bad_weights = {k: 1 for k in ("common", "uncommon", "rare", "epic", "legendary")}
    resp = await admin.put(
        "/api/v1/admin/settings/rarity_weights", json={"value": bad_weights}
    )
    assert resp.status_code == 422

    async with SessionLocal() as db:
        rows = (
            await db.scalars(
                select(AdminAudit).where(AdminAudit.action == "settings.update")
            )
        ).all()
    assert len(rows) == 1


async def test_admin_rolls_events_market_audit(alice, bob, admin, rng) -> None:
    alice_id = await _user_id("alice")
    bob_id = await _user_id("bob")
    game_id = await start_game(alice, bob, rng)

    # Деп (успех при roll_value 0 меньше шанса).
    resp = await alice.post(
        f"/api/v1/games/{game_id}/dep", json={"square": "e2", "target": "N"}
    )
    assert resp.status_code == 200, resp.text

    resp = await admin.get(f"/api/v1/admin/rolls?user_id={alice_id}")
    assert resp.status_code == 200, resp.text
    rolls = resp.json()["items"]
    assert len(rolls) == 1
    assert rolls[0]["kind"] == "dep"
    assert rolls[0]["ref"] == game_id

    resp = await admin.get(f"/api/v1/admin/rolls?user_id={alice_id}&kind=case_open")
    assert resp.json()["items"] == []
    resp = await admin.get(f"/api/v1/admin/rolls?user_id={bob_id}&kind=dep")
    assert resp.json()["items"] == []

    # Ход конём, чтобы events содержали два события по порядку seq.
    resp = await alice.post(f"/api/v1/games/{game_id}/move", json={"uci": "e2d4"})
    assert resp.status_code == 200, resp.text

    resp = await admin.get(f"/api/v1/admin/games/{game_id}/events")
    assert resp.status_code == 200, resp.text
    events = resp.json()
    assert [e["seq"] for e in events] == sorted(e["seq"] for e in events)
    assert [e["kind"] for e in events] == ["dep", "move"]

    # Админ снимает чужой лот.
    ids = await give_items("bob", ["genesis-pawn-chalk"])
    resp = await bob.post(
        "/api/v1/market/listings", json={"item_id": ids[0], "price": 50}
    )
    assert resp.status_code == 201, resp.text
    listing_id = resp.json()["id"]

    resp = await admin.post(
        f"/api/v1/admin/market/listings/{listing_id}/cancel",
        json={"reason": "модерация"},
    )
    assert resp.status_code == 200, resp.text

    resp = await admin.get("/api/v1/admin/market?status=cancelled")
    body = resp.json()
    assert body["items"][0]["id"] == listing_id

    async with SessionLocal() as db:
        item = await db.get(InventoryItem, ids[0])
        assert item is not None
        assert item.user_id == bob_id
        assert item.status == "owned"

    # Журнал админа: последние сверху.
    resp = await admin.get("/api/v1/admin/audit")
    body = resp.json()
    assert body["items"][0]["action"] == "market.cancel"
    assert body["items"][0]["admin_login"] == "admin"
    ids_in_order = [row["id"] for row in body["items"]]
    assert ids_in_order == sorted(ids_in_order, reverse=True)
