# Цель
Админ-роутер каталога v2: коллекции без кейсов, кейсы отдельно, новые эндпоинты.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 6.1, 6.3 «Админ»), `backend/app/api/admin_catalog.py` (стиль).
Будет в этой волне (используй как есть):
- `app.services.catalog_admin`: `create_collection(db, admin, body)`, `patch_collection`, `delete_collection`, `release_collection(db, admin, id, now)`, `retire_collection(db, admin, id, now)`, `patch_item_def(db, admin, id, body)`, `create_case(db, admin, body)`, `patch_case(db, admin, id, body)`, `delete_case(db, admin, id)`, `set_drops(db, admin, id, drops)`, `auto_drops(db, admin, id, collection_ids: list[int])`, `activate_case(db, admin, id)`, `close_case(db, admin, id)`, `grant_item(...)` (без изменений). `create_item_def`/`delete_item_def` удалены.
- `app.services.cases.case_collections(db, case_ids: list[int]) -> dict[int, list[CollectionRef]]`.
- `app.seed_data.CANONICAL_SLOTS` (12 строк `"wP"…"bK"`).
- схемы: `AdminCollectionOut` без `cases_count`; `AdminCollectionDetailOut` без `cases`; `AdminCaseOut(id, code, name, price, status, sort, collections, drops)`; `AutoDropsIn.collection_ids`; `ItemDefCreateIn` удалён.

# Область
Только `backend/app/api/admin_catalog.py`.

# Что сделать
- `_collection_out(collection, items_count)` — без `cases_count`; `_collection_counts(db) -> dict[int, int]` — только счётчик скинов.
- Порядок скинов везде: `key=lambda d: CANONICAL_SLOTS.index(d.side + d.piece_type)`.
- `GET /collections/{id}`: без кейсов.
- `POST /collections` → `status_code=201`, `response_model=AdminCollectionDetailOut`: после `service.create_collection` загрузить скины коллекции и вернуть деталь (как в `GET`).
- `PATCH /collections/{id}`, `/release`, `/retire` → `AdminCollectionOut`.
- Удалить `POST /collections/{collection_id}/items`, `DELETE /item-defs/{item_def_id}`, `POST /collections/{collection_id}/cases`.
- Новый `GET /item-defs` → `list[ItemDefOut]`: `select(ItemDef, Collection).join(Collection, Collection.id == ItemDef.collection_id).where(Collection.status != "retired").order_by(ItemDef.collection_id, ItemDef.id)`.
- `async def _case_out(db, case: Case) -> AdminCaseOut`: дропы по `item_def_id`, `collections=(await case_collections(db, [case.id]))[case.id]`, `status=case.status`. `_load_case` удалить; нет кейса → `AppError(404, "CASE_NOT_FOUND", "Кейс не найден")` (сделай хелпер `_get_case(db, case_id) -> Case`).
- Новый `GET /cases` → `list[AdminCaseOut]`: все кейсы `order_by(Case.sort, Case.id)`, один вызов `case_collections` для всех id, дропы — одним запросом `select(CaseDrop).where(CaseDrop.case_id.in_(ids)).order_by(CaseDrop.case_id, CaseDrop.item_def_id)`.
- `POST /cases` (`status_code=201`) → `AdminCaseOut` с пустыми `drops` и `collections`.
- `PATCH /cases/{id}`, `PUT /cases/{id}/drops`, `POST /cases/{id}/drops/auto` (тело `AutoDropsIn` обязательно, НЕ Optional) → после вызова сервиса `return await _case_out(db, case)`.
- Новые `POST /cases/{id}/activate`, `POST /cases/{id}/close` → `AdminCaseOut`.
- `DELETE /cases/{id}` (204), `POST /users/{id}/grant-item` — как сейчас.
- Убрать неиспользуемые импорты.

# Готово, когда
`python3 -m py_compile backend/app/api/admin_catalog.py` без ошибок.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md`. Имена, поля, коды ошибок и тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`.
- Тесты бэкенда в этой волне НЕ запускаются и будут падать — это ожидаемо, их чинит следующая волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
