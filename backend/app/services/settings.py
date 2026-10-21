import time
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting

_CACHE_TTL_S = 5.0
_cache: dict[str, tuple[Any, float]] = {}

DEFAULTS: Mapping[str, Any] = {
    "starting_balance": 1000,
    "daily_bonus": 200,
    "daily_bonus_cooldown_h": 24,
    "game_win_reward": 100,
    "game_draw_reward": 30,
    "reward_min_plies": 10,
    "reward_games_per_day": 20,
    "dep_multiplier": 1.0,
    "upgrade_edge": 0.05,
    "upgrade_min_chance": 0.01,
    "upgrade_max_chance": 0.80,
    "upgrade_max_inputs": 10,
    "time_controls": ["3+2", "5+0", "10+0"],
    "abort_first_move_s": 30,
}


async def get_setting(db: AsyncSession, key: str) -> Any:
    if key not in DEFAULTS:
        raise KeyError(key)
    cached = _cache.get(key)
    now = time.monotonic()
    if cached is not None and now - cached[1] < _CACHE_TTL_S:
        return cached[0]
    row = await db.get(Setting, key)
    value = row.value if row is not None else DEFAULTS[key]
    _cache[key] = (value, now)
    return value


def clear_cache() -> None:
    _cache.clear()
