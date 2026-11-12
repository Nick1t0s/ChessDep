# Цель
Миграция `0006`: удалить все текущие предметы, перестроить схему под коллекции v2 и вставить новую Genesis.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 2, 4), `backend/alembic/versions/0003_items.py` (образец: стиль, `op.f(...)`-имена, `bulk_insert`, `setval`), `backend/alembic/versions/0005_chat.py` (как записаны `revision`/`down_revision`).

# Область
Создать только `backend/alembic/versions/0006_collections_v2.py`. `revision = "0006"`, `down_revision = "0005"`. Импорт сида: `from app.seed_data import genesis_rows` (функция будет переписана другой задачей; её ключи строк: collections — id, code, name, description, status, released_at; item_defs — id, collection_id, code, name, side, piece_type, rarity, value, asset, is_upgrade_target; cases — id, code, name, price, status, sort; case_drops — case_id, item_def_id, weight).

# Имена ограничений
В проекте у metadata задан naming convention (`backend/app/models/base.py`), alembic применяет его к именам. Поэтому КАЖДОЕ имя ограничения/индекса во всех вызовах `drop_constraint`, `create_check_constraint`, `create_unique_constraint`, `create_foreign_key`, `drop_index`, `create_index` оборачивай в `op.f(...)`, например `op.drop_constraint(op.f("ck_item_defs_kind_whitelist"), "item_defs", type_="check")`. Имена ниже — полные итоговые имена в БД.

# upgrade()
1. `op.execute` по очереди: `DELETE FROM item_transfers`, `DELETE FROM market_listings`, `DELETE FROM loadouts`, `DELETE FROM inventory_items`, `DELETE FROM case_drops`, `DELETE FROM cases`, `DELETE FROM item_defs`, `DELETE FROM collections`.
2. item_defs:
   - `op.drop_constraint("ck_item_defs_kind_piece_type_consistency", "item_defs", type_="check")`;
   - `op.drop_constraint("ck_item_defs_kind_whitelist", "item_defs", type_="check")`;
   - `op.drop_constraint("ck_item_defs_piece_type_whitelist", "item_defs", type_="check")`;
   - `op.drop_column("item_defs", "kind")`;
   - `op.add_column("item_defs", sa.Column("side", sa.CHAR(length=1), nullable=False))`;
   - `op.alter_column("item_defs", "piece_type", existing_type=sa.CHAR(length=1), nullable=False)`;
   - `op.create_check_constraint("ck_item_defs_side_whitelist", "item_defs", "side IN ('w', 'b')")`;
   - `op.create_check_constraint("ck_item_defs_piece_type_whitelist", "item_defs", "piece_type IN ('P', 'N', 'B', 'R', 'Q', 'K')")`;
   - `op.create_unique_constraint("uq_item_defs_collection_id_side_piece_type", "item_defs", ["collection_id", "side", "piece_type"])`.
3. cases:
   - `op.drop_index("ix_cases_collection_id", table_name="cases")`;
   - `op.drop_constraint("fk_cases_collection_id_collections", "cases", type_="foreignkey")`;
   - `op.drop_column("cases", "collection_id")`; `op.drop_column("cases", "is_active")`;
   - `op.add_column("cases", sa.Column("status", sa.Text(), server_default="draft", nullable=False))`;
   - `op.create_check_constraint("ck_cases_status_whitelist", "cases", "status IN ('draft', 'active', 'closed')")`.
4. loadouts: `op.drop_constraint("ck_loadouts_slot_whitelist", "loadouts", type_="check")`; `op.create_check_constraint("ck_loadouts_slot_whitelist", "loadouts", "slot IN ('wP', 'wN', 'wB', 'wR', 'wQ', 'wK', 'bP', 'bN', 'bB', 'bR', 'bQ', 'bK')")`.
5. `rows = genesis_rows()`; `op.bulk_insert` в `collections`, `item_defs`, `cases`, `case_drops` через локальные `sa.Table`-описания (как `_collections_table()` и т. д. в 0003, но с колонками новой схемы); затем `setval` для `collections`, `item_defs`, `cases` — ровно тем же кодом, что в 0003.

# downgrade()
1. Те же 8 `DELETE FROM` в том же порядке.
2. loadouts: вернуть `ck_loadouts_slot_whitelist` = `slot IN ('P', 'N', 'B', 'R', 'Q', 'K', 'board')`.
3. cases: drop `ck_cases_status_whitelist`, drop column `status`; add `collection_id INTEGER NOT NULL`, add `is_active BOOLEAN NOT NULL server_default true`; `op.create_foreign_key("fk_cases_collection_id_collections", "cases", "collections", ["collection_id"], ["id"])`; `op.create_index("ix_cases_collection_id", "cases", ["collection_id"])`.
4. item_defs: drop `uq_item_defs_collection_id_side_piece_type`, `ck_item_defs_side_whitelist`, `ck_item_defs_piece_type_whitelist`; drop column `side`; `piece_type` → nullable=True; add column `kind TEXT NOT NULL`; вернуть три check-ограничения ровно как в 0003 (`kind_piece_type_consistency`, `kind_whitelist`, `piece_type_whitelist` с `piece_type IS NULL OR ...`).
Данные в downgrade не восстанавливаются.

# Готово, когда
`python3 -m py_compile backend/alembic/versions/0006_collections_v2.py` без ошибок. Полная проверка миграции — следующей волной.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md`. Имена, поля, коды ошибок и тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`.
- Тесты бэкенда в этой волне НЕ запускаются и будут падать — это ожидаемо, их чинит следующая волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
