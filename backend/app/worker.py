import asyncio
import contextlib
import logging
import signal
import time
import uuid
from datetime import datetime

from sqlalchemy import select

from app.core import clock
from app.core.errors import AppError
from app.db import SessionLocal, run_after_commit
from app.models import Game
from app.redis import redis_client
from app.services import matchmaking
from app.services.game_clock import deadline
from app.services.games import check_timeout, lock_game, schedule_deadline

logger = logging.getLogger("app.worker")

DEADLINES_KEY = "clock:deadlines"

_CLOCK_TICK_S = 0.2
_MATCHMAKING_TICK_S = 0.5
_DEADLINE_BATCH = 50


async def rebuild_deadlines() -> None:
    # Восстановление ZSET после потери Redis: для всех активных партий
    # пересчитать дедлайн и ZADD.
    async with SessionLocal() as db:
        rows = (
            await db.scalars(select(Game).where(Game.status == "active"))
        ).all()
    mapping: dict[str, int] = {}
    for game in rows:
        dl = deadline(game)
        if dl is not None:
            mapping[str(game.id)] = clock.to_ms(dl)
    if mapping:
        await redis_client.zadd(DEADLINES_KEY, mapping)


async def _process_deadline(raw_id: str, now: datetime) -> None:
    try:
        game_id = uuid.UUID(raw_id)
    except ValueError:
        await redis_client.zrem(DEADLINES_KEY, raw_id)
        return
    need_remove = False
    async with SessionLocal() as db:
        async with db.begin():
            try:
                game = await lock_game(db, game_id)
            except AppError as exc:
                if exc.code != "GAME_NOT_FOUND":
                    raise
                need_remove = True
            else:
                if game.status != "active":
                    need_remove = True
                elif not await check_timeout(db, game, now):
                    schedule_deadline(db, game)
        await run_after_commit(db)
    if need_remove:
        await redis_client.zrem(DEADLINES_KEY, raw_id)


async def tick_clocks(now: datetime) -> None:
    now_ms = clock.to_ms(now)
    game_ids = await redis_client.zrangebyscore(
        DEADLINES_KEY, "-inf", now_ms, start=0, num=_DEADLINE_BATCH
    )
    for raw_id in game_ids:
        # Сбой одной партии не должен блокировать флаги остальных.
        try:
            await _process_deadline(raw_id, now)
        except Exception:
            logger.exception("deadline processing failed for %s", raw_id)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await rebuild_deadlines()
        last_matchmaking = 0.0
        while not stop.is_set():
            try:
                await tick_clocks(clock.now())
            except Exception:
                logger.exception("tick_clocks failed")
            now_mono = time.monotonic()
            if now_mono - last_matchmaking >= _MATCHMAKING_TICK_S:
                last_matchmaking = now_mono
                try:
                    await matchmaking.tick(clock.now())
                except Exception:
                    logger.exception("matchmaking tick failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=_CLOCK_TICK_S)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):
                loop.remove_signal_handler(sig)


if __name__ == "__main__":
    asyncio.run(main())
