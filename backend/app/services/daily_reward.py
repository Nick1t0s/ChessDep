from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Case, DailyRewardPool, Game, User
from app.schemas.items import DailyRewardClaimOut, DailyRewardOut
from app.services.cases import weighted_pick
from app.services.economy import lock_user
from app.services.items import case_ref_out, create_case_item, item_out
from app.services.rolls import get_rng, record_roll
from app.services.settings import get_setting

_DAILY_REWARD_CLAIMED = AppError(
    400, "DAILY_REWARD_CLAIMED", "Награда за сегодня уже получена"
)
_DAILY_REWARD_EMPTY = AppError(400, "DAILY_REWARD_EMPTY", "Пул наград пуст")


def _day_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


async def wins_today(db: AsyncSession, user_id: int, now: datetime) -> int:
    start, end = _day_bounds(now)
    min_plies = int(await get_setting(db, "reward_min_plies"))
    value = await db.scalar(
        select(func.count())
        .select_from(Game)
        .where(
            Game.status == "finished",
            Game.ply >= min_plies,
            Game.finished_at >= start,
            Game.finished_at < end,
            or_(
                and_(Game.white_id == user_id, Game.result == "white"),
                and_(Game.black_id == user_id, Game.result == "black"),
            ),
        )
    )
    return int(value)


async def get_status(db: AsyncSession, user: User, now: datetime) -> DailyRewardOut:
    wins_required = int(await get_setting(db, "daily_reward_wins"))
    wins = await wins_today(db, user.id, now)
    claimed_today = user.last_daily_reward_on == now.date()
    return DailyRewardOut(
        wins_today=wins,
        wins_required=wins_required,
        claimed_today=claimed_today,
        available=not claimed_today and wins >= wins_required,
    )


async def claim(db: AsyncSession, user: User, now: datetime) -> DailyRewardClaimOut:
    wins_required = int(await get_setting(db, "daily_reward_wins"))
    locked = await lock_user(db, user.id)
    if locked.last_daily_reward_on == now.date():
        raise _DAILY_REWARD_CLAIMED
    if await wins_today(db, locked.id, now) < wins_required:
        raise AppError(
            400,
            "DAILY_REWARD_NOT_READY",
            f"Нужно победить в {wins_required} партиях за сегодня",
        )
    pool = list(
        (await db.scalars(select(DailyRewardPool).order_by(DailyRewardPool.case_id))).all()
    )
    if not pool:
        raise _DAILY_REWARD_EMPTY
    r = get_rng().random()
    entry = weighted_pick(pool, r)
    total = sum(p.weight for p in pool)
    item = await create_case_item(
        db,
        user_id=locked.id,
        case_id=entry.case_id,
        source="daily_reward",
        source_ref=None,
        now=now,
    )
    roll_id = await record_roll(
        db,
        user_id=locked.id,
        kind="daily_reward",
        ref=str(entry.case_id),
        chance=entry.weight / total,
        roll_value=r,
        input={"pool": [[p.case_id, p.weight] for p in pool]},
        outcome={"case_id": entry.case_id, "item_id": item.id},
    )
    locked.last_daily_reward_on = now.date()
    case = await db.get(Case, entry.case_id)
    return DailyRewardClaimOut(
        case=case_ref_out(case),
        item=await item_out(db, item),
        roll_id=roll_id,
    )
