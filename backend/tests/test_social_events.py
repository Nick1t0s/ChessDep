import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    ActivePlayer,
    InventoryItem,
    Invite,
    ItemDef,
    ItemTransfer,
    MarketListing,
    User,
)
from app.models.social import InviteDelivery, Notification
from tests.conftest import give_items, set_balance, set_setting, start_game


async def _get_user(login: str) -> User:
    async with SessionLocal() as db:
        return (await db.scalars(select(User).where(User.login == login))).one()


async def _make_friends(client_a, client_b, user_a: User, user_b: User) -> None:
    req_resp = await client_a.post("/api/v1/friends/requests", json={"login": user_b.login})
    assert req_resp.status_code == 200, req_resp.text
    accept_resp = await client_b.post(f"/api/v1/friends/requests/{user_a.id}/accept")
    assert accept_resp.status_code == 200, accept_resp.text


@pytest.mark.asyncio
async def test_gift_producer_notification_success(alice, bob) -> None:
    ids = await give_items("alice", ["genesis-knight-frost"])
    item_id = ids[0]
    bob_user = await _get_user("bob")

    gift_resp = await alice.post(
        "/api/v1/gifts",
        json={"item_id": item_id, "to_login": "bob", "note": "С наилучшими пожеланиями"},
    )
    assert gift_resp.status_code == 201, gift_resp.text

    async with SessionLocal() as db:
        notifs = (
            await db.scalars(
                select(Notification).where(
                    Notification.user_id == bob_user.id,
                    Notification.kind == "gift",
                )
            )
        ).all()
        assert len(notifs) == 1
        notif = notifs[0]
        assert notif.kind == "gift"
        assert notif.user_id == bob_user.id
        assert notif.href == "/gifts.html"
        assert "alice" in notif.body.lower()
        assert "с наилучшими пожеланиями" in notif.body.lower()
        assert notif.read is False


@pytest.mark.asyncio
async def test_gift_producer_atomicity_on_notify_failure(alice, bob, monkeypatch) -> None:
    ids = await give_items("alice", ["genesis-knight-frost"])
    item_id = ids[0]
    alice_user = await _get_user("alice")
    bob_user = await _get_user("bob")

    async def _crash_notify(*args, **kwargs):
        raise RuntimeError("Gifts notify failure for test rollback")

    monkeypatch.setattr("app.services.gifts.notify", _crash_notify)

    # При сбое notify в той же транзакции запрос должен завершиться исключением
    with pytest.raises(Exception):
        await alice.post(
            "/api/v1/gifts",
            json={"item_id": item_id, "to_login": "bob", "note": "crash notify"},
        )

    # Проверяем откат транзакции:
    # 1. Предмет остался у Alice
    # 2. Запись ItemTransfer не сохранилась
    # 3. Уведомление не сохранилось
    async with SessionLocal() as db:
        item = await db.get(InventoryItem, item_id)
        assert item is not None
        assert item.user_id == alice_user.id

        transfers = (
            await db.scalars(
                select(ItemTransfer).where(ItemTransfer.item_id == item_id)
            )
        ).all()
        assert len(transfers) == 0

        notifs = (
            await db.scalars(
                select(Notification).where(Notification.user_id == bob_user.id)
            )
        ).all()
        assert len(notifs) == 0


@pytest.mark.asyncio
async def test_market_sale_producer_notification_success(alice, bob) -> None:
    ids = await give_items("alice", ["genesis-knight-frost"])
    item_id = ids[0]
    alice_user = await _get_user("alice")

    # Устанавливаем известную комиссию маркета 0.05
    await set_setting("market_fee", 0.05)

    list_resp = await alice.post(
        "/api/v1/market/listings",
        json={"item_id": item_id, "price": 100},
    )
    assert list_resp.status_code == 201, list_resp.text
    listing_id = list_resp.json()["id"]

    await set_balance("bob", 1000)
    buy_resp = await bob.post(f"/api/v1/market/listings/{listing_id}/buy")
    assert buy_resp.status_code == 200, buy_resp.text

    async with SessionLocal() as db:
        listing = await db.get(MarketListing, listing_id)
        assert listing is not None
        item_def = await db.get(ItemDef, listing.item_def_id)
        assert item_def is not None

        notifs = (
            await db.scalars(
                select(Notification).where(
                    Notification.user_id == alice_user.id,
                    Notification.kind == "market_sale",
                )
            )
        ).all()
        assert len(notifs) == 1
        notif = notifs[0]
        assert notif.kind == "market_sale"
        assert notif.user_id == alice_user.id
        assert notif.href == f"/market-item.html?def={listing.item_def_id}"
        # Проверяем точную чистую сумму выручки: 100 - ceil(100 * 0.05) = 95
        assert "95" in notif.body
        # Проверяем отображение полезной информации о предмете (название скина)
        assert item_def.name in notif.body
        assert notif.read is False


