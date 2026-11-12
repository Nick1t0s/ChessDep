import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.main import app
from app.models.social import Friendship, InviteDelivery, Notification
from app.models.user import User
from app.services.friends import require_friend
from app.services.notifications import notify


async def _get_user_info(client: AsyncClient) -> dict:
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_friends_lifecycle(alice: AsyncClient, bob: AsyncClient, db: AsyncSession) -> None:
    alice_info = await _get_user_info(alice)
    bob_info = await _get_user_info(bob)

    # 1. Отправка заявки в друзья от Alice к Bob
    resp = await alice.post("/api/v1/friends/requests", json={"login": bob_info["login"]})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "pending"}

    # Проверяем списки заявок
    alice_reqs = (await alice.get("/api/v1/friends/requests")).json()
    assert len(alice_reqs["incoming"]) == 0
    assert len(alice_reqs["outgoing"]) == 1
    assert alice_reqs["outgoing"][0]["id"] == bob_info["id"]
    assert alice_reqs["outgoing"][0]["login"] == bob_info["login"]

    bob_reqs = (await bob.get("/api/v1/friends/requests")).json()
    assert len(bob_reqs["incoming"]) == 1
    assert len(bob_reqs["outgoing"]) == 0
    assert bob_reqs["incoming"][0]["id"] == alice_info["id"]
    assert bob_reqs["incoming"][0]["login"] == alice_info["login"]

    # Проверяем, что Боб получил уведомление
    bob_notifs = (await bob.get("/api/v1/notifications")).json()
    assert bob_notifs["unread_count"] >= 1
    req_notif = next(
        n for n in bob_notifs["items"]
        if n["kind"] == "friend_request" and alice_info["login"] in n["body"]
    )
    assert req_notif["href"] == "/friends.html"

    # 2. Bob принимает заявку от Alice
    accept_resp = await bob.post(f"/api/v1/friends/requests/{alice_info['id']}/accept")
    assert accept_resp.status_code == 200, accept_resp.text
    assert accept_resp.json() == {"status": "accepted"}

    # После принятия в заявках пусто
    bob_reqs_after = (await bob.get("/api/v1/friends/requests")).json()
    assert len(bob_reqs_after["incoming"]) == 0
    assert len(bob_reqs_after["outgoing"]) == 0

    # В друзьях у обоих есть друг
    alice_friends = (await alice.get("/api/v1/friends")).json()
    assert len(alice_friends["items"]) == 1
    assert alice_friends["items"][0]["id"] == bob_info["id"]
    assert alice_friends["items"][0]["login"] == bob_info["login"]

    bob_friends = (await bob.get("/api/v1/friends")).json()
    assert len(bob_friends["items"]) == 1
    assert bob_friends["items"][0]["id"] == alice_info["id"]
    assert bob_friends["items"][0]["login"] == alice_info["login"]

    # Alice получила уведомление о принятии
    alice_notifs = (await alice.get("/api/v1/notifications")).json()
    acc_notif = next(
        n for n in alice_notifs["items"]
        if n["kind"] == "friend_accepted" and bob_info["login"] in n["body"]
    )
    assert acc_notif["href"] == f"/user.html?login={bob_info['login']}"

    # 3. Удаление из друзей (Alice удаляет Bob)
    del_resp = await alice.delete(f"/api/v1/friends/{bob_info['id']}")
    assert del_resp.status_code == 204

    # Друзей больше нет ни у кого
    assert len((await alice.get("/api/v1/friends")).json()["items"]) == 0
    assert len((await bob.get("/api/v1/friends")).json()["items"]) == 0


