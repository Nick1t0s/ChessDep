# Цель
Миграция `0007`: наборы, доски, кейсы-предметы, магазин, пул ежедневной награды; удаление всех предметов; новый сид; выдача базовых скинов всем пользователям.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 2, 4), `backend/alembic/versions/0006_collections_v2.py` (образец: стиль, `op.f(...)`, `bulk_insert`, `setval`), `backend/alembic/versions/0003_items.py`, `backend/alembic/versions/0001_initial.py` (как устроены `settings`, `users`), `backend/alembic/versions/0002_games.py` (`rolls`), `backend/alembic/versions/0004_market.py` (`market_listings`).
Сид: `from app.seed_data import seed_rows, LOADOUT_SLOTS, BASE_DEF_IDS` (функция пишется параллельно; ключи строк — ровно как в п. 4 контракта, у `item_defs` все ключи `id, set_id, collection_id, code, name, kind, side, piece_type, rarity, value, asset, is_upgrade_target`; у `cases` — `id, code, name, kind, set_id, collection_id, price, status, sort, stock_limit, sold_count, sale_starts_at, sale_ends_at`).

# Область
Создать только `backend/alembic/versions/0007_sets.py`, `revision = "0007"`, `down_revision = "0006"`.

# Имена ограничений
Каждое имя ограничения/индекса в `drop_constraint`, `create_check_constraint`, `create_unique_constraint`, `create_foreign_key`, `create_index`, `drop_index`, `sa.CheckConstraint(name=...)` внутри `create_table` оборачивай в `op.f(...)` — полное итоговое имя, как в 0006. Имена FK: `fk_<таблица>_<колонка>_<таблица-цель>`; индексы: `ix_<таблица>_<колонка>`.

# upgrade()
1. `DELETE FROM` по порядку: `item_transfers`, `market_listings`, `loadouts`, `inventory_items`, `case_drops`, `cases`, `item_defs`, `collections`.
2. `op.create_table("item_sets", ...)` по контракту; `op.create_index(op.f("uq_item_sets_single_base"), "item_sets", ["is_base"], unique=True, postgresql_where=sa.text("is_base"))`.
3. `collections`: drop check `ck_collections_status_whitelist`, drop columns `status`, `released_at`, `retired_at`; add `set_id INTEGER NOT NULL` + FK `fk_collections_set_id_item_sets` + индекс `ix_collections_set_id`.
4. `item_defs`: add `kind TEXT NOT NULL` + check `ck_item_defs_kind_whitelist` (`kind IN ('piece', 'board')`); add `set_id INTEGER NOT NULL` + FK `fk_item_defs_set_id_item_sets` + индекс `ix_item_defs_set_id`; `alter_column` nullable=True для `collection_id`, `side`, `piece_type`; пересоздать `ck_item_defs_side_whitelist` = `side IS NULL OR side IN ('w', 'b')`, `ck_item_defs_piece_type_whitelist` = `piece_type IS NULL OR piece_type IN ('P', 'N', 'B', 'R', 'Q', 'K')`; add check `ck_item_defs_kind_shape` (текст — п. 2 контракта).
5. `cases`: add `kind TEXT NOT NULL`, `set_id INTEGER NULL` (FK `fk_cases_set_id_item_sets`), `collection_id INTEGER NULL` (FK `fk_cases_collection_id_collections`), `stock_limit INTEGER NULL`, `sold_count INTEGER NOT NULL server_default '0'`, `sale_starts_at TIMESTAMPTZ NULL`, `sale_ends_at TIMESTAMPTZ NULL`; checks `ck_cases_kind_whitelist` (`kind IN ('set', 'collection', 'custom')`), `ck_cases_kind_ref` (п. 2), `ck_cases_stock_limit_positive` (`stock_limit IS NULL OR stock_limit > 0`), `ck_cases_sold_count_nonnegative` (`sold_count >= 0`); пересоздать `ck_cases_status_whitelist` = `status IN ('draft', 'on_sale', 'off_sale')`; `alter_column("cases", "status", server_default="draft")`.
6. `inventory_items`: `item_def_id` и `wear` → nullable; add `case_id INTEGER NULL` + FK `fk_inventory_items_case_id_cases`; check `ck_inventory_items_one_kind` (`(item_def_id IS NULL) <> (case_id IS NULL)`); пересоздать `ck_inventory_items_wear_range` = `wear IS NULL OR (wear >= 0 AND wear < 1)`; пересоздать `ck_inventory_items_source_whitelist` = `source IN ('case', 'upgrade', 'admin_grant', 'base', 'shop', 'daily_reward')`.
7. `loadouts`: пересоздать `ck_loadouts_slot_whitelist` = 12 слотов фигур + `'board'`.
8. `market_listings`: `item_def_id` → nullable; add `case_id INTEGER NULL` + FK `fk_market_listings_case_id_cases`; check `ck_market_listings_one_kind` (`(item_def_id IS NULL) <> (case_id IS NULL)`); индекс `ix_market_listings_case_id_status_price` на `["case_id", "status", "price"]`.
9. `op.create_table("daily_reward_pool", ...)`: `case_id INTEGER` pk (`pk_daily_reward_pool`) + FK `fk_daily_reward_pool_case_id_cases`, `weight INTEGER NOT NULL` + check `ck_daily_reward_pool_weight_positive` (`weight > 0`).
10. `users`: drop column `last_daily_bonus_at`; add `last_daily_reward_on DATE NULL`.
11. `rolls`: пересоздать `ck_rolls_kind_whitelist` = `kind IN ('dep', 'case_open', 'upgrade', 'daily_reward')` (сначала проверь точное имя в 0002).
12. `settings`: `DELETE FROM settings WHERE key IN ('daily_bonus', 'daily_bonus_cooldown_h')`; вставить `{"key": "daily_reward_wins", "value": 3}` (через `op.bulk_insert` и локальную `sa.Table` с JSONB, как `_settings_table()` в 0003).
13. `rows = seed_rows()`; `op.bulk_insert` по порядку: `item_sets`, `collections`, `item_defs`, `cases`, `case_drops`, `daily_reward_pool` (локальные `sa.Table` с нужными колонками; `asset` — JSONB). Затем `setval` для `item_sets`, `collections`, `item_defs`, `cases` (код как в 0006).
14. Выдача базовых предметов всем пользователям — два `op.execute(sa.text(...))`:
    - `INSERT INTO inventory_items (user_id, item_def_id, wear, status, source, created_at, acquired_at) SELECT u.id, d.id, 0, 'owned', 'base', now(), now() FROM users u CROSS JOIN item_defs d WHERE d.id BETWEEN 1 AND 13`;
    - `INSERT INTO loadouts (user_id, slot, inventory_item_id) SELECT i.user_id, CASE WHEN d.kind = 'board' THEN 'board' ELSE d.side || d.piece_type END, i.id FROM inventory_items i JOIN item_defs d ON d.id = i.item_def_id WHERE i.source = 'base'`.

