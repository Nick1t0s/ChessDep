# T3. API уведомлений о продажах на маркете + миграция 0010 (бэкенд)

Worktree: /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t3

## 1. `backend/app/models/market.py`, класс `MarketListing`
После поля `closed_at` добавить:
```python
    # False — продавец ещё не видел уведомление о продаже (GET /me/sales/unseen).
    seller_seen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
```

## 2. Новый файл `backend/alembic/versions/0010_sale_notices.py`
Образец оформления — `0009_exterior_images.py`.
```python
"""sale notices: market_listings.seller_seen; empty loadout slots get base skins

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-24

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Пустые слоты экипировки получают базовый скин владельца (теперь слот не пустеет сам).
_FILL_SLOTS = """
INSERT INTO loadouts (user_id, slot, inventory_item_id)
SELECT ii.user_id,
       CASE WHEN d.kind = 'board' THEN 'board' ELSE d.side || d.piece_type END,
       ii.id
FROM inventory_items ii
JOIN item_defs d ON d.id = ii.item_def_id
WHERE ii.source = 'base' AND ii.status = 'owned'
ON CONFLICT DO NOTHING
"""


def upgrade() -> None:
    op.add_column(
        "market_listings",
        sa.Column("seller_seen", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.execute(_FILL_SLOTS)


def downgrade() -> None:
    # Надетые базовые скины не снимаем: это валидная экипировка.
    op.drop_column("market_listings", "seller_seen")
```

## 3. `backend/app/schemas/market.py` — добавить в конец файла
```python
class SaleNoticeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: int
    name: str
    price: int
    payout: int
    buyer_login: str
    closed_at: datetime


class SalesUnseenOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sales: list[SaleNoticeOut]
    balance: int
```

## 4. `backend/app/services/market.py`
- В функции `buy_listing` сразу после строки `listing.closed_at = now` добавить строку `listing.seller_seen = False`.
- В импорт `from sqlalchemy import func, select` добавить `update`: `from sqlalchemy import func, select, update`. Добавить строку `from sqlalchemy.orm import aliased` после него.
- В конец файла добавить:
```python
async def take_unseen_sales(db: AsyncSession, user: User) -> list[dict]:
    """Проданные лоты продавца, о которых он ещё не знает; помечает их увиденными."""
    ids = list(
        await db.scalars(
            update(MarketListing)
            .where(
                MarketListing.seller_id == user.id,
                MarketListing.status == "sold",
                MarketListing.seller_seen.is_(False),
            )
            .values(seller_seen=True)
            .returning(MarketListing.id)
            .execution_options(synchronize_session=False)
        )
    )
    if not ids:
        return []
    buyer = aliased(User)
    rows = await db.execute(
        select(MarketListing, ItemDef.name, Case.name, buyer.login)
        .outerjoin(ItemDef, ItemDef.id == MarketListing.item_def_id)
        .outerjoin(Case, Case.id == MarketListing.case_id)
        .join(buyer, buyer.id == MarketListing.buyer_id)
        .where(MarketListing.id.in_(ids))
        .order_by(MarketListing.closed_at, MarketListing.id)
    )
    return [
        {
            "listing_id": listing.id,
            "name": def_name if def_name is not None else case_name,
            "price": listing.price,
            "payout": listing.price - (listing.fee or 0),
            "buyer_login": buyer_login,
            "closed_at": listing.closed_at,
        }
        for listing, def_name, case_name, buyer_login in rows
    ]
```

## 5. `backend/app/api/market.py`
- В импорт из `app.schemas.market` добавить `SaleNoticeOut, SalesUnseenOut`.
- Сразу после функции эндпоинта `@router.get("/me/listings", ...)` добавить:
```python
@router.get("/me/sales/unseen", response_model=SalesUnseenOut)
async def sales_unseen(user: UserDep, db: DbDep) -> SalesUnseenOut:
    sales = await market_service.take_unseen_sales(db, user)
    return SalesUnseenOut(sales=[SaleNoticeOut(**s) for s in sales], balance=user.balance)
```

## 6. Новый файл `backend/tests/test_sales_notify.py`
Образец — `backend/tests/test_market.py` (как выставлять и покупать, `set_balance`, `give_items`).
```python
from tests.conftest import give_items, set_balance


async def test_sale_notice_once(alice, bob) -> None:
    ids = await give_items("alice", ["genesis-wp"])
    resp = await alice.post("/api/v1/market/listings", json={"item_id": ids[0], "price": 1000})
    assert resp.status_code == 201, resp.text
    listing_id = resp.json()["id"]
    await set_balance("bob", 5000)
    resp = await bob.post(f"/api/v1/market/listings/{listing_id}/buy")
    assert resp.status_code == 200, resp.text

    resp = await alice.get("/api/v1/me/sales/unseen")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["sales"]) == 1
    sale = body["sales"][0]
    assert sale["listing_id"] == listing_id
    assert sale["price"] == 1000
    assert sale["payout"] == 950
    assert sale["buyer_login"] == "bob"
    assert sale["name"]
    me = (await alice.get("/api/v1/me")).json()
    assert body["balance"] == me["balance"]

    again = (await alice.get("/api/v1/me/sales/unseen")).json()
    assert again["sales"] == []
    assert (await bob.get("/api/v1/me/sales/unseen")).json()["sales"] == []


async def test_cancelled_listing_no_notice(alice) -> None:
    ids = await give_items("alice", ["genesis-wp"])
    resp = await alice.post("/api/v1/market/listings", json={"item_id": ids[0], "price": 1000})
    listing_id = resp.json()["id"]
    resp = await alice.delete(f"/api/v1/market/listings/{listing_id}")
    assert resp.status_code in (200, 204), resp.text
    assert (await alice.get("/api/v1/me/sales/unseen")).json()["sales"] == []
```
Если код ответа покупки в test_market.py другой (не 200) — используй тот, что там. Комиссия по умолчанию 0.05 → payout 950.

## Проверка
`cd /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t3 && bash scripts/test_isolated.sh tests/test_sales_notify.py tests/test_market.py` — всё зелёное (миграция прогоняется скриптом сама).
