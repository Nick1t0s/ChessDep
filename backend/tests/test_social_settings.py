import asyncio
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models.social import Friendship, Notification, UserBlock, UserSocialSettings
from app.models.user import User
from app.services.social_settings import (
    ensure_invitation_allowed,
    ensure_not_blocked,
    get_or_create_social_settings,
    record_presence_heartbeat,
    update_social_settings,
)
from tests.conftest import FixedRng, give_items, start_game


@pytest.mark.asyncio
async def test_social_settings_defaults_and_patch(alice: AsyncClient) -> None:
    # 1. Defaults
    resp = await alice.get("/api/v1/me/social-settings")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["presence_mode"] == "online"
    assert data["match_invites"] == "all"
    assert data["notifications"]["friend_request"] is True
    assert data["notifications"]["friend_accepted"] is True
    assert data["notifications"]["match_invite"] is True
    assert data["notifications"]["market_sale"] is True
    assert data["notifications"]["gift"] is True

    # 2. Patch partial notifications and match_invites
    resp = await alice.patch(
        "/api/v1/me/social-settings",
        json={"match_invites": "friends", "notifications": {"gift": False}},
    )
    assert resp.status_code == 200, resp.text
    patched = resp.json()
    assert patched["match_invites"] == "friends"
    assert patched["presence_mode"] == "online"
    assert patched["notifications"]["gift"] is False
    assert patched["notifications"]["friend_request"] is True

    # Check persistence
    resp = await alice.get("/api/v1/me/social-settings")
    assert resp.status_code == 200
    assert resp.json()["match_invites"] == "friends"
    assert resp.json()["notifications"]["gift"] is False