@pytest.mark.asyncio
async def test_friend_request_permissions_and_rejections(
    alice: AsyncClient,
    bob: AsyncClient,
    carol: AsyncClient,
) -> None:
    alice_info = await _get_user_info(alice)
    bob_info = await _get_user_info(bob)
    carol_info = await _get_user_info(carol)

    # Нельзя добавить себя
    self_resp = await alice.post("/api/v1/friends/requests", json={"login": alice_info["login"]})
    assert self_resp.status_code == 400

    # Alice отправляет заявку Bob
    await alice.post("/api/v1/friends/requests", json={"login": bob_info["login"]})

    # Инициатор (Alice) не может сама принять свою исходящую заявку (403)
    alice_accept = await alice.post(f"/api/v1/friends/requests/{bob_info['id']}/accept")
    assert alice_accept.status_code == 403

    # Третья сторона (Carol) не может принять чужую заявку (404)
    carol_accept = await carol.post(f"/api/v1/friends/requests/{alice_info['id']}/accept")
    assert carol_accept.status_code == 404

    # Отклонение заявки Бобом
    bob_reject = await bob.delete(f"/api/v1/friends/requests/{alice_info['id']}")
    assert bob_reject.status_code == 204

    # Заявки больше нет
    assert len((await bob.get("/api/v1/friends/requests")).json()["incoming"]) == 0
    assert len((await alice.get("/api/v1/friends/requests")).json()["outgoing"]) == 0


@pytest.mark.asyncio
async def test_cancel_outgoing_request(alice: AsyncClient, bob: AsyncClient) -> None:
    bob_info = await _get_user_info(bob)

    # Alice отправляет заявку Bob
    await alice.post("/api/v1/friends/requests", json={"login": bob_info["login"]})

    # Alice отменяет свою исходящую заявку
    cancel_resp = await alice.delete(f"/api/v1/friends/requests/{bob_info['id']}")
    assert cancel_resp.status_code == 204

    # Заявка отменена у обоих
    assert len((await alice.get("/api/v1/friends/requests")).json()["outgoing"]) == 0
    assert len((await bob.get("/api/v1/friends/requests")).json()["incoming"]) == 0


@pytest.mark.asyncio
async def test_friend_duplicates_and_cross_conflicts(
    alice: AsyncClient,
    bob: AsyncClient,
) -> None:
    alice_info = await _get_user_info(alice)
    bob_info = await _get_user_info(bob)

    # Alice отправляет заявку Bob
    resp1 = await alice.post("/api/v1/friends/requests", json={"login": bob_info["login"]})
    assert resp1.status_code == 200

    # Повторная отправка той же заявки -> 409
    resp_dup = await alice.post("/api/v1/friends/requests", json={"login": bob_info["login"]})
    assert resp_dup.status_code == 409

    # Встречная отправка от Bob к Alice -> 409 (требуется явный accept)
    resp_cross = await bob.post("/api/v1/friends/requests", json={"login": alice_info["login"]})
    assert resp_cross.status_code == 409

    # Bob принимает
    await bob.post(f"/api/v1/friends/requests/{alice_info['id']}/accept")

    # Повторный accept уже принятой дружбы -> 409
    resp_reaccept = await bob.post(f"/api/v1/friends/requests/{alice_info['id']}/accept")
    assert resp_reaccept.status_code == 409

    # Попытка отправить заявку уже существующему другу -> 409
    resp_friend_again = await alice.post("/api/v1/friends/requests", json={"login": bob_info["login"]})
    assert resp_friend_again.status_code == 409


