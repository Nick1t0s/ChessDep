import uuid
from typing import Annotated, Literal

import app.core.clock as clock
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.core.errors import AppError
from app.db import get_db
from app.models import (
    ActivePlayer,
    AdminAudit,
    Game,
    GameEvent,
    InventoryItem,
    Ledger,
    MarketListing,
    Roll,
    Setting,
    User,
)
from app.schemas.admin import (
    AdminLedgerItemOut,
    AdminListingOut,
    AdminUserDetailOut,
    AdminUserOut,
    AdminUsersOut,
    AuditOut,
    BalanceIn,
    BanIn,
    CancelIn,
    GameEventOut,
    RollOut,
    SettingOut,
    SettingPutIn,
)
from app.services import admin_users as admin_service
from app.services.settings import DEFAULTS

router = APIRouter(prefix="/api/v1/admin", tags=["admin-users"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_admin)]

_USER_NOT_FOUND = AppError(404, "USER_NOT_FOUND", "Пользователь не найден")
_GAME_NOT_FOUND = AppError(404, "GAME_NOT_FOUND", "Партия не найдена")


def _user_out(user: User, active_game_id: str | None) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        login=user.login,
        email=user.email,
        role=user.role,
        is_banned=user.is_banned,
        balance=user.balance,
        elo=user.elo,
        created_at=user.created_at,
        active_game_id=active_game_id,
    )


async def _active_game_ids(
    db: AsyncSession, user_ids: list[int]
) -> dict[int, uuid.UUID]:
    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(ActivePlayer.user_id, ActivePlayer.game_id).where(
                ActivePlayer.user_id.in_(user_ids)
            )
        )
    ).all()
    return {row[0]: row[1] for row in rows}


