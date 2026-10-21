import asyncio
import contextlib
import json
import uuid

import app.core.clock as clock
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.core.errors import AppError
from app.core.sessions import resolve_session
from app.db import SessionLocal
from app.models import Game, User
from app.services import pubsub
from app.services.game_view import build_state, game_players, last_game_action
from app.services.games import color_of

router = APIRouter(tags=["ws"])


def ws_messages(message: dict, state: dict) -> list[dict]:
    out = []
    if message.get("dep"):
        out.append({"type": "dep", "data": message["dep"]})
    out.append({"type": "state", "data": state})
    if message.get("game_over"):
        out.append({"type": "game_over", "data": message["game_over"]})
    return out


async def _load_ws_context(
    game_id: uuid.UUID, token: str | None
) -> tuple[User, Game, dict[str, User], dict | None] | None:
    if token is None:
        return None
    async with SessionLocal() as db:
        async with db.begin():
            resolved = await resolve_session(db, token)
            if resolved is None:
                return None
            _, user = resolved
            if user.is_banned:
                return None
            game = await db.get(Game, game_id)
            if game is None:
                return None
            try:
                color_of(game, user.id)
            except AppError:
                return None
            players = await game_players(db, game)
            last_action = await last_game_action(db, game.id)
        return user, game, players, last_action


def _state_payload(game: Game, user_id: int, players: dict[str, User], last_action: dict | None) -> dict:
    state = build_state(game, user_id, players, clock.now(), last_action)
    return state.model_dump(mode="json", by_alias=True)


async def _client_loop(websocket: WebSocket) -> None:
    while True:
        data = await websocket.receive_json()
        if isinstance(data, dict) and data.get("type") == "ping":
            await websocket.send_json({"type": "pong"})
        # Прочие сообщения клиента игнорируются.


async def _pubsub_loop(
    websocket: WebSocket, pubsub, game_id: uuid.UUID, user_id: int
) -> None:
    async for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        try:
            event = json.loads(message["data"])
        except (TypeError, ValueError):
            continue
        async with SessionLocal() as db:
            game = await db.get(Game, game_id)
            if game is None:
                continue
            try:
                color_of(game, user_id)
            except AppError:
                continue
            players = await game_players(db, game)
            last_action = await last_game_action(db, game.id)
        payload = _state_payload(game, user_id, players, last_action)
        for out in ws_messages(event, payload):
            await websocket.send_json(out)


@router.websocket("/ws/games/{game_id}")
async def ws_game(websocket: WebSocket, game_id: uuid.UUID) -> None:
    token = websocket.cookies.get(settings.cookie_name)
    context = await _load_ws_context(game_id, token)
    if context is None:
        await websocket.close(code=4403)
        return
    user, game, players, last_action = context
    channel = pubsub.game_channel(game.id)
    pubsub_conn = await pubsub.subscribe(channel)
    reader_task: asyncio.Task | None = None
    listener_task: asyncio.Task | None = None
    try:
        await websocket.accept()
        await websocket.send_json(
            {"type": "state", "data": _state_payload(game, user.id, players, last_action)}
        )
        reader_task = asyncio.create_task(_client_loop(websocket))
        listener_task = asyncio.create_task(
            _pubsub_loop(websocket, pubsub_conn, game.id, user.id)
        )
        done, pending = await asyncio.wait(
            {reader_task, listener_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        for task in done:
            with contextlib.suppress(Exception):
                task.result()
    except WebSocketDisconnect:
        pass
    finally:
        for task in (reader_task, listener_task):
            if task is not None:
                task.cancel()
        with contextlib.suppress(Exception):
            await pubsub_conn.unsubscribe(channel)
        await pubsub_conn.aclose()
