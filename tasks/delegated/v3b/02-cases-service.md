# Цель
`services/cases.py` под v3: магазин, покупка кейса-предмета, открытие кейса из инвентаря.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1 «Кейс», 5 «Кейс», 6.1 `ShopCaseOut`/`CaseDetailOut`/`CaseBuyOut`/`CaseOpenOut`), `backend/app/services/cases.py` (текущий — образец ленты и RNG), `backend/app/services/economy.py` (`apply_delta`), `backend/app/services/rolls.py` (`record_roll`).

# Область
Только `backend/app/services/cases.py`.

# Что сделать
Реализовать функции `app.services.cases` из «Общие хелперы» ниже. Удалить `openable_case`, `case_collections`, старую `open_case`. `auto_weights`, `weighted_pick`, константы ленты — НЕ менять.
- `on_sale_now` — по формуле п. 5 контракта.
- `shop_case_outs`: одним запросом загрузить `ItemSet` по `set_id` и `Collection` по `collection_id` кейсов; `stock_left = stock_limit - sold_count` или `None`.
- `case_detail`: кейс (`draft` / нет → `AppError(404, "CASE_NOT_FOUND", "Кейс не найден")`); дропы `order_by(CaseDrop.item_def_id)`; `defs = await defs_out(db, ids)`; `chance = weight / total`, `chance_text = format_chance(chance)` (`from app.chess_engine import format_chance`); `on_sale_now=on_sale_now(case, now)`. Поля `ShopCaseOut` — через `shop_case_outs(db, [case])[0]`.
- `buy_case`: кейс нет / `draft` → 404; `not on_sale_now(case, now)` → `AppError(400, "CASE_NOT_AVAILABLE", "Кейс сейчас не продаётся")`; затем атомарный `UPDATE` (SQLAlchemy `update(Case).where(Case.id == case_id, Case.status == "on_sale", or_(Case.stock_limit.is_(None), Case.sold_count < Case.stock_limit)).values(sold_count=Case.sold_count + 1).returning(Case.sold_count, Case.stock_limit)`); нет строки → `CASE_NOT_AVAILABLE`; если `stock_limit is not None and sold_count >= stock_limit` → `update(Case).where(Case.id == case_id).values(status="off_sale")`; `balance = await apply_delta(db, user.id, -case.price, "case_purchase", ref=str(case.id))`; `item = await create_case_item(db, user_id=user.id, case_id=case.id, source="shop", source_ref=str(case.id), now=now)`; вернуть `CaseBuyOut(item=await item_out(db, item), balance=balance)`. Перед `UPDATE` — ничего не блокировать (порядок: `cases` → `users`).
- `open_case_item`: `items = await lock_items(db, user.id, [item_id])` (свой `owned`); `item.case_id is None` → `AppError(400, "ITEM_NOT_CASE", "Это не кейс")`; `case = await db.get(Case, item.case_id)`; дропы по `item_def_id`; пусто → `CASE_NOT_AVAILABLE`; `item.status = "burned"`, `item.burned_at = now`; далее как в старом `open_case`: `rng = get_rng()`, `r_win`, `winner`, `win_index`, лента 60, `create_item(... source="case", source_ref=str(case.id) ...)`, `record_roll(kind="case_open", ref=str(case.id), chance=winner.weight/total, roll_value=r_win, input={"case_id": case.id, "inventory_item_id": item.id}, outcome={"item_def_id": winner.item_def_id, "item_id": new_item.id})`; `defs = await defs_out(db, set(strip))`, ключи — `str(id)`; вернуть `CaseOpenOut(item=await item_out(db, new_item), strip, win_index, defs)`. Баланс не трогать.

# Готово, когда
`python3 -m py_compile backend/app/services/cases.py` без ошибок.

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
