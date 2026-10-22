from datetime import datetime, timedelta

from sqlalchemy import select

import app.core.clock as clock
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import InventoryItem, User
from tests.conftest import give_items


async def _user_id(login: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(User.id).where(User.login == login))


async def test_gift_flow(alice, bob) -> None:
    ids = await give_items("alice", ["genesis-knight-frost"])
    item_id = ids[0]
    resp = await alice.put("/api/v1/loadout/N", json={"inventory_item_id": item_id})
    assert resp.status_code == 200, resp.text

    inv_before = (await alice.get("/api/v1/inventory")).json()
    old_acquired = next(
        i["acquired_at"] for i in inv_before if i["id"] == item_id
    )

    resp = await alice.post(
        "/api/v1/gifts",
        json={
            "item_id": item_id,
            "to_login": "bob",
            "note": "с днём рождения",
        },
    )
    assert resp.status_code == 201, resp.text

    # Слот пуст.
    loadout = (await alice.get("/api/v1/loadout")).json()
    assert loadout["N"] is None

    # Предмет у bob, acquired_at обновлён.
    bob_id = await _user_id("bob")
    async with SessionLocal() as db:
        item = await db.get(InventoryItem, item_id)
        assert item is not None
        assert item.user_id == bob_id
        assert item.status == "owned"
        assert item.acquired_at > datetime.fromisoformat(old_acquired)

    # Непросмотренный подарок: unseen-count = 1.
    resp = await bob.get("/api/v1/me/gifts/unseen-count")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1

    # Список входящих: seen=false, записка совпадает.
    resp = await bob.get("/api/v1/me/gifts?direction=in")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    gift = items[0]
    assert gift["item"]["id"] == item_id
    assert gift["from_login"] == "alice"
    assert gift["to_login"] == "bob"
    assert gift["note"] == "с днём рождения"
    assert gift["seen"] is False

    # Повторное чтение помечает seen; значение в первом ответе было «до».
    resp = await bob.get("/api/v1/me/gifts?direction=in")
    assert resp.json()["items"][0]["seen"] is True

    resp = await bob.get("/api/v1/me/gifts/unseen-count")
    assert resp.json()["count"] == 0

    # У отправителя — один исходящий.
    resp = await alice.get("/api/v1/me/gifts?direction=out")
    assert len(resp.json()["items"]) == 1


async def test_gift_errors(alice, bob, db) -> None:
    ids = await give_items("alice", ["genesis-pawn-chalk"])

    # Себе.
    resp = await alice.post(
        "/api/v1/gifts", json={"item_id": ids[0], "to_login": "alice"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CANNOT_GIFT_SELF"

    # Неизвестный логин.
    resp = await alice.post(
        "/api/v1/gifts", json={"item_id": ids[0], "to_login": "nobody"}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "USER_NOT_FOUND"

    # Забаненный получатель.
    async with SessionLocal() as ban_db:
        async with ban_db.begin():
            eve = User(
                login="eve",
                email="eve@example.com",
                password_hash=hash_password("password123"),
                is_banned=True,
            )
            ban_db.add(eve)
            await ban_db.flush()
    resp = await alice.post(
        "/api/v1/gifts", json={"item_id": ids[0], "to_login": "eve"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "RECIPIENT_BANNED"

    # Выставленный предмет.
    resp = await alice.post(
        "/api/v1/market/listings", json={"item_id": ids[0], "price": 10}
    )
    assert resp.status_code == 201, resp.text
    resp = await alice.post(
        "/api/v1/gifts", json={"item_id": ids[0], "to_login": "bob"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_NOT_OWNED"

    # Записка 141 символ.
    resp = await alice.post(
        "/api/v1/gifts",
        json={"item_id": ids[0], "to_login": "bob", "note": "а" * 141},
    )
    assert resp.status_code == 422


async def test_gift_resets_trade_hold(alice, bob, frozen) -> None:
    from tests.conftest import set_setting

    await set_setting("trade_hold_hours", 24)
    ids = await give_items("alice", ["genesis-pawn-chalk"])
    # Предмет получен alice двое суток назад.
    async with SessionLocal() as db:
        async with db.begin():
            item = await db.get(InventoryItem, ids[0])
            assert item is not None
            item.acquired_at = clock.now() - timedelta(days=2)

    resp = await alice.post(
        "/api/v1/gifts", json={"item_id": ids[0], "to_login": "bob"}
    )
    assert resp.status_code == 201, resp.text

    # bob сразу выставить не может: acquired_at обновлён при дарении.
    resp = await bob.post(
        "/api/v1/market/listings", json={"item_id": ids[0], "price": 10}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TRADE_HOLD"
