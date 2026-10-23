# Цель
SQLAlchemy-модели под контракт v3.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 2), `backend/app/models/items.py`, `backend/app/models/market.py`, `backend/app/models/roll.py`, `backend/app/models/user.py`, `backend/app/models/__init__.py`, `backend/app/models/base.py` (naming convention: в `CheckConstraint(name=...)` — КОРОТКОЕ имя, например `"kind_whitelist"`; итоговое `ck_<table>_<name>`).

# Область
`backend/app/models/items.py`, `backend/app/models/market.py`, `backend/app/models/roll.py`, `backend/app/models/user.py`, `backend/app/models/__init__.py`.

# Что сделать
`models/items.py`:
- Новый класс `ItemSet` (`__tablename__ = "item_sets"`) перед `Collection`: `id`, `code` (unique), `name`, `description`, `status` (default/server_default `"draft"`), `is_base: Mapped[bool]` (`Boolean`, nullable=False, default=False, server_default `"false"`), `created_at` (server_default `func.now()`), `released_at`, `retired_at` (nullable). `__table_args__`: `CheckConstraint("status IN ('draft', 'released', 'retired')", name="status_whitelist")`, `Index("uq_item_sets_single_base", "is_base", unique=True, postgresql_where=text("is_base"))` (импорт `text` из `sqlalchemy`).
- `Collection`: удалить `status`, `released_at`, `retired_at` и их check; добавить `set_id: Mapped[int] = mapped_column(Integer, ForeignKey("item_sets.id"), nullable=False)`, `Index("ix_collections_set_id", "set_id")`.
- `ItemDef`: добавить `kind: Mapped[str]` (Text, not null), `set_id: Mapped[int]` (FK `item_sets.id`, not null); `collection_id: Mapped[int | None]`, `side: Mapped[str | None]`, `piece_type: Mapped[str | None]` (nullable). Ограничения: `CheckConstraint("kind IN ('piece', 'board')", name="kind_whitelist")`, `CheckConstraint("side IS NULL OR side IN ('w', 'b')", name="side_whitelist")`, `CheckConstraint("piece_type IS NULL OR piece_type IN ('P', 'N', 'B', 'R', 'Q', 'K')", name="piece_type_whitelist")`, `CheckConstraint("(kind = 'piece' AND collection_id IS NOT NULL AND side IS NOT NULL AND piece_type IS NOT NULL) OR (kind = 'board' AND collection_id IS NULL AND side IS NULL AND piece_type IS NULL)", name="kind_shape")`, прежние `rarity_whitelist`, `value_positive`, unique `(collection_id, side, piece_type)`, индекс `ix_item_defs_collection_id`, новый `Index("ix_item_defs_set_id", "set_id")`.
- `InventoryItem`: `item_def_id: Mapped[int | None]` (nullable), `case_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cases.id"))`, `wear: Mapped[float | None]` (nullable). Ограничения: `source IN ('case', 'upgrade', 'admin_grant', 'base', 'shop', 'daily_reward')` (`source_whitelist`), `wear IS NULL OR (wear >= 0 AND wear < 1)` (`wear_range`), `(item_def_id IS NULL) <> (case_id IS NULL)` (`one_kind`). ВАЖНО: класс `Case` объявлен ниже — ForeignKey по строке `"cases.id"` это допускает.
- `Loadout`: whitelist слотов — 12 фигур + `'board'`.
- `Case`: добавить `kind: Mapped[str]` (Text, not null), `set_id: Mapped[int | None]` (FK `item_sets.id`), `collection_id: Mapped[int | None]` (FK `collections.id`), `stock_limit: Mapped[int | None]` (Integer), `sold_count: Mapped[int]` (Integer, not null, default 0, server_default `"0"`), `sale_starts_at`, `sale_ends_at` (`DateTime(timezone=True)`, nullable). Ограничения: статус `status IN ('draft', 'on_sale', 'off_sale')`, `kind IN ('set', 'collection', 'custom')` (`kind_whitelist`), `kind_ref` (текст — п. 2 контракта), `stock_limit IS NULL OR stock_limit > 0` (`stock_limit_positive`), `sold_count >= 0` (`sold_count_nonnegative`), прежний `price_positive`.
- Новый класс `DailyRewardPool` (`__tablename__ = "daily_reward_pool"`) в конце: `case_id: Mapped[int] = mapped_column(Integer, ForeignKey("cases.id"), primary_key=True)`, `weight: Mapped[int]` (not null), `CheckConstraint("weight > 0", name="weight_positive")`.

`models/market.py` (`MarketListing`): `item_def_id: Mapped[int | None]` (nullable), `case_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cases.id"))`, `CheckConstraint("(item_def_id IS NULL) <> (case_id IS NULL)", name="one_kind")`, `Index("ix_market_listings_case_id_status_price", "case_id", "status", "price")`. Остальное не трогать.

`models/roll.py`: whitelist `kind IN ('dep', 'case_open', 'upgrade', 'daily_reward')`.

`models/user.py`: удалить `last_daily_bonus_at`; добавить `last_daily_reward_on: Mapped[date | None] = mapped_column(Date)` (импорт `date` из `datetime`, `Date` из `sqlalchemy`).

`models/__init__.py`: экспортировать `ItemSet`, `DailyRewardPool` (импорт и `__all__`, в алфавитном порядке как сейчас).

# Готово, когда
`python3 -m py_compile backend/app/models/*.py` без ошибок.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md` (контракт предметов v3). Имена, поля, коды ошибок, тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()` (`import app.core.clock as clock`). Случайность — только `get_rng()` из `app.services.rolls`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`. Баланс — только `economy.apply_delta`.
- Порядок блокировок: `market_listings` → `inventory_items` → `cases` → `games` → `users`.
- Тесты бэкенда в этой волне НЕ запускаются и могут падать — их чинит отдельная волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
