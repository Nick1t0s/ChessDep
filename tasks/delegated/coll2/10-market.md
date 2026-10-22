# Цель
Фильтр маркета `kind` заменить на `side`.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 6.3, `/market`), `backend/app/api/market.py`, `backend/app/services/market.py`. У `ItemDef` больше нет `kind`, есть `side` (`"w"|"b"`).

# Область
`backend/app/api/market.py`, `backend/app/services/market.py`.

# Что сделать
- `api/market.py`: параметр `kind: Literal["piece_skin", "board_skin"] | None = None` → `side: Literal["w", "b"] | None = None`; передавать в сервис `side=side` вместо `kind=kind`.
- `services/market.py`: во всех функциях параметр `kind: str | None` переименовать в `side: str | None` (и в вызовах `kind=kind` → `side=side`); `base.where(ItemDef.kind == kind)` → `base.where(ItemDef.side == side)`. Строку `kind="market"` (это поле `ItemTransfer.kind`) НЕ трогать.
- Больше ничего не менять.

# Готово, когда
`python3 -m py_compile backend/app/api/market.py backend/app/services/market.py` и `grep -n "ItemDef.kind\|piece_skin\|board_skin" backend/app/api/market.py backend/app/services/market.py` ничего не находит.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md`. Имена, поля, коды ошибок и тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`.
- Тесты бэкенда в этой волне НЕ запускаются и будут падать — это ожидаемо, их чинит следующая волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
