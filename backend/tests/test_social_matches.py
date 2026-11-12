import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

import app.core.clock as clock
from app.models import ActivePlayer, Game, Invite, User
from app.models.social import Friendship, InviteDelivery, Notification
from app.services.social_matches import notification_action_info
from tests.conftest import start_game


@pytest.mark.asyncio
async def test_rematch_and_targeted_invite_lifecycle(
    alice: AsyncClient, bob: AsyncClient, carol: AsyncClient, db, rng, frozen
):
    # 1. Play real game via start_game fixture and resign
    game_id = await start_game(alice, bob, rng, "3+2")
    resp_resign = await bob.post(f"/api/v1/games/{game_id}/resign")
    assert resp_resign.status_code == 200

    # Ensure finished game
    game = await db.get(Game, uuid.UUID(game_id))
    assert game.status == "finished"

    # Non-participant (Carol) cannot request rematch
    resp = await carol.post(f"/api/v1/games/{game_id}/rematch")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GAME_NOT_FOUND"

    # Alice requests rematch -> 200
    resp_rematch = await alice.post(f"/api/v1/games/{game_id}/rematch")
    assert resp_rematch.status_code == 200, resp_rematch.text
    data = resp_rematch.json()
    code = data["code"]
    assert data["status"] == "sent"

    # Idempotent repeated live request
    resp_repeat = await alice.post(f"/api/v1/games/{game_id}/rematch")
    assert resp_repeat.status_code == 200
    assert resp_repeat.json()["code"] == code

    # Targeted rematch cannot be claimed by third party (Carol)
    resp_carol = await carol.post(f"/api/v1/invites/{code}/accept")
    assert resp_carol.status_code == 403
    assert resp_carol.json()["error"]["code"] == "FORBIDDEN"

    bob_user = (await db.scalars(select(User).where(User.login == "bob"))).one()
    notif = (
        await db.scalars(
            select(Notification).where(
                Notification.user_id == bob_user.id, Notification.kind == "match_invite"
            )
        )
    ).first()
    assert notif is not None
    info = await notification_action_info(db, bob_user.id, notif)
    assert info["action_state"] == "pending"
    assert "accept" in info["allowed_actions"]
    assert "decline" in info["allowed_actions"]

    # Bob declines rematch invite
    resp_dec = await bob.post(f"/api/v1/invites/{code}/decline")
    assert resp_dec.status_code == 204

    # Now Bob cannot accept declined invite
    resp_acc = await bob.post(f"/api/v1/invites/{code}/accept")
    assert resp_acc.status_code == 400
    assert resp_acc.json()["error"]["code"] == "INVITE_DECLINED"

    info_after_decline = await notification_action_info(db, bob_user.id, notif)
    assert info_after_decline["action_state"] == "declined"
    assert info_after_decline["allowed_actions"] == []


@pytest.mark.asyncio
async def test_rematch_acceptance_copies_time_control_and_opponent(
    alice: AsyncClient, bob: AsyncClient, db, rng, frozen
):
    game_id = await start_game(alice, bob, rng, "5+0")
    await alice.post(f"/api/v1/games/{game_id}/resign")

    resp = await bob.post(f"/api/v1/games/{game_id}/rematch")
    assert resp.status_code == 200
    code = resp.json()["code"]

    alice_user = (await db.scalars(select(User).where(User.login == "alice"))).one()
    bob_user = (await db.scalars(select(User).where(User.login == "bob"))).one()

    # Alice accepts
    resp_acc = await alice.post(f"/api/v1/invites/{code}/accept")
    assert resp_acc.status_code == 200
    new_game_id = resp_acc.json()["game_id"]

    new_game = await db.get(Game, uuid.UUID(new_game_id))
    assert new_game.time_control == "5+0"
    assert set([new_game.white_id, new_game.black_id]) == set([alice_user.id, bob_user.id])


@pytest.mark.asyncio
async def test_rematch_aborted_or_active_denied(
    alice: AsyncClient, bob: AsyncClient, db, rng
):
    # Active game rematch denied
    game_id = await start_game(alice, bob, rng, "3+2")
    resp = await alice.post(f"/api/v1/games/{game_id}/rematch")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "GAME_NOT_FINISHED"

    # Abort game
    await alice.post(f"/api/v1/games/{game_id}/abort")
    game = await db.get(Game, uuid.UUID(game_id))
    assert game.status == "aborted"

    # Rematch on aborted game denied
    resp_abort = await alice.post(f"/api/v1/games/{game_id}/rematch")
    assert resp_abort.status_code == 400
    assert resp_abort.json()["error"]["code"] == "GAME_NOT_FINISHED"