@router.get("/users", response_model=AdminUsersOut)
async def list_users(
    admin: AdminDep,
    db: DbDep,
    q: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> AdminUsersOut:
    filters = []
    if q:
        pattern = f"%{q}%"
        filters.append(or_(User.login.ilike(pattern), User.email.ilike(pattern)))
    count_query = select(func.count()).select_from(User)
    for f in filters:
        count_query = count_query.where(f)
    total = await db.scalar(count_query) or 0
    rows = (
        await db.execute(
            select(User).where(*filters).order_by(User.id).offset((page - 1) * limit).limit(limit)
        )
    ).scalars()
    users = list(rows)
    games = await _active_game_ids(db, [u.id for u in users])
    return AdminUsersOut(
        items=[
            _user_out(u, str(games[u.id]) if u.id in games else None)
            for u in users
        ],
        total=total,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetailOut)
async def get_user(user_id: int, admin: AdminDep, db: DbDep) -> AdminUserDetailOut:
    user = await db.get(User, user_id)
    if user is None:
        raise _USER_NOT_FOUND
    games = await _active_game_ids(db, [user.id])
    items_owned = await db.scalar(
        select(func.count())
        .select_from(InventoryItem)
        .where(InventoryItem.user_id == user_id, InventoryItem.status == "owned")
    )
    active_listings = await db.scalar(
        select(func.count())
        .select_from(MarketListing)
        .where(MarketListing.seller_id == user_id, MarketListing.status == "active")
    )
    ledger_rows = (
        await db.scalars(
            select(Ledger)
            .where(Ledger.user_id == user_id)
            .order_by(Ledger.id.desc())
            .limit(20)
        )
    ).all()
    return AdminUserDetailOut(
        **_user_out(user, str(games[user.id]) if user.id in games else None).model_dump(),
        items_owned=items_owned or 0,
        active_listings=active_listings or 0,
        ledger=[
            AdminLedgerItemOut(
                id=row.id,
                delta=row.delta,
                balance_after=row.balance_after,
                reason=row.reason,
                ref=row.ref,
                actor_id=row.actor_id,
                created_at=row.created_at,
            )
            for row in ledger_rows
        ],
    )


@router.post("/users/{user_id}/ban")
async def ban_user(user_id: int, body: BanIn, admin: AdminDep, db: DbDep) -> dict:
    user = await admin_service.ban_user(db, admin, user_id, body.reason, clock.now())
    return _user_out(user, None).model_dump()


@router.post("/users/{user_id}/unban")
async def unban_user(user_id: int, admin: AdminDep, db: DbDep) -> dict:
    user = await admin_service.unban_user(db, admin, user_id, clock.now())
    return _user_out(user, None).model_dump()


@router.post("/users/{user_id}/balance")
async def adjust_balance(
    user_id: int, body: BalanceIn, admin: AdminDep, db: DbDep
) -> dict:
    balance = await admin_service.adjust_balance(
        db, admin, user_id, body.delta, body.comment
    )
    return {"balance": balance}


@router.get("/settings", response_model=list[SettingOut])
async def list_settings(admin: AdminDep, db: DbDep) -> list[SettingOut]:
    rows = {
        row.key: row for row in (await db.scalars(select(Setting))).all()
    }
    return [
        SettingOut(
            key=key,
            value=(rows[key].value if key in rows else DEFAULTS[key]),
            default=DEFAULTS[key],
            updated_at=(rows[key].updated_at if key in rows else None),
            updated_by=(rows[key].updated_by if key in rows else None),
        )
        for key in DEFAULTS
    ]


@router.put("/settings/{key}", response_model=SettingOut)
async def put_setting(
    key: str, body: SettingPutIn, admin: AdminDep, db: DbDep
) -> SettingOut:
    now = clock.now()
    normalized = await admin_service.set_setting(db, admin, key, body.value, now)
    return SettingOut(
        key=key,
        value=normalized,
        default=DEFAULTS[key],
        updated_at=now,
        updated_by=admin.id,
    )


@router.get("/rolls")
async def list_rolls(
    admin: AdminDep,
    db: DbDep,
    user_id: int | None = None,
    kind: Literal["dep", "case_open", "upgrade"] | None = None,
    before_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    query = select(Roll).order_by(Roll.id.desc())
    if user_id is not None:
        query = query.where(Roll.user_id == user_id)
    if kind is not None:
        query = query.where(Roll.kind == kind)
    if before_id is not None:
        query = query.where(Roll.id < before_id)
    rows = list((await db.scalars(query.limit(limit))).all())
    items = [
        RollOut(
            id=row.id,
            user_id=row.user_id,
            kind=row.kind,
            ref=row.ref,
            chance=row.chance,
            roll_value=row.roll_value,
            input=row.input,
            outcome=row.outcome,
            created_at=row.created_at,
        ).model_dump(mode="json", by_alias=True)
        for row in rows
    ]
    return {
        "items": items,
        "next_cursor": rows[-1].id if len(rows) == limit else None,
    }


@router.get("/games/{game_id}/events", response_model=list[GameEventOut])
async def list_game_events(game_id: uuid.UUID, admin: AdminDep, db: DbDep) -> list[GameEventOut]:
    game = await db.get(Game, game_id)
    if game is None:
        raise _GAME_NOT_FOUND
    rows = (
        await db.scalars(
            select(GameEvent).where(GameEvent.game_id == game_id).order_by(GameEvent.seq)
        )
    ).all()
    return [
        GameEventOut(
            id=row.id,
            game_id=str(row.game_id),
            seq=row.seq,
            ply=row.ply,
            actor=row.actor,
            kind=row.kind,
            payload=row.payload,
            fen_after=row.fen_after,
            white_ms=row.white_ms,
            black_ms=row.black_ms,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/market")
async def list_market(
    admin: AdminDep,
    db: DbDep,
    status: Literal["active", "sold", "cancelled"] | None = None,
    seller_id: int | None = None,
    before_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    query = select(MarketListing).order_by(MarketListing.id.desc())
    if status is not None:
        query = query.where(MarketListing.status == status)
    if seller_id is not None:
        query = query.where(MarketListing.seller_id == seller_id)
    if before_id is not None:
        query = query.where(MarketListing.id < before_id)
    rows = list((await db.scalars(query.limit(limit))).all())
    return {
        "items": [
            AdminListingOut(
                id=row.id,
                item_id=row.item_id,
                item_def_id=row.item_def_id,
                seller_id=row.seller_id,
                price=row.price,
                status=row.status,
                buyer_id=row.buyer_id,
                fee=row.fee,
                created_at=row.created_at,
                closed_at=row.closed_at,
            ).model_dump(mode="json")
            for row in rows
        ],
        "next_cursor": rows[-1].id if len(rows) == limit else None,
    }


@router.post("/market/listings/{listing_id}/cancel")
async def cancel_listing(
    listing_id: int, body: CancelIn, admin: AdminDep, db: DbDep
) -> dict:
    listing = await admin_service.cancel_listing_by_admin(
        db, admin, listing_id, body.reason
    )
    return {
        "id": listing.id,
        "status": listing.status,
        "closed_at": listing.closed_at.isoformat() if listing.closed_at else None,
    }


@router.get("/audit")
async def list_audit(
    admin: AdminDep,
    db: DbDep,
    before_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    query = select(AdminAudit, User.login).outerjoin(User, User.id == AdminAudit.admin_id)
    if before_id is not None:
        query = query.where(AdminAudit.id < before_id)
    rows = list(
        (
            await db.execute(query.order_by(AdminAudit.id.desc()).limit(limit))
        ).all()
    )
    items = [
        AuditOut(
            id=audit.id,
            admin_id=audit.admin_id,
            admin_login=login,
            action=audit.action,
            target=audit.target,
            payload=audit.payload,
            created_at=audit.created_at,
        ).model_dump(mode="json")
        for audit, login in rows
    ]
    return {
        "items": items,
        "next_cursor": rows[-1][0].id if len(rows) == limit else None,
    }