@pytest.mark.asyncio
async def test_search_and_escaping(
    alice: AsyncClient,
    bob: AsyncClient,
    carol: AsyncClient,
    db: AsyncSession,
) -> None:
    alice_info = await _get_user_info(alice)
    bob_info = await _get_user_info(bob)
    carol_info = await _get_user_info(carol)

    # Валидация длины q: меньше 2 символов -> 422
    assert (await alice.get("/api/v1/users/search?q=a")).status_code == 422

    # Поиск по подстроке регистронезависимый
    resp = await alice.get("/api/v1/users/search?q=BO")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(u["login"] == bob_info["login"] for u in items)

    # Исключение самого себя из выдачи
    resp_self = await alice.get(f"/api/v1/users/search?q={alice_info['login'][:3]}")
    assert resp_self.status_code == 200
    assert not any(u["id"] == alice_info["id"] for u in resp_self.json()["items"])

    # Проверка статусов отношений в поиске:
    # 1) none для carol
    search_carol = (await alice.get(f"/api/v1/users/search?q={carol_info['login']}")).json()["items"]
    assert search_carol[0]["relationship"] == "none"

    # 2) outgoing для bob после отправки заявки
    await alice.post("/api/v1/friends/requests", json={"login": bob_info["login"]})
    search_bob_alice = (await alice.get(f"/api/v1/users/search?q={bob_info['login']}")).json()["items"]
    assert search_bob_alice[0]["relationship"] == "outgoing"

    # 3) incoming для bob со стороны alice
    search_alice_bob = (await bob.get(f"/api/v1/users/search?q={alice_info['login']}")).json()["items"]
    assert search_alice_bob[0]["relationship"] == "incoming"

    # 4) friend после принятия
    await bob.post(f"/api/v1/friends/requests/{alice_info['id']}/accept")
    search_friend = (await alice.get(f"/api/v1/users/search?q={bob_info['login']}")).json()["items"]
    assert search_friend[0]["relationship"] == "friend"

    # Проверка экранирования LIKE-символов % и _
    # Поиск "%" или "_" не должен возвращать всех пользователей, как подстановочные знаки
    wildcard_resp = await alice.get("/api/v1/users/search?q=%%")
    assert wildcard_resp.status_code == 200
    assert len(wildcard_resp.json()["items"]) == 0


@pytest.mark.asyncio
async def test_notifications_isolation_pagination_read(
    alice: AsyncClient,
    bob: AsyncClient,
    db: AsyncSession,
) -> None:
    alice_info = await _get_user_info(alice)
    bob_info = await _get_user_info(bob)

    # Создаём несколько уведомлений для Alice
    async with db.begin():
        for i in range(15):
            await notify(
                db,
                user_id=alice_info["id"],
                kind="market_sale",
                title=f"Sale #{i}",
                body=f"Your item sold {i}",
                href="/market.html",
            )
        # И одно для Bob
        await notify(
            db,
            user_id=bob_info["id"],
            kind="gift",
            title="Gift",
            body="You received a gift",
        )

    # Изоляция: Bob видит только своё уведомление
    bob_notifs = (await bob.get("/api/v1/notifications")).json()
    assert bob_notifs["unread_count"] == 1
    assert len(bob_notifs["items"]) == 1
    assert bob_notifs["items"][0]["kind"] == "gift"

    # Пагинация у Alice: limit=10
    page1 = (await alice.get("/api/v1/notifications?limit=10")).json()
    assert len(page1["items"]) == 10
    assert page1["unread_count"] == 15
    assert page1["next_cursor"] is not None

    page2 = (
        await alice.get(f"/api/v1/notifications?limit=10&before_id={page1['next_cursor']}")
    ).json()
    assert len(page2["items"]) == 5
    assert page2["next_cursor"] is None

    # Пометка одного прочитанным
    first_id = page1["items"][0]["id"]
    r_resp = await alice.post(f"/api/v1/notifications/{first_id}/read")
    assert r_resp.status_code == 204

    count_resp = (await alice.get("/api/v1/notifications/unread-count")).json()
    assert count_resp["count"] == 14

    # Чужой пользователь не может пометить чужое уведомление (Bob пытается прочитать уведомление Alice)
    foreign_resp = await bob.post(f"/api/v1/notifications/{first_id}/read")
    assert foreign_resp.status_code == 404

    # Пометка всех прочитанными
    read_all_resp = await alice.post("/api/v1/notifications/read-all")
    assert read_all_resp.status_code == 204

    count_after = (await alice.get("/api/v1/notifications/unread-count")).json()
    assert count_after["count"] == 0


