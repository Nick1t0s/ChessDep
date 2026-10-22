from typing import Annotated, Literal

import app.core.clock as clock
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user, optional_user
from app.core.ratelimit import hit
from app.db import get_db
from app.models import User
from app.schemas.market import BrowseOut, DefMarketOut, ListingCreateIn, ListingOut
from app.services import market as market_service

router = APIRouter(prefix="/api/v1", tags=["market"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
OptionalUserDep = Annotated[User | None, Depends(optional_user)]
UserDep = Annotated[User, Depends(current_user)]


@router.get("/market", response_model=BrowseOut)
async def browse_market(
    db: DbDep,
    viewer: OptionalUserDep,
    collection: str | None = None,
    kind: Literal["piece_skin", "board_skin"] | None = None,
    piece_type: Literal["P", "N", "B", "R", "Q", "K"] | None = None,
    rarity: Literal["common", "uncommon", "rare", "epic", "legendary", "mythic"] | None = None,
    def_id: int | None = None,
    sort: Literal["price_asc", "price_desc", "new"] = "new",
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> BrowseOut:
    viewer_id = viewer.id if viewer is not None else None
    items, total = await market_service.browse(
        db,
        viewer_id,
        collection=collection,
        kind=kind,
        piece_type=piece_type,
        rarity=rarity,
        def_id=def_id,
        sort=sort,
        page=page,
        limit=limit,
    )
    return BrowseOut(items=items, total=total)


@router.get("/market/defs/{def_id}", response_model=DefMarketOut)
async def get_def_market(def_id: int, db: DbDep, viewer: OptionalUserDep) -> DefMarketOut:
    viewer_id = viewer.id if viewer is not None else None
    return await market_service.def_market(db, def_id, viewer_id)


@router.post("/market/listings", response_model=ListingOut, status_code=201)
async def create_listing(body: ListingCreateIn, user: UserDep, db: DbDep) -> ListingOut:
    await hit(f"rl:market:{user.id}", 5, 1)
    listing = await market_service.create_listing(
        db, user, body.item_id, body.price, clock.now()
    )
    return (await market_service._out_listings(db, [(listing, user.login)], user.id))[0]


@router.delete("/market/listings/{listing_id}", response_model=ListingOut)
async def cancel_listing(listing_id: int, user: UserDep, db: DbDep) -> ListingOut:
    await hit(f"rl:market:{user.id}", 5, 1)
    listing = await market_service.cancel_listing(db, user, listing_id, clock.now())
    return (await market_service._out_listings(db, [(listing, user.login)], user.id))[0]


@router.post("/market/listings/{listing_id}/buy", response_model=ListingOut)
async def buy_listing(listing_id: int, user: UserDep, db: DbDep) -> ListingOut:
    listing = await market_service.buy_listing(db, user, listing_id, clock.now())
    seller_login = (
        await db.scalar(select(User.login).where(User.id == listing.seller_id))
    )
    return (await market_service._out_listings(db, [(listing, seller_login)], user.id))[0]


@router.get("/me/listings", response_model=list[ListingOut])
async def my_listings(
    user: UserDep,
    db: DbDep,
    status: Literal["active", "sold", "cancelled"] = "active",
) -> list[ListingOut]:
    return await market_service.my_listings(db, user, status)
