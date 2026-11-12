# Цель
Публичные/игровые эндпоинты предметов под v2: инвентарь с фильтром `side`, 12 слотов, кейсы со списком коллекций.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 5, 6.1, 6.3 «Игрок / публично»), `backend/app/api/items.py`.
Функции, которые появятся в этой же волне (сигнатуры точные, используй их):
- `app.services.cases.openable_case(db, case_id) -> tuple[Case, list[CaseDrop]]` (бросает `CASE_NOT_FOUND`/`CASE_NOT_AVAILABLE`);
- `app.services.cases.case_collections(db, case_ids: list[int]) -> dict[int, list[CollectionRef]]`;
- `app.services.items.slot_matches(item_def, slot) -> bool`;
- `app.seed_data.CANONICAL_SLOTS: tuple[str, ...]` — 12 слотов `("wP", …, "wK", "bP", …, "bK")`.
У `Case` нет `collection_id`/`is_active`, есть `status`. У `ItemDef` нет `kind`, есть `side`.

# Область
Только `backend/app/api/items.py`.

# Что сделать
- `_ALL_SLOTS` удалить, вместо него импортировать `CANONICAL_SLOTS` из `app.seed_data`.
- `get_collection` и `list_item_defs`: сортировка `defs` → по `CANONICAL_SLOTS.index(d.side + d.piece_type)`. `list_item_defs` не менять.
- `list_inventory`: параметр `kind` заменить на `side: Literal["w", "b"] | None = None` → `query.where(ItemDef.side == side)`; фильтр `slot` → `query.where(ItemDef.side == slot[0], ItemDef.piece_type == slot[1])`.
- `_loadout_out`: цикл по `CANONICAL_SLOTS`; `return LoadoutOut(**out)`.
- `list_cases`: `select(Case).where(Case.status == "active").order_by(Case.sort, Case.id)`; `cols = await cases_service.case_collections(db, [c.id for c in cases])`; `CaseOut(..., collections=cols[case.id])`.
- `get_case`: `case, drops = await cases_service.openable_case(db, case_id)` (перехват `CASE_NOT_AVAILABLE` → 404 оставить); defs одним запросом `select(ItemDef, Collection).join(Collection, Collection.id == ItemDef.collection_id).where(ItemDef.id.in_([d.item_def_id for d in drops]))`; `item_def_out(defs[id], collections[id])`; `collections=(await cases_service.case_collections(db, [case.id]))[case.id]`.
- Убрать неиспользуемые импорты (`CollectionRef`, если не нужен).

# Готово, когда
`python3 -m py_compile backend/app/api/items.py` без ошибок.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md`. Имена, поля, коды ошибок и тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`.
- Тесты бэкенда в этой волне НЕ запускаются и будут падать — это ожидаемо, их чинит следующая волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
