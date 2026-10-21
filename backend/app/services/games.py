import uuid
from datetime import UTC, datetime, timedelta

import chess
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.chess_engine import (
    DEP_LIMIT_PER_GAME,
    EngineError,
    DepResolution,
    apply_move,
    can_win_on_time,
    game_outcome,
    position_key,
    resolve_dep,
    validate_dep,
)
from app.core.clock import to_ms
from app.core.errors import AppError
from app.db import after_commit
from app.models import ActivePlayer, Game, GameEvent, Ledger, User
from app.redis import redis_client
from app.schemas.games import DepEvent, EloDelta, GameOver, Rewards
from app.services import pubsub
from app.services.economy import apply_delta, lock_user
from app.services.elo import elo_update
from app.services.game_clock import deadline, is_expired, parse_time_control, remaining_ms, turn_color
from app.services.rolls import get_rng, record_roll
from app.services.settings import get_setting

_ENGINE_MOVE_ERROR = AppError(400, "ILLEGAL_MOVE", "Невозможный ход")

_DEP_ENGINE_MESSAGES = {
    "DEP_INVALID_PIECE": "Нельзя депнуть эту фигуру",
    "DEP_INVALID_TARGET": "Некорректная цель депа",
    "WOULD_CHECK_OPPONENT": "Деп дал бы шах сопернику",
}

_NOT_YOUR_TURN = AppError(400, "NOT_YOUR_TURN", "Сейчас не ваш ход")
_NOT_ACTIVE = AppError(400, "GAME_NOT_ACTIVE", "Партия не активна")
_TIME_EXPIRED = AppError(400, "TIME_EXPIRED", "Ваше время вышло, дождитесь результата")
_VERSION_CONFLICT = AppError(409, "VERSION_CONFLICT", "Партия изменилась, обновите её")
_ALREADY_IN_GAME = AppError(409, "ALREADY_IN_GAME", "У вас уже есть активная партия")


