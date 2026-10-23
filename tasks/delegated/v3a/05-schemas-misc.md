# Цель
Схемы маркета/подарков/me и настройки под контракт v3.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 2 `settings`, п. 6.1 маркет и `MeOut`), `backend/app/schemas/market.py`, `backend/app/schemas/gifts.py`, `backend/app/schemas/auth.py`, `backend/app/services/settings.py`.
В этой же волне в `app.schemas.items` появится `CaseRefOut {id, code, name, kind, price}`.

# Область
`backend/app/schemas/market.py`, `backend/app/schemas/auth.py`, `backend/app/services/settings.py`.

# Что сделать
- `schemas/market.py`: `ListingItemOut {id, kind: Literal["skin", "case"], item_def: ItemDefOut | None = Field(alias="def"), case: CaseRefOut | None, wear: float | None, exterior: str | None}`; новый `CaseMarketOut {case: CaseRefOut, stats: MarketStatsOut, listings: list[ListingOut], sales: list[DefSaleOut]}` (`extra="forbid"`, как соседние классы). Остальное не менять.
- `schemas/auth.py`: из `MeOut` удалить `daily_bonus_available_at`; удалить класс `DailyBonusOut`.
- `services/settings.py`: удалить ключи `daily_bonus`, `daily_bonus_cooldown_h` из `DEFAULTS` и `SETTINGS_SCHEMA`; добавить `"daily_reward_wins": 3` в `DEFAULTS` (после `trade_hold_hours`) и `"daily_reward_wins": _int_validator(1, 50)` в `SETTINGS_SCHEMA`.
- `schemas/gifts.py` не трогать (он использует `ListingItemOut`).

# Готово, когда
`python3 -m py_compile backend/app/schemas/market.py backend/app/schemas/auth.py backend/app/services/settings.py` без ошибок.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md` (контракт предметов v3). Имена, поля, коды ошибок, тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()` (`import app.core.clock as clock`). Случайность — только `get_rng()` из `app.services.rolls`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`. Баланс — только `economy.apply_delta`.
- Порядок блокировок: `market_listings` → `inventory_items` → `cases` → `games` → `users`.
- Тесты бэкенда в этой волне НЕ запускаются и могут падать — их чинит отдельная волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
