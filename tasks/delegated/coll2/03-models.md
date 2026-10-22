# Цель
Обновить SQLAlchemy-модели предметов под коллекции v2.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 2), `backend/app/models/items.py`, `backend/app/models/base.py` (naming convention: в `CheckConstraint(name=...)` пишется КОРОТКОЕ имя, например `"side_whitelist"`).

# Область
Только `backend/app/models/items.py`.

# Что сделать
`ItemDef`:
- удалить поле `kind` и ограничения `kind_piece_type_consistency`, `kind_whitelist`;
- `piece_type: Mapped[str] = mapped_column(CHAR(1), nullable=False)`;
- добавить `side: Mapped[str] = mapped_column(CHAR(1), nullable=False)` сразу после `name`;
- в `__table_args__`: `CheckConstraint("side IN ('w', 'b')", name="side_whitelist")`, `CheckConstraint("piece_type IN ('P', 'N', 'B', 'R', 'Q', 'K')", name="piece_type_whitelist")`, `UniqueConstraint("collection_id", "side", "piece_type", name="uq_item_defs_collection_id_side_piece_type")` (импорт `UniqueConstraint` из `sqlalchemy`); остальные ограничения и индекс оставить.

`Loadout`: whitelist слотов → `"slot IN ('wP', 'wN', 'wB', 'wR', 'wQ', 'wK', 'bP', 'bN', 'bB', 'bR', 'bQ', 'bK')"`, имя прежнее `slot_whitelist`.

`Case`:
- удалить `collection_id`, `is_active` и `Index("ix_cases_collection_id", ...)`;
- добавить `status: Mapped[str] = mapped_column(Text, nullable=False, default="draft", server_default="draft")` после `price`;
- в `__table_args__` добавить `CheckConstraint("status IN ('draft', 'active', 'closed')", name="status_whitelist")`.

Остальные классы не трогать. Неиспользуемые импорты (`Boolean` используется в `ItemDef.is_upgrade_target` — оставить) не добавлять/не ломать.

# Готово, когда
`python3 -m py_compile backend/app/models/items.py` без ошибок.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md`. Имена, поля, коды ошибок и тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`.
- Тесты бэкенда в этой волне НЕ запускаются и будут падать — это ожидаемо, их чинит следующая волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
