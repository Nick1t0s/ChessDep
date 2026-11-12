# Цель
Сервис кейсов v2: кейс не привязан к коллекции, статус `draft/active/closed`, хелпер «коллекции кейса».

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1, 5 «Кейс», 6.1), `backend/app/services/cases.py`, `backend/app/services/items.py` (`item_def_out(d, collection)`).
Учти: после этой волны у `Case` нет `collection_id` и `is_active`, есть `status: str`; у `ItemDef` есть `collection_id`.

# Область
Только `backend/app/services/cases.py`.

# Что сделать
1. `auto_weights` и `weighted_pick` — НЕ менять.
2. Добавить (импорт `CollectionRef` из `app.schemas.items`):
```python
async def case_collections(db: AsyncSession, case_ids: list[int]) -> dict[int, list[CollectionRef]]:
    """Различные коллекции дропов каждого кейса, по возрастанию collection.id."""
```
   Один запрос: `select(CaseDrop.case_id, Collection.id, Collection.code, Collection.name).join(ItemDef, ItemDef.id == CaseDrop.item_def_id).join(Collection, Collection.id == ItemDef.collection_id).where(CaseDrop.case_id.in_(case_ids)).distinct().order_by(CaseDrop.case_id, Collection.id)`. В результате есть ключ для КАЖДОГО id из `case_ids` (пустой список, если дропов нет). Пустой `case_ids` → `{}` без запроса.
3. `openable_case(db, case_id) -> tuple[Case, list[CaseDrop]]`:
   - нет кейса или `case.status == "draft"` → `_CASE_NOT_FOUND`;
   - `case.status == "closed"` → `_CASE_NOT_AVAILABLE`;
   - дропы (как сейчас, по `item_def_id`); пусто → `_CASE_NOT_AVAILABLE`.
4. `open_case`: `case, drops = await openable_case(db, case_id)`. Порядок вызовов `rng.random()`, лента, `record_roll` — без изменений. Сборка `defs`: одним запросом `select(ItemDef, Collection).join(Collection, Collection.id == ItemDef.collection_id).where(ItemDef.id.in_(set(strip)))`, затем `defs[str(d.id)] = item_def_out(d, collection)` для каждого def-id из `strip` в порядке первого появления.
5. Удалить переменную/использование `collection_ref`.

# Готово, когда
`python3 -m py_compile backend/app/services/cases.py` без ошибок.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md`. Имена, поля, коды ошибок и тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`.
- Тесты бэкенда в этой волне НЕ запускаются и будут падать — это ожидаемо, их чинит следующая волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
