# Цель
Маркет v3: лоты кейсов-предметов, запрет базовых предметов, новые фильтры и страница кейса.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 5 «Маркет», 6.1 маркет, 6.3 `/market`), `backend/app/services/market.py`, `backend/app/api/market.py`, `backend/app/schemas/market.py` (уже v3: `ListingItemOut` с `kind/def/case`, `CaseMarketOut`), `backend/app/api/admin.py` (~стр. 270–310, `AdminListingOut`), `backend/app/schemas/admin.py` (`AdminListingOut`).

# Область
`backend/app/services/market.py`, `backend/app/api/market.py`, `backend/app/api/admin.py` (только функция списка лотов маркета), `backend/app/schemas/admin.py` (только `AdminListingOut`).

# Что сделать
- `create_listing`: после блокировки предмета — `check_transferable(item)` (из `app.services.items`); лот: `item_def_id=item.item_def_id`, `case_id=item.case_id`.
- `_out_listings`: `ListingItemOut(id=..., kind=out.kind, item_def=out.item_def, case=out.case, wear=out.wear, exterior=out.exterior)`.
- `_apply_filters(..., kind, set_code, collection, side, piece_type, rarity, def_id, case_id)`: `outerjoin(ItemDef, ItemDef.id == MarketListing.item_def_id)`, `outerjoin(Collection, Collection.id == ItemDef.collection_id)`, `outerjoin(ItemSet, ItemSet.id == ItemDef.set_id)`; `kind == "case"` → `MarketListing.case_id.is_not(None)`; `piece`/`board` → `ItemDef.kind == kind`; `set_code` → `ItemSet.code == set_code`; `case_id` → `MarketListing.case_id == case_id`; остальные — как сейчас.
- `load_listing_def(db, def_id) -> tuple[ItemDef, ItemSet, Collection | None]`; `def_market` — `item_def_out(item_def, item_set, collection)`.
- Новая `case_market(db, case_id: int, viewer_id: int | None) -> CaseMarketOut` — копия логики `def_market` с фильтром `MarketListing.case_id == case_id`; кейса нет или `draft` → `AppError(404, "CASE_NOT_FOUND", "Кейс не найден")`; `case=case_ref_out(case)`.
- `api/market.py`: в `GET /market` параметры `kind: Literal["piece", "board", "case"] | None`, `set: str | None` (передавать как `set_code`), `case_id: int | None`; новый `GET /market/cases/{case_id}` → `CaseMarketOut` (авторизация — как у `/market/defs/{def_id}`).
- `schemas/admin.py` `AdminListingOut`: `item_def_id: int | None`, добавить `case_id: int | None` после него; `api/admin.py`: передавать `case_id=row.case_id`.

# Готово, когда
`python3 -m py_compile backend/app/services/market.py backend/app/api/market.py backend/app/api/admin.py backend/app/schemas/admin.py` без ошибок.

# Общие хелперы этой волны (пишутся параллельно — используй ровно эти сигнатуры)
`app.services.items`:
- `ITEM_BOUND = AppError(400, "ITEM_BOUND", "Базовый предмет нельзя передать или апгрейдить")`, `ITEM_NOT_UPGRADABLE = AppError(400, "ITEM_NOT_UPGRADABLE", "Кейс нельзя апгрейдить")`, `LOADOUT_INCOMPLETE = AppError(400, "LOADOUT_INCOMPLETE", "Экипируйте скины на все фигуры и доску")`.
- `item_def_out(d: ItemDef, item_set: ItemSet, collection: Collection | None) -> ItemDefOut`
- `case_ref_out(case: Case) -> CaseRefOut`
- `async defs_out(db, def_ids: Iterable[int]) -> dict[int, ItemDefOut]` — пакетно (≤ 3 запроса).
- `async items_out(db, items: list[InventoryItem]) -> list[ItemOut]`, `async item_out(db, item) -> ItemOut` — для скинов и кейсов.
- `async create_item(db, *, user_id, def_id, source, source_ref, now) -> InventoryItem` — скин, `wear = get_rng().random()`.
- `async create_case_item(db, *, user_id: int, case_id: int, source: str, source_ref: str | None, now) -> InventoryItem` — кейс, `wear = None`.
- `async grant_base_items(db, user_id: int, now) -> None` — 13 базовых предметов (`BASE_DEF_IDS`, `source="base"`, `wear=0.0`) и экипировка во все 13 слотов.
- `check_transferable(item: InventoryItem) -> None` — `source == "base"` → `ITEM_BOUND`.
- `async ensure_loadout_complete(db, user_id: int) -> None` — нет хотя бы одного из 13 слотов → `LOADOUT_INCOMPLETE`; `async loadout_complete(db, user_id) -> bool`.
- `async loadout_snapshot(db, user_id: int, side: str) -> dict[str, dict]` — 6 слотов стороны без префикса + `"board"`.
- `slot_matches(item_def: ItemDef | None, slot: str) -> bool`.
- без изменений: `lock_items`, `load_items`, `lock_item_any`, `unequip_items`, `check_trade_hold`.

`app.services.cases`:
- `auto_weights`, `weighted_pick` — без изменений.
- `on_sale_now(case: Case, now: datetime) -> bool`
- `async shop_case_outs(db, cases: list[Case]) -> list[ShopCaseOut]`
- `async case_detail(db, case_id: int, now) -> CaseDetailOut` (нет / `draft` → `404 CASE_NOT_FOUND`)
- `async buy_case(db, user: User, case_id: int, now) -> CaseBuyOut`
- `async open_case_item(db, user: User, item_id: int, now) -> CaseOpenOut`

`app.services.daily_reward`: `async get_status(db, user: User, now) -> DailyRewardOut`, `async claim(db, user: User, now) -> DailyRewardClaimOut`.

Модели (уже в коде): `ItemSet`, `Collection.set_id`, `ItemDef.kind/set_id/collection_id/side/piece_type`, `InventoryItem.item_def_id|case_id|wear` (nullable), `Case.kind/set_id/collection_id/stock_limit/sold_count/sale_starts_at/sale_ends_at/status`, `DailyRewardPool`, `MarketListing.item_def_id|case_id`, `User.last_daily_reward_on`. Схемы — `app/schemas/items.py`, `app/schemas/market.py` (уже в коде). Константы — `app/seed_data.py` (`LOADOUT_SLOTS`, `CANONICAL_SLOTS`, `BASE_DEF_IDS`, `BASE_SET_ID`, `item_code`, `item_name`).

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md` (контракт предметов v3). Имена, поля, коды ошибок, тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()` (`import app.core.clock as clock`). Случайность — только `get_rng()` из `app.services.rolls`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`. Баланс — только `economy.apply_delta`.
- Порядок блокировок: `market_listings` → `inventory_items` → `cases` → `games` → `users`.
- Тесты бэкенда в этой волне НЕ запускаются и могут падать — их чинит отдельная волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
