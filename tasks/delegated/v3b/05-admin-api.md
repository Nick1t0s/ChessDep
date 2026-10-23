# Цель
Админ-роутер каталога v3.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 6.1 «Админ», 6.2, 6.3 «Админ»), `backend/app/api/admin_catalog.py` (стиль), раздел про `app.services.catalog_admin` в задаче ниже.
Функции сервиса `app.services.catalog_admin` (пишутся параллельно, сигнатуры точные): `create_set(db, admin, body)`, `patch_set(db, admin, set_id, body)`, `delete_set(db, admin, set_id)`, `release_set(db, admin, set_id, now)`, `retire_set(db, admin, set_id, now)`, `create_collection(db, admin, set_id, body) -> Collection`, `patch_collection(db, admin, collection_id, body) -> Collection`, `delete_collection(db, admin, collection_id)`, `create_board(db, admin, set_id, body) -> ItemDef`, `patch_item_def(db, admin, item_def_id, body) -> ItemDef`, `delete_item_def(db, admin, item_def_id)`, `create_case(db, admin, body) -> Case`, `patch_case(db, admin, case_id, body) -> Case`, `delete_case(db, admin, case_id)`, `set_drops(db, admin, case_id, drops)`, `auto_drops(db, admin, case_id, set_ids, collection_ids)`, `publish_case(db, admin, case_id, now)`, `unpublish_case(db, admin, case_id)`, `set_daily_pool(db, admin, entries)`, `grant_item(db, admin, user_id, item_def_id, case_id, now) -> int`.

# Область
Только `backend/app/api/admin_catalog.py`.

# Что сделать
Переписать роутер: все эндпоинты из таблицы «Админ» п. 6.3, ответы — схемы п. 6.1. Удалить эндпоинты, перечисленные в контракте как удалённые.
- Хелперы: `async _set_out(db, s: ItemSet) -> AdminSetOut` (счётчики коллекций и досок), `async _set_detail(db, s) -> AdminSetDetailOut` (коллекции по id, их 12 скинов в порядке `CANONICAL_SLOTS.index(side + piece_type)`, доски по id; через `item_def_out(d, s, collection)`), `async _cases_out(db, cases: list[Case]) -> list[AdminCaseOut]` (пакетно: наборы, коллекции, дропы одним запросом каждое; `on_sale_now=on_sale_now(case, clock.now())`), `_get(db, Model, id, error)`.
- `GET /admin/sets` — все наборы `order_by(id)`.
- `POST /admin/sets/{id}/collections` → 201 `await _set_detail(...)`; `PATCH /admin/collections/{id}` → `_set_detail` набора коллекции; `DELETE` → 204.
- `POST /admin/sets/{id}/boards` → 201 `ItemDefOut`.
- `PATCH /admin/item-defs/{id}` → `ItemDefOut`; `DELETE /admin/item-defs/{id}` → 204.
- `GET /admin/item-defs` — join `ItemSet`, `ItemSet.is_base == False`, `ItemSet.status != "retired"`, outerjoin `Collection`, `order_by(ItemDef.set_id, ItemDef.id)`.
- `GET /admin/cases` — `order_by(Case.sort, Case.id)`.
- `POST /admin/cases/{id}/drops/auto` — тело `AutoDropsIn` обязательно → `auto_drops(db, admin, id, body.set_ids, body.collection_ids)`.
- `GET /admin/daily-reward-pool` → `list[DailyPoolEntryOut]` (join `Case`, порядок `case_id`); `PUT` (тело `DailyPoolIn`) → `set_daily_pool(db, admin, body.root)` → тот же список.
- `POST /admin/users/{id}/grant-item` (тело `GrantItemIn`) → `grant_item(..., body.item_def_id, body.case_id, clock.now())` → `ItemOut` через `items_out`.
- Импорты `item_def_out`, `items_out` — из `app.services.items`; `on_sale_now` — из `app.services.cases`.

# Готово, когда
`python3 -m py_compile backend/app/api/admin_catalog.py` без ошибок.

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
