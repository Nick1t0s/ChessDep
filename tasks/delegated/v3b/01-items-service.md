# Цель
`services/items.py` под v3: скины и кейсы в инвентаре, 13 слотов, базовые предметы.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1, 5 «Экипировка», «Снапшот», 6.1 `ItemDefOut`/`ItemOut`/`CaseRefOut`), `backend/app/services/items.py`, `backend/app/models/items.py`, `backend/app/schemas/items.py`.

# Область
Только `backend/app/services/items.py`.

# Что сделать
Реализовать ВСЕ функции `app.services.items` из раздела «Общие хелперы» ниже, точно по сигнатурам.
- `item_def_out`: `set=SetRef(code=item_set.code, name=item_set.name)`, `collection=CollectionRef(...)` или `None`, `kind`, `side`, `piece_type`.
- `defs_out`: запросы `select(ItemDef)` по id, `select(ItemSet)` по set_id, `select(Collection)` по collection_id (если есть).
- `items_out`: сохранить порядок; запросы: defs (через `defs_out`), кейсы `select(Case).where(Case.id.in_(...))` (если есть кейсы), слоты `Loadout`. Для кейса: `kind="case"`, `item_def=None`, `case=case_ref_out(case)`, `wear=None`, `exterior=None`. Для скина: `kind="skin"`, `case=None`, `wear=float(item.wear)`, `exterior=exterior(wear)`. `bound = item.source == "base"`. Поле `ItemOut` с алиасом передавай по имени `item_def=` (как сейчас).
- `item_out(db, item)` = `(await items_out(db, [item]))[0]`.
- `grant_base_items`: для каждого `def_id, slot in zip(BASE_DEF_IDS, LOADOUT_SLOTS)` — `InventoryItem(user_id, item_def_id=def_id, wear=0.0, status="owned", source="base", source_ref=None, created_at=now, acquired_at=now)`; `flush`; затем `Loadout(user_id, slot, inventory_item_id)` для каждого; `flush`. RNG не использовать.
- `loadout_snapshot(db, user_id, side)`: строки лоадаута пользователя со слотами, где `slot.startswith(side)` ИЛИ `slot == "board"`; ключ — `slot[1:]` для фигур и `"board"` для доски; значение `{"code", "name", "rarity", "asset"}`.
- `loadout_complete`: `select(func.count()).select_from(Loadout).where(Loadout.user_id == user_id)` == 13.
- `slot_matches`: `None` → False; `kind == "board"` → `slot == "board"`; иначе `slot == side + piece_type`.

# Готово, когда
`python3 -m py_compile backend/app/services/items.py` без ошибок.

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
