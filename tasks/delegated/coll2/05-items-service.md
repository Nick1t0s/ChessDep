# Цель
Сервис предметов: экипировка по 12 слотам и снапшот лоадаута по стороне.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 5 «Экипировка», «Снапшот», п. 6.1), `backend/app/services/items.py`, `backend/app/services/games.py` (строки ~155–185).

# Область
`backend/app/services/items.py`, `backend/app/services/games.py`.

# Что сделать
`services/items.py`:
- `item_def_out`: убрать `kind=d.kind`, добавить `side=d.side` (перед `piece_type`).
- `loadout_snapshot(db, user_id: int, side: str) -> dict[str, dict]`: брать только строки, где `Loadout.slot` начинается с `side` (фильтр `.where(Loadout.slot.startswith(side))`), ключ снапшота — `loadout.slot[1:]` (буква фигуры); значение прежнее `{code, name, rarity, asset}`. Docstring: «Снапшот слотов одной стороны (side = 'w'|'b'); ключи — буква фигуры без префикса.»
- `slot_matches(item_def, slot) -> bool`: `return slot == item_def.side + item_def.piece_type`.

`services/games.py`: только две строки — `white_loadout = await loadout_snapshot(db, white_id, "w")`, `black_loadout = await loadout_snapshot(db, black_id, "b")`. Больше ничего не менять.

# Готово, когда
`python3 -m py_compile backend/app/services/items.py backend/app/services/games.py` без ошибок.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md`. Имена, поля, коды ошибок и тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`.
- Тесты бэкенда в этой волне НЕ запускаются и будут падать — это ожидаемо, их чинит следующая волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
