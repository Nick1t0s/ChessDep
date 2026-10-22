import time
from collections.abc import Callable, Mapping
from typing import Annotated, Any

from pydantic import Field, RootModel, StringConstraints, TypeAdapter, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting
from app.services.game_clock import parse_time_control

_CACHE_TTL_S = 5.0
_cache: dict[str, tuple[Any, float]] = {}


def _int_validator(ge: int, le: int) -> Callable[[Any], Any]:
    return TypeAdapter(Annotated[int, Field(ge=ge, le=le)]).validate_python


def _float_validator(gt: float | None, ge: float | None, le: float) -> Callable[[Any], Any]:
    return TypeAdapter(
        Annotated[float, Field(gt=gt, ge=ge, le=le)]
    ).validate_python


_TIME_CONTROL_LIST = Annotated[
    list[Annotated[str, StringConstraints(pattern=r"^\d{1,3}\+\d{1,3}$")]],
    Field(min_length=1, max_length=10),
]


class _TimeControls(RootModel[_TIME_CONTROL_LIST]):
    @model_validator(mode="after")
    def check(self) -> "_TimeControls":
        values = self.root
        if len(set(values)) != len(values):
            raise ValueError("time_controls содержит дубликаты")
        for tc in values:
            try:
                base_ms, _inc = parse_time_control(tc)
            except ValueError as exc:
                raise ValueError(str(exc)) from exc
            if base_ms <= 0:
                raise ValueError(f"База контрола времени должна быть > 0: {tc!r}")
        return values


class _RarityWeights(RootModel[dict[str, Annotated[int, Field(ge=0, le=10_000_000)]]]):
    @model_validator(mode="after")
    def check(self) -> "_RarityWeights":
        if set(self.root.keys()) != set(_RARITIES):
            raise ValueError("rarity_weights должен содержать ровно 6 ключей редкостей")
        if not any(value > 0 for value in self.root.values()):
            raise ValueError("Хотя бы один вес должен быть > 0")
        return self


_RARITIES = ("common", "uncommon", "rare", "epic", "legendary", "mythic")

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
    "rarity_weights": {
        "common": 7992,
        "uncommon": 1598,
        "rare": 320,
        "epic": 64,
        "legendary": 20,
        "mythic": 6,
    },
    "market_fee": 0.05,
    "market_max_listings": 50,
    "trade_hold_hours": 0,
}


def _time_controls_validator() -> Callable[[Any], Any]:
    return TypeAdapter(_TimeControls).validate_python


def _rarity_weights_validator() -> Callable[[Any], Any]:
    return TypeAdapter(_RarityWeights).validate_python


SETTINGS_SCHEMA: dict[str, Callable[[Any], Any]] = {
    "starting_balance": _int_validator(0, 10_000_000),
    "daily_bonus": _int_validator(0, 1_000_000),
    "daily_bonus_cooldown_h": _int_validator(1, 168),
    "game_win_reward": _int_validator(0, 1_000_000),
    "game_draw_reward": _int_validator(0, 1_000_000),
    "reward_min_plies": _int_validator(0, 500),
    "reward_games_per_day": _int_validator(0, 1000),
    "dep_multiplier": _float_validator(gt=0.0, ge=None, le=2.0),
    "upgrade_edge": _float_validator(gt=None, ge=0.0, le=0.5),
    "upgrade_min_chance": _float_validator(gt=None, ge=0.0001, le=1.0),
    "upgrade_max_chance": _float_validator(gt=None, ge=0.0001, le=1.0),
    "upgrade_max_inputs": _int_validator(1, 50),
    "time_controls": _time_controls_validator(),
    "abort_first_move_s": _int_validator(10, 600),
    "rarity_weights": _rarity_weights_validator(),
    "market_fee": _float_validator(gt=None, ge=0.0, le=0.5),
    "market_max_listings": _int_validator(1, 1000),
    "trade_hold_hours": _int_validator(0, 720),
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