@pytest.mark.asyncio
async def test_market_sale_producer_atomicity_on_notify_failure(alice, bob, monkeypatch) -> None:
    ids = await give_items("alice", ["genesis-knight-frost"])
    item_id = ids[0]
    alice_user = await _get_user("alice")
    bob_user = await _get_user("bob")

    await set_setting("market_fee", 0.05)
    await set_balance("bob", 1000)

    alice_balance_before = (await _get_user("alice")).balance
    bob_balance_before = (await _get_user("bob")).balance

    list_resp = await alice.post(
        "/api/v1/market/listings",
        json={"item_id": item_id, "price": 100},
    )
    assert list_resp.status_code == 201, list_resp.text
    listing_id = list_resp.json()["id"]

    async def _crash_notify(*args, **kwargs):
        raise RuntimeError("Market notify failure for test rollback")

    monkeypatch.setattr("app.services.market.notify", _crash_notify)

    # При сбое notify во время покупки запрос завершается исключением
    with pytest.raises(Exception):
        await bob.post(f"/api/v1/market/listings/{listing_id}/buy")

    # Проверяем полный откат транзакции:
    # 1. Лот остался active
    # 2. Предмет остался listed у Alice
    # 3. Балансы Bob и Alice не изменились
    # 4. ItemTransfer не создан
    # 5. Уведомление не сохранено
    async with SessionLocal() as db:
        listing = await db.get(MarketListing, listing_id)
        assert listing is not None
        assert listing.status == "active"
        assert listing.buyer_id is None

        item = await db.get(InventoryItem, item_id)
        assert item is not None
        assert item.status == "listed"
        assert item.user_id == alice_user.id

        alice_cur = (await db.scalars(select(User).where(User.id == alice_user.id))).one()
        bob_cur = (await db.scalars(select(User).where(User.id == bob_user.id))).one()
        assert alice_cur.balance == alice_balance_before
        assert bob_cur.balance == bob_balance_before

        transfers = (
            await db.scalars(
                select(ItemTransfer).where(ItemTransfer.ref == str(listing_id))
            )
        ).all()
        assert len(transfers) == 0

        notifs = (
            await db.scalars(
                select(Notification).where(
                    Notification.user_id == alice_user.id,
                    Notification.kind == "market_sale",
                )
            )
        ).all()
        assert len(notifs) == 0


@pytest.mark.asyncio
async def test_friend_match_invite_send_and_duplicate_idempotency(alice, bob) -> None:
    alice_user = await _get_user("alice")
    bob_user = await _get_user("bob")
    await _make_friends(alice, bob, alice_user, bob_user)

    # Alice создаёт инвайт
    inv_resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    assert inv_resp.status_code == 200, inv_resp.text
    code = inv_resp.json()["code"]

    # Alice отправляет инвайт другу Bob
    send_resp = await alice.post(
        f"/api/v1/invites/{code}/send",
        json={"friend_id": bob_user.id},
    )
    assert send_resp.status_code == 200, send_resp.text
    assert send_resp.json() == {"status": "sent"}

    # Проверяем доставку и уведомление
    async with SessionLocal() as db:
        deliveries = (
            await db.scalars(
                select(InviteDelivery).where(
                    InviteDelivery.code == code,
                    InviteDelivery.recipient_id == bob_user.id,
                )
            )
        ).all()
        assert len(deliveries) == 1

        notifs = (
            await db.scalars(
                select(Notification).where(
                    Notification.user_id == bob_user.id,
                    Notification.kind == "match_invite",
                )
            )
        ).all()
        assert len(notifs) == 1
        notif = notifs[0]
        assert notif.kind == "match_invite"
        assert notif.user_id == bob_user.id
        assert notif.href == f"/invite.html?code={code}"
        assert "alice" in notif.body.lower()
        assert notif.read is False

    # Повторная отправка того же инвайта тому же другу — идемпотентна (без дублирования уведомления)
    send_dup = await alice.post(
        f"/api/v1/invites/{code}/send",
        json={"friend_id": bob_user.id},
    )
    assert send_dup.status_code == 200, send_dup.text
    assert send_dup.json() == {"status": "sent"}

    async with SessionLocal() as db:
        deliveries = (
            await db.scalars(
                select(InviteDelivery).where(
                    InviteDelivery.code == code,
                    InviteDelivery.recipient_id == bob_user.id,
                )
            )
        ).all()
        assert len(deliveries) == 1  # не удвоилось

        notifs = (
            await db.scalars(
                select(Notification).where(
                    Notification.user_id == bob_user.id,
                    Notification.kind == "match_invite",
                )
            )
        ).all()
        assert len(notifs) == 1  # нет повторного уведомления