async def lock_game(db: AsyncSession, game_id: uuid.UUID) -> Game:
    # FOR UPDATE всегда с populate_existing=True, иначе SQLAlchemy может
    # вернуть объект из identity map со старыми атрибутами.
    game = await db.scalar(
        select(Game)
        .where(Game.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if game is None:
        raise AppError(404, "GAME_NOT_FOUND", "Партия не найдена")
    return game


def color_of(game: Game, user_id: int) -> str:
    if user_id == game.white_id:
        return "white"
    if user_id == game.black_id:
        return "black"
    raise AppError(404, "GAME_NOT_FOUND", "Партия не найдена")


def bump(game: Game) -> int:
    game.version += 1
    return game.version


def add_event(db: AsyncSession, game: Game, *, actor: str, kind: str, payload: dict) -> None:
    # Вызывать после bump: seq = game.version.
    db.add(
        GameEvent(
            game_id=game.id,
            seq=game.version,
            ply=game.ply,
            actor=actor,
            kind=kind,
            payload=payload,
            fen_after=game.fen,
            white_ms=game.white_ms,
            black_ms=game.black_ms,
        )
    )


def schedule_deadline(db: AsyncSession, game: Game) -> None:
    game_id = game.id

    async def _hook() -> None:
        dl = deadline(game)
        if dl is None:
            await redis_client.zrem("clock:deadlines", str(game_id))
        else:
            await redis_client.zadd("clock:deadlines", {str(game_id): to_ms(dl)})

    after_commit(db, _hook)


def publish(db: AsyncSession, game: Game, *, dep: DepEvent | None = None,
            game_over: GameOver | None = None) -> None:
    version = game.version
    dep_data = dep.model_dump(mode="json", by_alias=True) if dep is not None else None
    game_over_data = (
        game_over.model_dump(mode="json", by_alias=True) if game_over is not None else None
    )

    async def _hook() -> None:
        await pubsub.publish_game(game.id, {
            "version": version,
            "dep": dep_data,
            "game_over": game_over_data,
        })

    after_commit(db, _hook)


async def _guard_action(
    db: AsyncSession,
    user_id: int,
    game_id: uuid.UUID,
    expected_version: int | None,
    now: datetime,
) -> tuple[Game, str]:
    game = await lock_game(db, game_id)
    color = color_of(game, user_id)
    if expected_version is not None and expected_version != game.version:
        raise _VERSION_CONFLICT
    if game.status != "active":
        raise _NOT_ACTIVE
    if is_expired(game, now):
        raise _TIME_EXPIRED
    return game, color


async def create_game(
    db: AsyncSession, user_a_id: int, user_b_id: int, time_control: str, now: datetime
) -> Game:
    time_controls = await get_setting(db, "time_controls")
    if time_control not in time_controls:
        raise AppError(400, "INVALID_TIME_CONTROL", "Недопустимый контроль времени")
    if get_rng().random() < 0.5:
        white_id, black_id = user_a_id, user_b_id
    else:
        white_id, black_id = user_b_id, user_a_id
    users = {
        user.id: user
        for user in (
            await db.scalars(select(User).where(User.id.in_([white_id, black_id])))
        ).all()
    }
    base_ms, inc_ms = parse_time_control(time_control)
    abort_first_move_s = int(await get_setting(db, "abort_first_move_s"))
    start_board = chess.Board()
    game = Game(
        id=uuid.uuid4(),
        status="active",
        time_control=time_control,
        base_ms=base_ms,
        inc_ms=inc_ms,
        white_id=white_id,
        black_id=black_id,
        fen=start_board.fen(),
        ply=0,
        repetition={position_key(start_board): 1},
        white_ms=base_ms,
        black_ms=base_ms,
        turn_started_at=now,
        clock_running=False,
        abort_deadline=now + timedelta(seconds=abort_first_move_s),
        white_elo_before=users[white_id].elo,
        black_elo_before=users[black_id].elo,
        version=0,
    )
    db.add(game)
    await db.flush()
    db.add(ActivePlayer(user_id=white_id, game_id=game.id))
    db.add(ActivePlayer(user_id=black_id, game_id=game.id))
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        raise _ALREADY_IN_GAME from exc
    schedule_deadline(db, game)
    return game


async def do_move(
    db: AsyncSession,
    user: User,
    game_id: uuid.UUID,
    uci: str,
    expected_version: int | None,
    now: datetime,
) -> Game:
    game, color = await _guard_action(db, user.id, game_id, expected_version, now)
    if turn_color(game) != color:
        raise _NOT_YOUR_TURN
    board = chess.Board(game.fen)
    try:
        result = apply_move(board, uci)
    except EngineError as exc:
        raise _ENGINE_MOVE_ERROR from exc
    if game.clock_running:
        left = remaining_ms(game, color, now) + game.inc_ms
        if color == "white":
            game.white_ms = left
        else:
            game.black_ms = left
    game.turn_started_at = now
    new_ply = game.ply + 1
    if new_ply == 1:
        abort_first_move_s = int(await get_setting(db, "abort_first_move_s"))
        game.abort_deadline = now + timedelta(seconds=abort_first_move_s)
    elif new_ply == 2:
        game.clock_running = True
        game.abort_deadline = None
    game.ply = new_ply
    game.fen = result.board.fen()
    game.dep_used_this_turn = False
    if game.draw_offer_by is not None and game.draw_offer_by != color:
        game.draw_offer_by = None
    key = position_key(result.board)
    if result.irreversible:
        repetition: dict[str, int] = {key: 1}
    else:
        repetition = dict(game.repetition or {})
        repetition[key] = repetition.get(key, 0) + 1
    game.repetition = repetition
    bump(game)
    add_event(db, game, actor=color, kind="move", payload={"uci": result.uci, "san": result.san})
    outcome = game_outcome(result.board, repetition[key])
    game_over = None
    if outcome is not None:
        game_over = await finish_game(db, game, outcome.result, outcome.end_reason, now)
        bump(game)
        add_event(
            db,
            game,
            actor="system",
            kind="game_over",
            payload={"result": outcome.result, "end_reason": outcome.end_reason},
        )
    schedule_deadline(db, game)
    publish(db, game, game_over=game_over)
    return game


async def do_dep(
    db: AsyncSession,
    user: User,
    game_id: uuid.UUID,
    square: str,
    target: str,
    expected_version: int | None,
    now: datetime,
) -> tuple[Game, DepResolution, int]:
    game, color = await _guard_action(db, user.id, game_id, expected_version, now)
    if turn_color(game) != color:
        raise _NOT_YOUR_TURN
    if game.dep_used_this_turn:
        raise AppError(400, "DEP_ALREADY_USED_THIS_TURN", "В этом ходу деп уже сделан")
    used = game.white_deps if color == "white" else game.black_deps
    if used >= DEP_LIMIT_PER_GAME:
        raise AppError(400, "DEP_LIMIT_REACHED", "Лимит депов в партии исчерпан")
    board = chess.Board(game.fen)
    try:
        validate_dep(board, square, target)
    except EngineError as exc:
        raise AppError(
            400,
            exc.code,
            _DEP_ENGINE_MESSAGES.get(exc.code, "Некорректный деп"),
        ) from exc
    roll_value = get_rng().random()
    multiplier = float(await get_setting(db, "dep_multiplier"))
    resolution = resolve_dep(board, square, target, roll_value, multiplier)
    fen_before = game.fen
    roll_id = await record_roll(
        db,
        user_id=user.id,
        kind="dep",
        ref=str(game.id),
        chance=resolution.chance,
        roll_value=resolution.roll_value,
        input={
            "square": square,
            "from": resolution.from_piece,
            "to": resolution.to_piece,
            "fen_before": fen_before,
        },
        outcome={"success": resolution.success, "fen_after": resolution.board.fen()},
    )
    game.fen = resolution.board.fen()
    game.dep_used_this_turn = True
    if color == "white":
        game.white_deps += 1
    else:
        game.black_deps += 1
    game.repetition = {position_key(resolution.board): 1}
    bump(game)
    add_event(
        db,
        game,
        actor=color,
        kind="dep",
        payload={
            "square": resolution.square,
            "from": resolution.from_piece,
            "to": resolution.to_piece,
            "chance": resolution.chance,
            "success": resolution.success,
            "roll_id": roll_id,
        },
    )
    outcome = game_outcome(resolution.board, 1)
    game_over = None
    if outcome is not None:
        game_over = await finish_game(db, game, outcome.result, outcome.end_reason, now)
        bump(game)
        add_event(
            db,
            game,
            actor="system",
            kind="game_over",
            payload={"result": outcome.result, "end_reason": outcome.end_reason},
        )
    schedule_deadline(db, game)
    dep_event = DepEvent(
        by=color,
        square=resolution.square,
        from_=resolution.from_piece,
        to=resolution.to_piece,
        success=resolution.success,
        chance=resolution.chance,
        roll_value=resolution.roll_value,
    )
    publish(db, game, dep=dep_event, game_over=game_over)
    return game, resolution, roll_id


async def do_resign(
    db: AsyncSession, user: User, game_id: uuid.UUID, expected_version: int | None, now: datetime
) -> Game:
    game, color = await _guard_action(db, user.id, game_id, expected_version, now)
    opponent = "black" if color == "white" else "white"
    bump(game)
    add_event(db, game, actor=color, kind="resign", payload={})
    game_over = await finish_game(db, game, opponent, "resign", now)
    bump(game)
    add_event(
        db,
        game,
        actor="system",
        kind="game_over",
        payload={"result": opponent, "end_reason": "resign"},
    )
    schedule_deadline(db, game)
    publish(db, game, game_over=game_over)
    return game


async def do_draw_offer(
    db: AsyncSession, user: User, game_id: uuid.UUID, expected_version: int | None, now: datetime
) -> Game:
    game, color = await _guard_action(db, user.id, game_id, expected_version, now)
    last_ply = game.white_last_offer_ply if color == "white" else game.black_last_offer_ply
    if game.draw_offer_by is not None or (
        last_ply is not None and game.ply < last_ply + 2
    ):
        raise AppError(400, "DRAW_OFFER_NOT_ALLOWED", "Сейчас нельзя предложить ничью")
    game.draw_offer_by = color
    if color == "white":
        game.white_last_offer_ply = game.ply
    else:
        game.black_last_offer_ply = game.ply
    bump(game)
    add_event(db, game, actor=color, kind="draw_offer", payload={})
    schedule_deadline(db, game)
    publish(db, game)
    return game


async def do_draw_accept(
    db: AsyncSession, user: User, game_id: uuid.UUID, expected_version: int | None, now: datetime
) -> Game:
    game, color = await _guard_action(db, user.id, game_id, expected_version, now)
    if game.draw_offer_by is None or game.draw_offer_by == color:
        raise AppError(400, "NO_DRAW_OFFER", "Встречного предложения ничьей нет")
    bump(game)
    add_event(db, game, actor=color, kind="draw_accept", payload={})
    game_over = await finish_game(db, game, "draw", "agreement", now)
    bump(game)
    add_event(
        db,
        game,
        actor="system",
        kind="game_over",
        payload={"result": "draw", "end_reason": "agreement"},
    )
    schedule_deadline(db, game)
    publish(db, game, game_over=game_over)
    return game


async def do_draw_decline(
    db: AsyncSession, user: User, game_id: uuid.UUID, expected_version: int | None, now: datetime
) -> Game:
    game, color = await _guard_action(db, user.id, game_id, expected_version, now)
    if game.draw_offer_by is None or game.draw_offer_by == color:
        raise AppError(400, "NO_DRAW_OFFER", "Встречного предложения ничьей нет")
    game.draw_offer_by = None
    bump(game)
    add_event(db, game, actor=color, kind="draw_decline", payload={})
    schedule_deadline(db, game)
    publish(db, game)
    return game


async def do_abort(
    db: AsyncSession, user: User, game_id: uuid.UUID, expected_version: int | None, now: datetime
) -> Game:
    game, color = await _guard_action(db, user.id, game_id, expected_version, now)
    if game.ply >= 2:
        raise AppError(400, "ABORT_NOT_ALLOWED", "Абортировать можно до первых ходов")
    bump(game)
    add_event(db, game, actor=color, kind="abort", payload={})
    game_over = await finish_game(db, game, None, "abort", now, aborted=True)
    schedule_deadline(db, game)
    publish(db, game, game_over=game_over)
    return game


async def check_timeout(db: AsyncSession, game: Game, now: datetime) -> bool:
    if game.status != "active" or not is_expired(game, now):
        return False
    if not game.clock_running:
        # Истёк abort_deadline: аннулирование.
        game_over = await finish_game(db, game, None, "abort_no_first_move", now, aborted=True)
        bump(game)
        add_event(
            db,
            game,
            actor="system",
            kind="abort",
            payload={"end_reason": "abort_no_first_move"},
        )
    else:
        turn = turn_color(game)
        if turn == "white":
            game.white_ms = 0
        else:
            game.black_ms = 0
        opponent = "black" if turn == "white" else "white"
        board = chess.Board(game.fen)
        if can_win_on_time(board, opponent):
            result, reason = opponent, "timeout"
        else:
            result, reason = "draw", "timeout_vs_insufficient"
        game_over = await finish_game(db, game, result, reason, now)
        bump(game)
        add_event(
            db,
            game,
            actor="system",
            kind="flag",
            payload={"result": result, "end_reason": reason},
        )
    schedule_deadline(db, game)
    publish(db, game, game_over=game_over)
    return True


async def finish_game(
    db: AsyncSession,
    game: Game,
    result: str | None,
    end_reason: str,
    now: datetime,
    aborted: bool = False,
) -> GameOver:
    if game.clock_running:
        turn = turn_color(game)
        left = remaining_ms(game, turn, now)
        if turn == "white":
            game.white_ms = left
        else:
            game.black_ms = left
    game.clock_running = False
    game.status = "aborted" if aborted else "finished"
    game.result = result
    game.end_reason = end_reason
    game.finished_at = now
    game.draw_offer_by = None
    await db.execute(delete(ActivePlayer).where(ActivePlayer.game_id == game.id))
    if aborted:
        return GameOver(
            result=None, end_reason=end_reason, elo_delta=None, rewards=Rewards(white=0, black=0)
        )
    users: dict[int, User] = {}
    for user_id in sorted((game.white_id, game.black_id)):
        users[user_id] = await lock_user(db, user_id)
    white = users[game.white_id]
    black = users[game.black_id]
    score_white = 1.0 if result == "white" else 0.5 if result == "draw" else 0.0
    new_white, new_black = elo_update(game.white_elo_before, game.black_elo_before, score_white)
    game.white_elo_after = new_white
    game.black_elo_after = new_black
    white.elo = new_white
    black.elo = new_black
    rewards = {"white": 0, "black": 0}
    if game.ply >= int(await get_setting(db, "reward_min_plies")):
        win_reward = int(await get_setting(db, "game_win_reward"))
        draw_reward = int(await get_setting(db, "game_draw_reward"))
        per_day = int(await get_setting(db, "reward_games_per_day"))
        midnight = datetime(now.year, now.month, now.day, tzinfo=UTC)
        for user_id in sorted((game.white_id, game.black_id)):
            color = "white" if user_id == game.white_id else "black"
            if result == "draw":
                delta, reason = draw_reward, "game_draw"
            elif user_id == (game.white_id if result == "white" else game.black_id):
                delta, reason = win_reward, "game_win"
            else:
                continue
            granted = await db.scalar(
                select(func.count())
                .select_from(Ledger)
                .where(
                    Ledger.user_id == user_id,
                    Ledger.reason.in_(("game_win", "game_draw")),
                    Ledger.created_at >= midnight,
                )
            )
            if (granted or 0) >= per_day:
                continue
            await apply_delta(db, user_id, delta, reason, ref=str(game.id))
            rewards[color] = delta
    game.white_reward = rewards["white"]
    game.black_reward = rewards["black"]
    return GameOver(
        result=result,
        end_reason=end_reason,
        elo_delta=EloDelta(white=new_white - game.white_elo_before,
                           black=new_black - game.black_elo_before),
        rewards=Rewards(white=rewards["white"], black=rewards["black"]),
    )
