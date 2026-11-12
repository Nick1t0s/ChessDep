# Цель
Подарки и апгрейд по правилам v3: базовые предметы не передаются, кейсы дарятся, но не апгрейдятся.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1 «Базовый набор», 5 «Маркет и подарки», «Апгрейд»), `backend/app/services/gifts.py`, `backend/app/services/upgrade.py`.

# Область
`backend/app/services/gifts.py`, `backend/app/services/upgrade.py`.

# Что сделать
- `gifts.py`: в `send_gift` после `lock_items` — `check_transferable(item)` (из `app.services.items`); `_item_brief(item_out)` → `ListingItemOut(id=item_out.id, kind=item_out.kind, item_def=item_out.item_def, case=item_out.case, wear=item_out.wear, exterior=item_out.exterior)`.
- `upgrade.py`:
  - после загрузки входов (и в `compute`, и в `execute`): любой вход с `case_id is not None` → `raise ITEM_NOT_UPGRADABLE`; с `source == "base"` → `raise ITEM_BOUND` (оба из `app.services.items`). Делать это ДО подсчёта ценности.
  - проверка цели: вместо коллекции — набор: `item_set = await db.get(ItemSet, target.set_id)`; цель недоступна, если `item_set is None or item_set.status != "released" or item_set.is_base or not target.is_upgrade_target` (тот же код/reason, что сейчас для недоступной цели).
  - всё остальное (шанс, броски, сгорание) не менять.

# Готово, когда
`python3 -m py_compile backend/app/services/gifts.py backend/app/services/upgrade.py` без ошибок.

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
