from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Ledger, User

_INSUFFICIENT_FUNDS = AppError(400, "INSUFFICIENT_FUNDS", "Недостаточно ◈")


async def lock_user(db: AsyncSession, user_id: int) -> User:
    # Любой FOR UPDATE по сущности, которая могла быть загружена раньше в этой
    # сессии, — только с populate_existing=True, иначе SQLAlchemy вернёт объект
    # из identity map со старыми атрибутами.
    user = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise KeyError(user_id)
    return user


async def apply_delta(
    db: AsyncSession,
    user_id: int,
    delta: int,
    reason: str,
    ref: str | None = None,
    actor_id: int | None = None,
) -> int:
    user = await lock_user(db, user_id)
    new_balance = user.balance + delta
    if new_balance < 0:
        raise _INSUFFICIENT_FUNDS
    user.balance = new_balance
    db.add(
        Ledger(
            user_id=user_id,
            delta=delta,
            balance_after=new_balance,
            reason=reason,
            ref=ref,
            actor_id=actor_id,
        )
    )
    return new_balance
