# Цель
Ежедневная награда (кейс из пула после 3 побед за сутки UTC), удаление старого бонуса, базовые скины при регистрации.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1 «Ежедневная награда», 5 «Ежедневная награда», 6.1 `DailyRewardOut`/`DailyRewardClaimOut`/`MeOut`), `backend/app/api/me.py`, `backend/app/api/auth.py`, `backend/app/services/economy.py` (`lock_user`), `backend/app/services/rolls.py` (`record_roll`, `get_rng`), `backend/app/services/cases.py` (`weighted_pick` — работает с любыми объектами с полем `.weight`), `backend/app/models/game.py` (`Game`: `white_id`, `black_id`, `status`, `result`, `ply`, `finished_at`).

# Область
Создать `backend/app/services/daily_reward.py`; изменить `backend/app/api/me.py`, `backend/app/api/auth.py`.

# Что сделать
`services/daily_reward.py`:
- `_day_bounds(now) -> tuple[datetime, datetime]` — начало суток UTC `now.replace(hour=0, minute=0, second=0, microsecond=0)` и +1 день.
- `async wins_today(db, user_id: int, now) -> int` — `select(func.count()).select_from(Game).where(Game.status == "finished", Game.ply >= min_plies, Game.finished_at >= start, Game.finished_at < end, or_(and_(Game.white_id == user_id, Game.result == "white"), and_(Game.black_id == user_id, Game.result == "black")))`, `min_plies = int(await get_setting(db, "reward_min_plies"))`.
- `async get_status(db, user, now) -> DailyRewardOut` — `wins_required = int(await get_setting(db, "daily_reward_wins"))`, `claimed_today = user.last_daily_reward_on == now.date()`, `available = not claimed_today and wins >= required`.
- `async claim(db, user, now) -> DailyRewardClaimOut` — `locked = await lock_user(db, user.id)`; `locked.last_daily_reward_on == now.date()` → `AppError(400, "DAILY_REWARD_CLAIMED", "Награда за сегодня уже получена")`; побед меньше → `AppError(400, "DAILY_REWARD_NOT_READY", f"Нужно победить в {required} партиях за сегодня")`; пул `select(DailyRewardPool).order_by(DailyRewardPool.case_id)` пуст → `AppError(400, "DAILY_REWARD_EMPTY", "Пул наград пуст")`; `r = get_rng().random()`; `entry = weighted_pick(pool, r)`; `item = await create_case_item(db, user_id=locked.id, case_id=entry.case_id, source="daily_reward", source_ref=None, now=now)`; `roll = await record_roll(db, user_id=locked.id, kind="daily_reward", ref=str(entry.case_id), chance=entry.weight / total, roll_value=r, input={"pool": [[p.case_id, p.weight] for p in pool]}, outcome={"case_id": entry.case_id, "item_id": item.id})` (если `record_roll` возвращает не объект с `.id` — посмотри, как его id берёт `services/upgrade.py`, и сделай так же); `locked.last_daily_reward_on = now.date()`; вернуть `DailyRewardClaimOut(case=case_ref_out(await db.get(Case, entry.case_id)), item=await item_out(db, item), roll_id=roll.id)`.
`api/me.py`:
- удалить `daily_bonus_available_at`, эндпоинт `POST /me/daily-bonus` и всё связанное с `daily_bonus*`; `me_out(user)` (без `cooldown_h`) — обнови все вызовы в файле;
- `GET /me/daily-reward` → `get_status(db, user, clock.now())`; `POST /me/daily-reward` → `claim(...)` с rate limit `await hit(f"rl:items:{user.id}", 3, 1)` (`from app.core.ratelimit import hit`).
`api/auth.py`:
- в регистрации после `apply_delta(... "signup_bonus")` — `await grant_base_items(db, user.id, clock.now())` (используй то время, которое уже используется в функции, если есть);
- убрать чтение `daily_bonus_cooldown_h`; вызовы `me_out(user)` без второго аргумента (импорт `me_out` — откуда он сейчас импортируется).

# Готово, когда
`python3 -m py_compile backend/app/services/daily_reward.py backend/app/api/me.py backend/app/api/auth.py` без ошибок; `grep -rn "daily_bonus" backend/app/api/me.py backend/app/api/auth.py` ничего не находит.

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