# downgrade()
1. `DELETE FROM daily_reward_pool` и те же 8 `DELETE FROM`.
2. Обратно всё по шагам 11 → 3 в обратном порядке: rolls whitelist без `daily_reward` (удалить строки `rolls` с `kind = 'daily_reward'` перед этим); users: drop `last_daily_reward_on`, add `last_daily_bonus_at TIMESTAMPTZ NULL`; drop table `daily_reward_pool`; market_listings: drop индекс, check, FK, колонку `case_id`, `item_def_id` → NOT NULL; loadouts: whitelist 12 слотов (как в 0006); inventory_items: вернуть whitelist source `('case', 'upgrade', 'admin_grant')`, wear-check `wear >= 0 AND wear < 1`, drop `one_kind`, FK, `case_id`, `item_def_id`/`wear` → NOT NULL; cases: drop добавленные checks/FK/колонки, статус-whitelist `('draft', 'active', 'closed')`; item_defs: drop `kind_shape`, `kind_whitelist`, индекс/FK/`set_id`, `kind`; whitelist'ы side/piece_type без `IS NULL OR`; `collection_id`/`side`/`piece_type` → NOT NULL; collections: drop индекс/FK/`set_id`, add `status TEXT NOT NULL server_default 'draft'` + check `ck_collections_status_whitelist` (`status IN ('draft', 'released', 'retired')`), `released_at`, `retired_at` TIMESTAMPTZ NULL; drop index `uq_item_sets_single_base`, drop table `item_sets`.
3. settings: `DELETE FROM settings WHERE key = 'daily_reward_wins'`; вставить `daily_bonus` = 200, `daily_bonus_cooldown_h` = 24.

# Готово, когда
`python3 -m py_compile backend/alembic/versions/0007_sets.py` без ошибок. Реальный прогон — в следующей волне.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md` (контракт предметов v3). Имена, поля, коды ошибок, тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()` (`import app.core.clock as clock`). Случайность — только `get_rng()` из `app.services.rolls`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`. Баланс — только `economy.apply_delta`.
- Порядок блокировок: `market_listings` → `inventory_items` → `cases` → `games` → `users`.
- Тесты бэкенда в этой волне НЕ запускаются и могут падать — их чинит отдельная волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
