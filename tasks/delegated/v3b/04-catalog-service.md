# Цель
Админ-сервис каталога v3: наборы, коллекции, доски, скины, кейсы (виды, лимиты, публикация), пул ежедневной награды, выдача предметов.

# Контекст
Прочитай: `docs/contracts-collections.md` (весь, особенно п. 5, 6.2, список аудита в конце 6.3), `backend/app/services/catalog_admin.py` (текущий — стиль, `_audit`, `_draft_case`, `_check_available_defs`).

# Область
Только `backend/app/services/catalog_admin.py`.

# Ошибки (константы модуля, тексты дословно)
`SET_NOT_FOUND (404) «Набор не найден»`, `COLLECTION_NOT_FOUND (404)`, `ITEM_DEF_NOT_FOUND (404)`, `CASE_NOT_FOUND (404)`, `USER_NOT_FOUND (404)`, `SET_CODE_TAKEN (409) «Код набора занят»`, `COLLECTION_CODE_TAKEN (409)`, `ITEM_CODE_TAKEN (409)`, `CASE_CODE_TAKEN (409)`, `SET_NOT_DRAFT (400) «Действие только для черновика»`, `SET_NOT_RELEASED (400) «Снять можно только выпущенный»`, `SET_EMPTY (400) «В наборе нет коллекций и досок»`, `SET_IS_BASE (400) «Базовый набор нельзя менять»`, `ITEM_DEF_LOCKED (400) «После выпуска можно менять только name, asset, value, is_upgrade_target»`, `ITEM_DEF_NOT_AVAILABLE (400) «Скин или кейс недоступен для выдачи»`, `ASSET_KIND_MISMATCH = AppError(422, "VALIDATION_ERROR", "asset не соответствует виду скина")`, `CASE_LOCKED (400) «Дропы можно менять только у черновика кейса»`, `CASE_NOT_READY (400) «Кейс не готов: нет дропов, есть невыпущенные наборы или тираж исчерпан»`, `CASE_NOT_ON_SALE (400) «Кейс не в продаже»`, `CASE_NOT_AVAILABLE (400) «Кейс недоступен»`, `DROP_ITEM_NOT_AVAILABLE (400) «Скин недоступен для кейса»`, `STOCK_BELOW_SOLD = AppError(422, "VALIDATION_ERROR", "Тираж меньше уже проданного")`, `SALE_WINDOW_INVALID = AppError(422, "VALIDATION_ERROR", "Начало продаж должно быть раньше конца")`.