@pytest.mark.asyncio
async def test_require_friend_and_invite_delivery(
    alice: AsyncClient,
    bob: AsyncClient,
    db: AsyncSession,
) -> None:
    alice_info = await _get_user_info(alice)
    bob_info = await _get_user_info(bob)

    # До дружбы require_friend выбрасывает FRIEND_NOT_FOUND (404)
    async with db.begin():
        with pytest.raises(AppError) as exc_info:
            await require_friend(db, alice_info["id"], bob_info["id"])
        assert exc_info.value.code == "FRIEND_NOT_FOUND"

        # require_friend на самого себя выбрасывает CANNOT_FRIEND_SELF (400)
        with pytest.raises(AppError) as exc_self:
            await require_friend(db, alice_info["id"], alice_info["id"])
        assert exc_self.value.code == "CANNOT_FRIEND_SELF"

    # Устанавливаем дружбу
    await alice.post("/api/v1/friends/requests", json={"login": bob_info["login"]})
    await bob.post(f"/api/v1/friends/requests/{alice_info['id']}/accept")

    # Теперь require_friend успешен и возвращает User
    async with db.begin():
        friend_user = await require_friend(db, alice_info["id"], bob_info["id"])
        assert friend_user.id == bob_info["id"]

    # Проверяем модель InviteDelivery
    # Создаём инвайт для проверки FK
    from app.models.game import Invite
    import app.core.clock as clock
    from datetime import timedelta

    now = clock.now()
    async with db.begin():
        invite = Invite(
            code="testinvcode1",
            creator_id=alice_info["id"],
            time_control="3+0",
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        db.add(invite)
        await db.flush()

        delivery = InviteDelivery(
            code=invite.code,
            recipient_id=bob_info["id"],
            created_at=now,
        )
        db.add(delivery)
        await db.flush()

        # Проверяем выборку
        deliv = await db.scalar(
            select(InviteDelivery).where(
                InviteDelivery.code == invite.code,
                InviteDelivery.recipient_id == bob_info["id"],
            )
        )
        assert deliv is not None
        assert deliv.code == "testinvcode1"
        assert deliv.recipient_id == bob_info["id"]


@pytest.mark.asyncio
async def test_banned_and_self_filtering(
    alice: AsyncClient,
    bob: AsyncClient,
    db: AsyncSession,
) -> None:
    alice_info = await _get_user_info(alice)
    bob_info = await _get_user_info(bob)

    # 1. Самопроверки
    # Поиск самого себя не возвращает свой аккаунт
    self_search = (await alice.get(f"/api/v1/users/search?q={alice_info['login']}")).json()["items"]
    assert not any(u["id"] == alice_info["id"] for u in self_search)

    # Запрос в друзья самому себе -> 400 CANNOT_FRIEND_SELF
    self_req = await alice.post("/api/v1/friends/requests", json={"login": alice_info["login"]})
    assert self_req.status_code == 400

    async with db.begin():
        with pytest.raises(AppError) as exc_self:
            await require_friend(db, alice_info["id"], alice_info["id"])
        assert exc_self.value.code == "CANNOT_FRIEND_SELF"

    # 2. Проверки блокировок
    # Баним Bob
    async with db.begin():
        bob_user = await db.get(User, bob_info["id"])
        assert bob_user is not None
        bob_user.is_banned = True

    # Заблокированный пользователь исключён из поиска
    search_banned = (await alice.get(f"/api/v1/users/search?q={bob_info['login']}")).json()["items"]
    assert not any(u["id"] == bob_info["id"] for u in search_banned)

    # Отправка заявки заблокированному пользователю -> 403 USER_BANNED
    req_banned = await alice.post("/api/v1/friends/requests", json={"login": bob_info["login"]})
    assert req_banned.status_code == 403

    # Разбаниваем Bob, чтобы он отправил заявку Alice
    async with db.begin():
        bob_user = await db.get(User, bob_info["id"])
        assert bob_user is not None
        bob_user.is_banned = False

    send_resp = await bob.post("/api/v1/friends/requests", json={"login": alice_info["login"]})
    assert send_resp.status_code == 200

    # Теперь снова баним Bob (инициатора заявки)
    async with db.begin():
        bob_user = await db.get(User, bob_info["id"])
        assert bob_user is not None
        bob_user.is_banned = True

    # Alice пытается принять заявку от заблокированного инициатора -> 403 USER_BANNED
    accept_banned = await alice.post(f"/api/v1/friends/requests/{bob_info['id']}/accept")
    assert accept_banned.status_code == 403

    # require_friend с заблокированным пользователем -> 403 USER_BANNED
    async with db.begin():
        with pytest.raises(AppError) as exc_banned:
            await require_friend(db, alice_info["id"], bob_info["id"])
        assert exc_banned.value.code == "USER_BANNED"


@pytest.mark.asyncio
async def test_case_insensitive_friendship_send(
    alice: AsyncClient,
    bob: AsyncClient,
) -> None:
    alice_info = await _get_user_info(alice)
    bob_info = await _get_user_info(bob)

    # Отправка запроса с логином в верхнем/смешанном регистре ("BoB")
    resp = await alice.post("/api/v1/friends/requests", json={"login": bob_info["login"].upper()})
    assert resp.status_code == 200
    assert resp.json() == {"status": "pending"}

    # Bob видит входящую заявку от Alice
    bob_reqs = (await bob.get("/api/v1/friends/requests")).json()
    assert len(bob_reqs["incoming"]) == 1
    assert bob_reqs["incoming"][0]["id"] == alice_info["id"]

    # Поиск по подстроке в разном регистре находит пользователя
    search_upper = (await alice.get(f"/api/v1/users/search?q={bob_info['login'].upper()}")).json()["items"]
    assert any(u["id"] == bob_info["id"] for u in search_upper)


@pytest.mark.asyncio
async def test_concurrent_same_pair_requests(
    alice: AsyncClient,
    bob: AsyncClient,
    db: AsyncSession,
) -> None:
    import asyncio

    alice_info = await _get_user_info(alice)
    bob_info = await _get_user_info(bob)

    # Параллельные одновременные запросы на добавление одной и той же пары
    t1 = alice.post("/api/v1/friends/requests", json={"login": bob_info["login"]})
    t2 = alice.post("/api/v1/friends/requests", json={"login": bob_info["login"]})

    res1, res2 = await asyncio.gather(t1, t2)
    statuses = {res1.status_code, res2.status_code}
    assert 200 in statuses
    assert 409 in statuses

    # В базе ровно одна строка заявки и ровно одно уведомление
    async with db.begin():
        low_id = min(alice_info["id"], bob_info["id"])
        high_id = max(alice_info["id"], bob_info["id"])
        friendships = (
            await db.scalars(
                select(Friendship).where(
                    Friendship.user_low_id == low_id,
                    Friendship.user_high_id == high_id,
                    Friendship.status == "pending",
                )
            )
        ).all()
        assert len(friendships) == 1

        notifs = (
            await db.scalars(
                select(Notification).where(
                    Notification.user_id == bob_info["id"],
                    Notification.kind == "friend_request",
                )
            )
        ).all()
        assert len(notifs) == 1


@pytest.mark.asyncio
async def test_notify_href_validation(db: AsyncSession, alice: AsyncClient) -> None:
    async with db.begin():
        # Невалидный href: протокольно-относительный //
        with pytest.raises(AppError) as exc_p:
            await notify(db, user_id=1, kind="gift", title="T", body="B", href="//evil.com")
        assert exc_p.value.code == "INVALID_NOTIFICATION_HREF"

        # Невалидный href: обратные слэши
        with pytest.raises(AppError) as exc_b:
            await notify(db, user_id=1, kind="gift", title="T", body="B", href="/path\\evil")
        assert exc_b.value.code == "INVALID_NOTIFICATION_HREF"

        # Невалидный href: абсолютный http URL
        with pytest.raises(AppError) as exc_u:
            await notify(db, user_id=1, kind="gift", title="T", body="B", href="https://example.com")
        assert exc_u.value.code == "INVALID_NOTIFICATION_HREF"

        # Валидный локальный путь
        n = await notify(db, user_id=1, kind="gift", title="T", body="B", href="/friends.html")
        assert n.href == "/friends.html"
