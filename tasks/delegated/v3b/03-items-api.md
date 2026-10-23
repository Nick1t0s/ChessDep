# Цель
Публичные/игровые эндпоинты предметов v3: наборы, коллекции, магазин, кейсы, покупка, открытие, инвентарь, экипировка.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 5, 6.1, 6.3 «Игрок / публично»), `backend/app/api/items.py` (текущий — стиль, rate limit `hit(f"rl:items:{user.id}", 3, 1)`).

# Область
Только `backend/app/api/items.py`.

# Что сделать (эндпоинты ровно по п. 6.3, без апгрейда — его оставить как есть)
- `GET /sets` → `list[PublicSetOut]`: `ItemSet` со `status IN ('released','retired')` и `is_base = false`, порядок `released_at desc, id`; счётчики коллекций и досок — `group_by`-запросами.
- `GET /sets/{code}` → `SetDetailOut`: нет / `draft` → `AppError(404, "SET_NOT_FOUND", "Набор не найден")`; коллекции по `id`, скины каждой — в порядке `CANONICAL_SLOTS.index(side + piece_type)`; доски (`kind == "board"`) по `id`. Используй `item_def_out`.
- `GET /collections/{code}` → `CollectionDetailOut` (`set` — `SetRef`); коллекция нет или её набор `draft` → `404 COLLECTION_NOT_FOUND`.
- `GET /item-defs?upgrade_target=false`: join `ItemSet`; всегда `ItemSet.is_base == False`; `upgrade_target=true` → `ItemSet.status == "released"`, `ItemDef.is_upgrade_target`, порядок `value, id`; иначе `ItemSet.status != "draft"`, порядок `id`. Коллекцию брать `outerjoin`.
- `GET /shop` → `list[ShopCaseOut]`: `select(Case).where(Case.status == "on_sale").order_by(Case.sort, Case.id)`, затем фильтр `on_sale_now(c, clock.now())` в Python, затем `shop_case_outs`.
- `GET /cases/{case_id}` → `case_detail(db, case_id, clock.now())` (без авторизации).
- `POST /cases/{case_id}/buy` (`current_user`, rate limit) → `buy_case`.
- `POST /inventory/{item_id}/open` (`current_user`, rate limit) → `open_case_item`.
- `GET /inventory?kind=&side=&slot=&sort=`: `kind: Literal["piece", "board", "case"] | None`; база — `InventoryItem` пользователя со статусом `owned`/`listed`, `outerjoin(ItemDef, ItemDef.id == InventoryItem.item_def_id)`; `kind="case"` → `InventoryItem.case_id.is_not(None)`; `piece`/`board` → `ItemDef.kind == kind`; `side` → `ItemDef.side == side`; `slot == "board"` → `ItemDef.kind == "board"`, иначе `ItemDef.side == slot[0], ItemDef.piece_type == slot[1]`. Сортировки прежние; у кейсов `ItemDef` = NULL — `nulls_last()` в `order_by` по редкости/ценности.
- `_loadout_out`: цикл по `LOADOUT_SLOTS`, `LoadoutOut(**out, complete=len(by_slot) == 13)`.
- `PUT /loadout/{slot}`: как сейчас, но `item_def = await db.get(ItemDef, item.item_def_id) if item.item_def_id is not None else None` и `slot_matches(item_def, slot)`.
- Удалить `GET /collections` (список), `GET /cases`, `POST /cases/{case_id}/open`.

# Готово, когда
`python3 -m py_compile backend/app/api/items.py` без ошибок.

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
