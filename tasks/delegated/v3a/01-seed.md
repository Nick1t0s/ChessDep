# Цель
Сид-данные v3 (базовый набор + Genesis) и заморозка сида v2 для миграции 0006.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 3, 4), `backend/app/seed_data.py`, `backend/app/seed_data_v1.py` (образец заморозки), `backend/alembic/versions/0006_collections_v2.py` (строка импорта сида).

# Область
1. Создать `backend/app/seed_data_v2.py` — ТОЧНАЯ копия текущего `backend/app/seed_data.py`, функция `genesis_rows` переименована в `genesis_rows_v2`, docstring модуля: «Замороженные сид-данные v2 для миграции 0006. Не менять.»
2. В `backend/alembic/versions/0006_collections_v2.py` заменить только строку импорта на `from app.seed_data_v2 import genesis_rows_v2 as genesis_rows`.
3. Переписать `backend/app/seed_data.py`:
   - оставить без изменений: `import app.core.clock as clock`, `RARITY_VALUES`, `SIDES`, `PIECE_TYPES`, `PIECE_NAMES`, `CANONICAL_SLOTS`, `GENESIS_RARITY`, `GENESIS_COLORS`, `item_code`, `item_name`;
   - добавить `LOADOUT_SLOTS: tuple[str, ...] = CANONICAL_SLOTS + ("board",)`, `BASE_SET_ID = 1`, `BASE_DEF_IDS: tuple[int, ...] = tuple(range(1, 14))`, `BASE_COLORS: dict[str, str] = {"w": "#f4f6ff", "b": "#ff5470"}`;
   - `GENESIS_WEIGHTS` заменить на `{"common": 3996000, "uncommon": 319600, "rare": 160000, "epic": 32000, "legendary": 10000, "mythic": 6000}`;
   - удалить `genesis_rows`; добавить `seed_rows() -> dict[str, list[dict]]` с ключами `item_sets`, `collections`, `item_defs`, `cases`, `case_drops`, `daily_reward_pool` — ровно по п. 4 контракта. `now = clock.now()`.
     - `item_sets`: 2 строки с ключами `id, code, name, description, status, is_base, released_at`.
     - `collections`: 2 строки `id, set_id, code, name, description`.
     - `item_defs`: 27 строк, у каждой ВСЕ ключи `id, set_id, collection_id, code, name, kind, side, piece_type, rarity, value, asset, is_upgrade_target` (для досок `collection_id/side/piece_type = None`). id 1–12 — база в порядке `CANONICAL_SLOTS`, коды `item_code("base", side, pt)`, имена `item_name("Базовая", side, pt)`; id 13 — базовая доска; id 14–25 — Genesis (`item_code("genesis", …)`, `item_name("Genesis", …)`); id 26, 27 — доски Genesis.
     - `cases`: 1 строка со всеми ключами из п. 4.
     - `case_drops`: для id 14–27 `{"case_id": 1, "item_def_id": id, "weight": GENESIS_WEIGHTS[rarity]}`.
     - `daily_reward_pool`: `[{"case_id": 1, "weight": 1}]`.
   - docstring модуля: используют `alembic/versions/0007_sets.py` и `tests/conftest.py`.

# Готово, когда
`python3 -m py_compile backend/app/seed_data.py backend/app/seed_data_v2.py backend/alembic/versions/0006_collections_v2.py` без ошибок, и `cd backend && python3 -c "from app.seed_data import seed_rows; r=seed_rows(); assert len(r['item_defs'])==27 and sum(d['weight'] for d in r['case_drops'])==10_000_000; print('ok')"` печатает `ok`.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md` (контракт предметов v3). Имена, поля, коды ошибок, тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()` (`import app.core.clock as clock`). Случайность — только `get_rng()` из `app.services.rolls`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`. Баланс — только `economy.apply_delta`.
- Порядок блокировок: `market_listings` → `inventory_items` → `cases` → `games` → `users`.
- Тесты бэкенда в этой волне НЕ запускаются и могут падать — их чинит отдельная волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