@pytest.mark.asyncio
async def test_notification_ownership_and_stale_requests(
    alice: AsyncClient, bob: AsyncClient, carol: AsyncClient, db, frozen
):
    alice_user = (await db.scalars(select(User).where(User.login == "alice"))).one()
    bob_user = (await db.scalars(select(User).where(User.login == "bob"))).one()

    # Alice creates a notification for Bob
    notif = Notification(
        user_id=bob_user.id,
        kind="friend_request",
        title="Запрос в друзья",
        body="alice хочет в друзья",
        href="/friends.html",
        data={"actor_id": alice_user.id},
        read=False,
        created_at=clock.now(),
    )
    db.add(notif)
    await db.commit()

    # 1. Carol cannot act on Bob's notification (ownership check)
    resp = await carol.post(f"/api/v1/notifications/{notif.id}/action", json={"action": "accept"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOTIFICATION_NOT_FOUND"

    # 2. Bob cannot accept when no actual friendship exists (stale notification)
    resp_stale = await bob.post(f"/api/v1/notifications/{notif.id}/action", json={"action": "accept"})
    assert resp_stale.status_code == 400
    assert resp_stale.json()["error"]["code"] == "ACTION_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_notification_actions_used_and_expired(
    alice: AsyncClient, bob: AsyncClient, db, frozen
):
    bob_user = (await db.scalars(select(User).where(User.login == "bob"))).one()
    alice_user = (await db.scalars(select(User).where(User.login == "alice"))).one()

    resp = await alice.post("/api/v1/invites", json={"time_control": "3+2"})
    code = resp.json()["code"]

    notif = Notification(
        user_id=bob_user.id,
        kind="match_invite",
        title="Приглашение",
        body="приглашение",
        href=f"/invite.html?code={code}",
        data={"actor_id": alice_user.id, "invite_code": code},
        read=False,
        created_at=clock.now(),
    )
    db.add(notif)
    await db.commit()

    # Expire invite
    frozen.advance(601)
    info = await notification_action_info(db, bob_user.id, notif)
    assert info["action_state"] == "expired"
    assert info["allowed_actions"] == []

    # Attempt to act on expired invite
    resp_act = await bob.post(f"/api/v1/notifications/{notif.id}/action", json={"action": "accept"})
    assert resp_act.status_code == 400
    assert resp_act.json()["error"]["code"] == "ACTION_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_rematch_rollback_on_notify_failure(
    alice: AsyncClient, bob: AsyncClient, db, rng, monkeypatch
):
    game_id = await start_game(alice, bob, rng, "3+2")
    await bob.post(f"/api/v1/games/{game_id}/resign")

    from app.services import social_matches

    async def fail_notify(*args, **kwargs):
        raise RuntimeError("Notify broker unavailable")

    monkeypatch.setattr(social_matches, "notify", fail_notify)

    with pytest.raises(RuntimeError, match="Notify broker unavailable"):
        await alice.post(f"/api/v1/games/{game_id}/rematch")

    # Ensure transaction rolled back
    invites = (
        await db.scalars(select(Invite).where(Invite.source_game_id == uuid.UUID(game_id)))
    ).all()
    assert len(invites) == 0


@pytest.mark.asyncio
async def test_rematch_muted_notifications_succeeds(
    alice: AsyncClient, bob: AsyncClient, db, rng, monkeypatch
):
    game_id = await start_game(alice, bob, rng, "3+2")
    await bob.post(f"/api/v1/games/{game_id}/resign")

    from app.services import social_matches

    async def muted_notify(*args, **kwargs):
        return None

    monkeypatch.setattr(social_matches, "notify", muted_notify)

    resp = await alice.post(f"/api/v1/games/{game_id}/rematch")
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"


async def test_old_friend_notification_cannot_accept_recreated_request(alice, bob):
    await alice.post('/api/v1/friends/requests', json={'login': 'bob'})
    old = (await bob.get('/api/v1/notifications')).json()['items'][0]
    actor_id = old['data']['actor_id']
    await bob.delete(f'/api/v1/friends/requests/{actor_id}')
    await alice.post('/api/v1/friends/requests', json={'login': 'bob'})
    response = await bob.post(f"/api/v1/notifications/{old['id']}/action", json={'action': 'accept'})
    assert response.status_code == 400, response.text
    assert response.json()['error']['code'] == 'ACTION_NOT_ALLOWED'
    assert (await bob.get('/api/v1/friends')).json()['items'] == []
    assert len((await bob.get('/api/v1/friends/requests')).json()['incoming']) == 1