@pytest.mark.asyncio
async def test_social_settings_validation(alice: AsyncClient) -> None:
    # Reject unknown top-level key
    resp = await alice.patch("/api/v1/me/social-settings", json={"unknown_key": 123})
    assert resp.status_code == 422

    # Reject non-literal boolean (e.g. integer 1)
    resp = await alice.patch(
        "/api/v1/me/social-settings",
        json={"notifications": {"gift": 1}},
    )
    assert resp.status_code == 422

    # Reject non-literal boolean (e.g. string "false")
    resp = await alice.patch(
        "/api/v1/me/social-settings",
        json={"notifications": {"gift": "false"}},
    )
    assert resp.status_code == 422

    # Reject unknown notification kind
    resp = await alice.patch(
        "/api/v1/me/social-settings",
        json={"notifications": {"non_existent_kind": True}},
    )
    assert resp.status_code == 422

    # Reject invalid presence_mode
    resp = await alice.patch(
        "/api/v1/me/social-settings",
        json={"presence_mode": "invisible"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_concurrent_patches_survive() -> None:
    # Проверяем, что два параллельных PATCH с разными ключами не перезаписывают друг друга
    async with SessionLocal() as db_init:
        async with db_init.begin():
            user = (await db_init.scalars(select(User).where(User.login == "alice"))).first()
            if not user:
                user = User(login="alice_concur", email="ac@test.com", password_hash="dummy")
                db_init.add(user)
                await db_init.flush()
            user_id = user.id

    async def patch_task(notif_key: str):
        async with SessionLocal() as session:
            async with session.begin():
                return await update_social_settings(
                    session, user_id, notifications={notif_key: False}
                )

    await asyncio.gather(patch_task("gift"), patch_task("market_sale"))

    async with SessionLocal() as check_db:
        settings = await get_or_create_social_settings(check_db, user_id)
        assert settings.notification_settings.get("gift") is False
        assert settings.notification_settings.get("market_sale") is False


@pytest.mark.asyncio
async def test_muted_notification_preserves_domain_action(
    alice: AsyncClient, bob: AsyncClient, db: AsyncSession
) -> None:
    # Используем genesis-pawn-chalk вместо несуществующего piece_pawn_wood
    item_ids = await give_items("alice", ["genesis-pawn-chalk"])
    pawn_id = item_ids[0]

    # Bob отключает уведомления о подарках и заявках в друзья
    resp = await bob.patch(
        "/api/v1/me/social-settings",
        json={"notifications": {"gift": False, "friend_request": False}},
    )
    assert resp.status_code == 200

    # Alice отправляет запрос в друзья -> дружба создается, но уведомление не пишется
    req_resp = await alice.post("/api/v1/friends/requests", json={"login": "bob"})
    assert req_resp.status_code == 200
    assert req_resp.json()["status"] == "pending"

    # Alice отправляет подарок Бобу -> статус 201
    resp = await alice.post(
        "/api/v1/gifts",
        json={"item_id": pawn_id, "to_login": "bob", "note": "Gift for you"},
    )
    assert resp.status_code == 201, resp.text

    # Bob не имеет уведомлений ни о запросе, ни о подарке
    bob_resp = await bob.get("/api/v1/notifications")
    assert bob_resp.status_code == 200
    assert len(bob_resp.json()["items"]) == 0

    # Доменное действие подарка выполнено
    gifts_resp = await bob.get("/api/v1/me/gifts?direction=in")
    assert gifts_resp.status_code == 200
    assert len(gifts_resp.json()["items"]) == 1

    # Входящая заявка в друзья существует
    reqs = (await bob.get("/api/v1/friends/requests")).json()
    assert len(reqs["incoming"]) == 1
    assert reqs["incoming"][0]["login"] == "alice"


@pytest.mark.asyncio
async def test_presence_heartbeat_and_modes(
    alice: AsyncClient, bob: AsyncClient, db: AsyncSession, redis_client
) -> None:
    await alice.post("/api/v1/friends/requests", json={"login": "bob"})
    alice_id = await db.scalar(select(User.id).where(User.login == "alice"))
    await bob.post(f"/api/v1/friends/requests/{alice_id}/accept")

    # До heartbeat статус offline
    resp = await bob.get("/api/v1/friends")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["presence"] == "offline"
    assert item["game_id"] is None

    # Heartbeat Alice
    resp = await alice.post("/api/v1/me/presence", json={"presence": "online"})
    assert resp.status_code == 200
    assert resp.json()["presence"] == "online"

    # Проверка TTL в Redis (70 секунд)
    ttl = await redis_client.ttl(f"presence:{alice_id}")
    assert 60 <= ttl <= 70

    # Bob видит Alice online
    resp = await bob.get("/api/v1/friends")
    assert resp.json()["items"][0]["presence"] == "online"

    # DND режим
    await alice.post("/api/v1/me/presence", json={"presence": "dnd"})
    resp = await bob.get("/api/v1/friends")
    assert resp.json()["items"][0]["presence"] == "dnd"

    # Принудительное удаление heartbeat без sleep
    await redis_client.delete(f"presence:{alice_id}")
    resp = await bob.get("/api/v1/friends")
    assert resp.json()["items"][0]["presence"] == "offline"


@pytest.mark.asyncio
async def test_active_game_and_dnd_watchable_presence(
    alice: AsyncClient, bob: AsyncClient, rng: FixedRng, db: AsyncSession
) -> None:
    # Дружба
    await alice.post("/api/v1/friends/requests", json={"login": "bob"})
    alice_id = await db.scalar(select(User.id).where(User.login == "alice"))
    await bob.post(f"/api/v1/friends/requests/{alice_id}/accept")

    # Начало игры
    game_id = await start_game(alice, bob, rng)

    # Bob видит Alice in_game
    resp = await bob.get("/api/v1/friends")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["presence"] == "in_game"
    assert item["game_id"] == game_id

    # Alice ставит DND во время активной игры: статус DND, но game_id сохраняется для наблюдения
    await alice.post("/api/v1/me/presence", json={"presence": "dnd"})
    resp = await bob.get("/api/v1/friends")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["presence"] == "dnd"
    assert item["game_id"] == game_id


@pytest.mark.asyncio
async def test_block_lifecycle(
    alice: AsyncClient, bob: AsyncClient, db: AsyncSession
) -> None:
    await alice.post("/api/v1/friends/requests", json={"login": "bob"})
    alice_user = await db.scalar(select(User).where(User.login == "alice"))
    bob_user = await db.scalar(select(User).where(User.login == "bob"))
    await bob.post(f"/api/v1/friends/requests/{alice_user.id}/accept")

    # 1. Alice блокирует Bob
    resp = await alice.post("/api/v1/me/blocks", json={"login": "bob"})
    assert resp.status_code == 204

    # Дружба удалена в обе стороны
    assert len((await alice.get("/api/v1/friends")).json()["items"]) == 0
    assert len((await bob.get("/api/v1/friends")).json()["items"]) == 0

    # 2. Поиск исключает заблокированных в обе стороны
    assert len((await alice.get("/api/v1/users/search?q=bob")).json()["items"]) == 0
    assert len((await bob.get("/api/v1/users/search?q=alice")).json()["items"]) == 0

    # 3. Запросы в друзья блокируются в обе стороны
    req1 = await alice.post("/api/v1/friends/requests", json={"login": "bob"})
    assert req1.status_code == 403
    assert req1.json()["error"]["code"] == "CONTACT_BLOCKED"

    req2 = await bob.post("/api/v1/friends/requests", json={"login": "alice"})
    assert req2.status_code == 403
    assert req2.json()["error"]["code"] == "CONTACT_BLOCKED"

    # 4. Подарки блокируются в обе стороны
    item_ids = await give_items("alice", ["genesis-pawn-chalk"])
    gift1 = await alice.post(
        "/api/v1/gifts",
        json={"item_id": item_ids[0], "to_login": "bob"},
    )
    assert gift1.status_code == 403
    assert gift1.json()["error"]["code"] == "CONTACT_BLOCKED"

    item_ids_bob = await give_items("bob", ["genesis-pawn-chalk"])
    gift2 = await bob.post(
        "/api/v1/gifts",
        json={"item_id": item_ids_bob[0], "to_login": "alice"},
    )
    assert gift2.status_code == 403
    assert gift2.json()["error"]["code"] == "CONTACT_BLOCKED"

    # 5. Разблокировка
    unblock = await alice.delete(f"/api/v1/me/blocks/{bob_user.id}")
    assert unblock.status_code == 204
    assert len((await alice.get("/api/v1/friends")).json()["items"]) == 0


@pytest.mark.asyncio
async def test_mutual_block_relationship(
    alice: AsyncClient, bob: AsyncClient, db: AsyncSession
) -> None:
    # И Alice блокирует Bob, и Bob блокирует Alice
    await alice.post("/api/v1/me/blocks", json={"login": "bob"})
    await bob.post("/api/v1/me/blocks", json={"login": "alice"})

    # Оба должны видеть relationship 'blocked' и blocked_by_me True, чтобы сохранить действие разблокировки
    resp_a = await alice.get("/api/v1/users/bob/social")
    assert resp_a.status_code == 200
    assert resp_a.json()["relationship"] == "blocked"
    assert resp_a.json()["blocked_by_me"] is True

    resp_b = await bob.get("/api/v1/users/alice/social")
    assert resp_b.status_code == 200
    assert resp_b.json()["relationship"] == "blocked"
    assert resp_b.json()["blocked_by_me"] is True


@pytest.mark.asyncio
async def test_user_social_profile(
    alice: AsyncClient, bob: AsyncClient, db: AsyncSession
) -> None:
    # Self
    resp = await alice.get("/api/v1/users/alice/social")
    assert resp.status_code == 200
    assert resp.json()["relationship"] == "self"

    # Stranger (presence offline, game_id null)
    resp = await alice.get("/api/v1/users/bob/social")
    assert resp.status_code == 200
    assert resp.json()["relationship"] == "none"
    assert resp.json()["presence"] == "offline"
    assert resp.json()["game_id"] is None

    # Outgoing / Incoming
    await alice.post("/api/v1/friends/requests", json={"login": "bob"})
    assert (await alice.get("/api/v1/users/bob/social")).json()["relationship"] == "outgoing"
    assert (await bob.get("/api/v1/users/alice/social")).json()["relationship"] == "incoming"


@pytest.mark.asyncio
async def test_ensure_invitation_allowed(alice: AsyncClient, bob: AsyncClient) -> None:
    # Вызовы через API и изолированные проверки
    async with SessionLocal() as test_db:
        alice_u = (await test_db.scalars(select(User).where(User.login == "alice"))).one()
        bob_u = (await test_db.scalars(select(User).where(User.login == "bob"))).one()
        alice_id, bob_id = alice_u.id, bob_u.id

    # 1. Разрешено по умолчанию
    async with SessionLocal() as db_call:
        res = await ensure_invitation_allowed(db_call, alice_id, bob_id)
        assert res.id == bob_id

    # 2. match_invites = 'none' -> 403 INVITES_DISABLED
    await bob.patch("/api/v1/me/social-settings", json={"match_invites": "none"})
    async with SessionLocal() as db_call:
        with pytest.raises(Exception) as exc:
            await ensure_invitation_allowed(db_call, alice_id, bob_id)
        assert exc.value.code == "INVITES_DISABLED"

    # 3. match_invites = 'friends' and not friends -> 403 INVITES_DISABLED
    await bob.patch("/api/v1/me/social-settings", json={"match_invites": "friends"})
    async with SessionLocal() as db_call:
        with pytest.raises(Exception) as exc:
            await ensure_invitation_allowed(db_call, alice_id, bob_id)
        assert exc.value.code == "INVITES_DISABLED"

    # 4. DND mode -> 403 INVITES_DISABLED независимо от heartbeat
    await bob.patch("/api/v1/me/social-settings", json={"match_invites": "all", "presence_mode": "dnd"})
    async with SessionLocal() as db_call:
        with pytest.raises(Exception) as exc:
            await ensure_invitation_allowed(db_call, alice_id, bob_id)
        assert exc.value.code == "INVITES_DISABLED"

    # 5. Блокировка отклоняет приглашения с CONTACT_BLOCKED
    await bob.patch("/api/v1/me/social-settings", json={"match_invites": "all", "presence_mode": "online"})
    await alice.post("/api/v1/me/blocks", json={"login": "bob"})
    async with SessionLocal() as db_call:
        with pytest.raises(Exception) as exc:
            await ensure_invitation_allowed(db_call, alice_id, bob_id)
        assert exc.value.code == "CONTACT_BLOCKED"