@pytest.mark.asyncio
async def test_friend_match_invite_ownership_and_no_leak(alice, bob, carol) -> None:
    bob_user = await _get_user("bob")

    # Alice создаёт инвайт
    inv_resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    assert inv_resp.status_code == 200
    code = inv_resp.json()["code"]

    # Carol (не создатель) пытается отправить инвайт Alice -> 404, код не утекает
    resp = await carol.post(
        f"/api/v1/invites/{code}/send",
        json={"friend_id": bob_user.id},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "INVITE_NOT_FOUND"

    # Несуществующий код также возвращает 404
    fake_code = "nonexistent99"
    resp_fake = await alice.post(
        f"/api/v1/invites/{fake_code}/send",
        json={"friend_id": bob_user.id},
    )
    assert resp_fake.status_code == 404
    assert resp_fake.json()["error"]["code"] == "INVITE_NOT_FOUND"


@pytest.mark.asyncio
async def test_friend_match_invite_stranger_and_self_rejected(alice, bob, carol) -> None:
    alice_user = await _get_user("alice")
    carol_user = await _get_user("carol")

    inv_resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    assert inv_resp.status_code == 200
    code = inv_resp.json()["code"]

    # Отправка себе -> отказ
    self_resp = await alice.post(
        f"/api/v1/invites/{code}/send",
        json={"friend_id": alice_user.id},
    )
    assert self_resp.status_code in (400, 403, 404)
    assert "error" in self_resp.json() and "code" in self_resp.json()["error"]

    # Отправка чужаку (не в друзьях) -> отказ
    stranger_resp = await alice.post(
        f"/api/v1/invites/{code}/send",
        json={"friend_id": carol_user.id},
    )
    assert stranger_resp.status_code in (400, 403, 404)
    assert "error" in stranger_resp.json() and "code" in stranger_resp.json()["error"]


@pytest.mark.asyncio
async def test_friend_match_invite_expired_and_used(alice, bob, carol, frozen) -> None:
    alice_user = await _get_user("alice")
    bob_user = await _get_user("bob")
    await _make_friends(alice, bob, alice_user, bob_user)

    # 1. Протухший инвайт
    inv_resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    assert inv_resp.status_code == 200
    code = inv_resp.json()["code"]

    frozen.advance(605)  # больше 10 минут TTL

    exp_resp = await alice.post(
        f"/api/v1/invites/{code}/send",
        json={"friend_id": bob_user.id},
    )
    assert exp_resp.status_code == 400
    assert exp_resp.json()["error"]["code"] == "INVITE_EXPIRED"

    # 2. Использованный инвайт (уже принят в партию)
    inv_resp2 = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    code2 = inv_resp2.json()["code"]

    accept_resp = await carol.post(f"/api/v1/invites/{code2}/accept")
    assert accept_resp.status_code == 200

    used_resp = await alice.post(
        f"/api/v1/invites/{code2}/send",
        json={"friend_id": bob_user.id},
    )
    assert used_resp.status_code == 400
    assert used_resp.json()["error"]["code"] == "INVITE_EXPIRED"


@pytest.mark.asyncio
async def test_friend_match_invite_active_player_rejected(alice, bob, carol, rng) -> None:
    alice_user = await _get_user("alice")
    bob_user = await _get_user("bob")
    await _make_friends(alice, bob, alice_user, bob_user)

    inv_resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    assert inv_resp.status_code == 200
    code = inv_resp.json()["code"]

    # Bob начинает реальную партию с Carol через conftest.start_game
    await start_game(bob, carol, rng)

    resp = await alice.post(
        f"/api/v1/invites/{code}/send",
        json={"friend_id": bob_user.id},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "ALREADY_IN_GAME"


@pytest.mark.asyncio
async def test_friend_match_invite_creator_active_player_rejected(alice, bob, carol, rng) -> None:
    alice_user = await _get_user("alice")
    bob_user = await _get_user("bob")
    await _make_friends(alice, bob, alice_user, bob_user)

    inv_resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    assert inv_resp.status_code == 200
    code = inv_resp.json()["code"]

    # Alice начинает реальную партию с Carol
    await start_game(alice, carol, rng)

    # Создатель не может отправлять инвайт, находясь в активной партии
    resp = await alice.post(
        f"/api/v1/invites/{code}/send",
        json={"friend_id": bob_user.id},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "ALREADY_IN_GAME"


@pytest.mark.asyncio
async def test_friend_match_invite_link_compatibility(alice, bob, rng) -> None:
    alice_user = await _get_user("alice")
    bob_user = await _get_user("bob")
    await _make_friends(alice, bob, alice_user, bob_user)

    inv_resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    assert inv_resp.status_code == 200
    code = inv_resp.json()["code"]

    # Отправка инвайта другу
    send_resp = await alice.post(
        f"/api/v1/invites/{code}/send",
        json={"friend_id": bob_user.id},
    )
    assert send_resp.status_code == 200

    # Принятие инвайта через стандартный эндпоинт ссылки /api/v1/invites/{code}/accept
    rng.values = [0.0]
    accept_resp = await bob.post(f"/api/v1/invites/{code}/accept")
    assert accept_resp.status_code == 200
    assert "game_id" in accept_resp.json()