# Функции (сигнатуры дословно; `db: AsyncSession`, `admin: User`)
Наборы:
- `create_set(db, admin, body: SetCreateIn) -> ItemSet` — `status="draft"`, `is_base=False`; IntegrityError → `SET_CODE_TAKEN`; аудит `set.create`.
- `patch_set(db, admin, set_id, body: SetPatchIn) -> ItemSet` — `name`, `description`; аудит `set.patch`.
- `delete_set(db, admin, set_id) -> None` — нет → 404; `is_base` → `SET_IS_BASE`; не `draft` → `SET_NOT_DRAFT`; удалить: строки `DailyRewardPool` и `CaseDrop` кейсов с `set_id`/`collection_id` этого набора, сами эти кейсы, `CaseDrop` со скинами набора (в других кейсах), `ItemDef` набора, `Collection` набора, набор; аудит `set.delete` `{}`.
- `release_set(db, admin, set_id, now) -> ItemSet` — `is_base` → `SET_IS_BASE`; не `draft` → `SET_NOT_DRAFT`; скинов в наборе 0 → `SET_EMPTY`; `released`, `released_at=now`; аудит `set.release` `{}`.
- `retire_set(db, admin, set_id, now) -> ItemSet` — `is_base` → `SET_IS_BASE`; не `released` → `SET_NOT_RELEASED`; id кейсов `on_sale` с дропом из набора (join `CaseDrop`→`ItemDef`, `ItemDef.set_id == set.id`, distinct, order by id) → `status="off_sale"`; `retired`, `retired_at=now`; аудит `set.retire` `{"unpublished_case_ids": ids}`.
Коллекции и скины:
- `_draft_set(db, set_id) -> ItemSet` — нет → `SET_NOT_FOUND`; не `draft` → `SET_NOT_DRAFT`.
- `create_collection(db, admin, set_id, body: CollectionCreateIn) -> Collection` — `_draft_set`; как в текущем коде (12 скинов), плюс `set_id`, у скинов `kind="piece"`, `set_id`; аудит `collection.create`.
- `patch_collection(db, admin, collection_id, body: CollectionPatchIn) -> Collection` — аудит `collection.patch`.
- `delete_collection(db, admin, collection_id) -> None` — нет → 404; набор не `draft` → `SET_NOT_DRAFT`; удалить `CaseDrop` её скинов, скины, коллекцию; аудит `collection.delete`.
- `create_board(db, admin, set_id, body: BoardCreateIn) -> ItemDef` — `_draft_set`; `ItemDef(kind="board", set_id, collection_id=None, side=None, piece_type=None, code, name, rarity, value, asset=body.asset.model_dump(), is_upgrade_target)`; IntegrityError → `ITEM_CODE_TAKEN`; аудит `board.create`.
- `patch_item_def(db, admin, item_def_id, body: ItemDefPatchIn) -> ItemDef` — нет → 404; `rarity` при наборе не `draft` → `ITEM_DEF_LOCKED`; если передан `asset`: для `piece` должен быть `PieceAsset`, для `board` — `BoardAsset` (иначе `ASSET_KIND_MISMATCH`); аудит `item_def.patch`.
- `delete_item_def(db, admin, item_def_id) -> None` — нет → 404; `kind == "piece"` или набор не `draft` → `ITEM_DEF_LOCKED`; удалить его `CaseDrop` и сам скин; аудит `item_def.delete`.
Кейсы:
- `create_case(db, admin, body: CaseCreateIn) -> Case` — для `set`: набор есть (иначе `SET_NOT_FOUND`), не базовый (`SET_IS_BASE`); для `collection`: коллекция есть (`COLLECTION_NOT_FOUND`), её набор не базовый; `Case(..., status="draft", sold_count=0)`; IntegrityError → `CASE_CODE_TAKEN`; аудит `case.create` `body.model_dump(mode="json")`.
- `patch_case(db, admin, case_id, body: CasePatchIn) -> Case` — только поля из `body.model_fields_set`; `stock_limit` не None и `< case.sold_count` → `STOCK_BELOW_SOLD`; итоговые `sale_starts_at`/`sale_ends_at` оба не None и `starts >= ends` → `SALE_WINDOW_INVALID`; аудит `case.patch`.
- `delete_case(db, admin, case_id) -> None` — не `draft` → `CASE_LOCKED`; удалить дропы, строку пула, кейс; аудит `case.delete`.
- `_allowed_def_ids(db, case: Case) -> set[int]` — скины небазовых наборов со статусом не `retired`; для `kind="set"` дополнительно `ItemDef.set_id == case.set_id`, для `collection` — `ItemDef.collection_id == case.collection_id`.
- `set_drops(db, admin, case_id, drops: list[DropIn]) -> Case` — `_draft_case`; все id ⊂ `_allowed_def_ids` иначе `DROP_ITEM_NOT_AVAILABLE`; заменить дропы; аудит `case.drops.set`.
- `auto_drops(db, admin, case_id, set_ids: list[int], collection_ids: list[int]) -> Case` — `_draft_case`; `set` → скины `ItemDef.set_id == case.set_id`; `collection` → `ItemDef.collection_id == case.collection_id`; `custom` → если оба списка пусты → `AppError(422, "VALIDATION_ERROR", "Укажите наборы или коллекции")`; наборы/коллекции из списков должны существовать (`SET_NOT_FOUND` / `COLLECTION_NOT_FOUND`), не быть базовыми (`SET_IS_BASE`) и не `retired` (`DROP_ITEM_NOT_AVAILABLE`); скины = `ItemDef.set_id IN set_ids OR ItemDef.collection_id IN collection_ids`; веса `auto_weights(skins, await get_setting(db, "rarity_weights"))`; заменить дропы; аудит `case.drops.auto` `{"set_ids": ..., "collection_ids": ...}`.
- `publish_case(db, admin, case_id, now) -> Case` — нет → 404; `on_sale` → `CASE_NOT_READY`; дропов 0 → `CASE_NOT_READY`; есть дроп со скином набора не `released` → `CASE_NOT_READY`; `stock_limit` не None и `sold_count >= stock_limit` → `CASE_NOT_READY`; `status="on_sale"`; аудит `case.publish`.
- `unpublish_case(db, admin, case_id) -> Case` — не `on_sale` → `CASE_NOT_ON_SALE`; `status="off_sale"`; аудит `case.unpublish`.
Пул и выдача:
- `set_daily_pool(db, admin, entries: list[DailyPoolEntryIn]) -> None` — каждый кейс есть и не `draft`, иначе `CASE_NOT_AVAILABLE`; `delete(DailyRewardPool)` целиком, вставить новые; аудит `daily_pool.set` `{"entries": [[case_id, weight], ...]}`.
- `grant_item(db, admin, user_id, item_def_id: int | None, case_id: int | None, now) -> int` — пользователя нет → 404; скин: нет → `ITEM_DEF_NOT_FOUND`, набор базовый или не `released` → `ITEM_DEF_NOT_AVAILABLE`, `create_item(source="admin_grant", source_ref=str(admin.id))`; кейс: нет → `CASE_NOT_FOUND`, `draft` → `ITEM_DEF_NOT_AVAILABLE`, `create_case_item(source="admin_grant", source_ref=str(admin.id))`; аудит `user.grant_item` `{"item_def_id": ..., "case_id": ...}`; вернуть id предмета.
Удалить: `release_collection`, `retire_collection`, `activate_case`, `close_case`, `_check_available_defs` и неиспользуемые константы.

# Готово, когда
`python3 -m py_compile backend/app/services/catalog_admin.py` без ошибок.

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
