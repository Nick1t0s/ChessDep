import secrets
from decimal import Decimal
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Roll


class Rng(Protocol):
    def random(self) -> float: ...


_rng: Rng = secrets.SystemRandom()


def get_rng() -> Rng:
    return _rng


def set_rng(rng: Rng) -> None:
    # Только для тестов.
    global _rng
    _rng = rng


def reset_rng() -> None:
    # Вернуть SystemRandom.
    global _rng
    _rng = secrets.SystemRandom()


async def record_roll(
    db: AsyncSession,
    *,
    user_id: int,
    kind: str,
    ref: str,
    chance: float | None,
    roll_value: float,
    input: dict,
    outcome: dict,
) -> int:
    roll = Roll(
        user_id=user_id,
        kind=kind,
        ref=ref,
        chance=None if chance is None else Decimal(str(chance)),
        roll_value=roll_value,
        input=input,
        outcome=outcome,
    )
    db.add(roll)
    await db.flush()
    return roll.id
