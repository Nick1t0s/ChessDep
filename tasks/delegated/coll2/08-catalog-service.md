# Цель
Админ-сервис каталога v2: создание коллекции сразу с 12 скинами, кейсы без коллекции, активация/закрытие.

# Контекст
Прочитай: `docs/contracts-collections.md` (весь, особенно п. 3, 5, 6.2, аудит в конце п. 6.3), `backend/app/services/catalog_admin.py` (стиль, `_audit`, коды ошибок).
Будет в этой волне (используй как есть):
- `app.seed_data`: `item_code(collection_code, side, piece_type) -> str`, `item_name(collection_name, side, piece_type) -> str`;
- `app.schemas.items`: `CollectionCreateIn` (+ поле `pieces: list[PieceIn]`, у `PieceIn`: side, piece_type, rarity, value, asset: PieceAsset, is_upgrade_target), `ItemDefPatchIn` (name, rarity, value, asset, is_upgrade_target), `CaseCreateIn` (code, name, price, sort), `CasePatchIn` (name, price, sort), `DropIn`. `ItemDefCreateIn`, `BoardAsset` больше НЕТ.
- модели: у `Case` нет `collection_id`/`is_active`, есть `status`; у `ItemDef` нет `kind`, есть `side`.

# Область
Только `backend/app/services/catalog_admin.py`.

# Ошибки (константы модуля, дословно)
Оставить: `COLLECTION_NOT_FOUND`, `ITEM_DEF_NOT_FOUND`, `CASE_NOT_FOUND`, `USER_NOT_FOUND`, `COLLECTION_CODE_TAKEN`, `ITEM_CODE_TAKEN`, `CASE_CODE_TAKEN`, `COLLECTION_NOT_DRAFT`, `COLLECTION_NOT_RELEASED`, `ITEM_DEF_NOT_AVAILABLE`.
Изменить: `ITEM_DEF_LOCKED = AppError(400, "ITEM_DEF_LOCKED", "После выпуска можно менять только name, asset, value, is_upgrade_target")` (текст прежний), `CASE_LOCKED = AppError(400, "CASE_LOCKED", "Дропы можно менять только у черновика кейса")`.
Добавить: `CASE_NOT_READY = AppError(400, "CASE_NOT_READY", "Кейс не готов: нет дропов или есть скины невыпущенных коллекций")`, `CASE_NOT_ACTIVE = AppError(400, "CASE_NOT_ACTIVE", "Кейс не активен")`, `DROP_ITEM_NOT_AVAILABLE = AppError(400, "DROP_ITEM_NOT_AVAILABLE", "Скин недоступен для кейса")`.
Удалить: `COLLECTION_NOT_READY`, `DROP_ITEM_NOT_IN_COLLECTION`, `ASSET_KIND_MISMATCH`, `PIECE_TYPE_REQUIRED`, функции `create_item_def`, `delete_item_def`, `_asset_matches_kind`.

# Функции (сигнатуры дословно)
- `create_collection(db, admin, body: CollectionCreateIn) -> Collection`: создать `Collection(status="draft")`, `flush` (IntegrityError → `COLLECTION_CODE_TAKEN`); затем для каждого `p in body.pieces` — `ItemDef(collection_id=..., code=item_code(body.code, p.side, p.piece_type), name=item_name(body.name, p.side, p.piece_type), side=p.side, piece_type=p.piece_type, rarity=p.rarity, value=p.value, asset=p.asset.model_dump(), is_upgrade_target=p.is_upgrade_target)`; `flush` (IntegrityError → `ITEM_CODE_TAKEN`); аудит `collection.create`, payload `body.model_dump(mode="json")`.
- `patch_collection` — без изменений.
- `delete_collection(db, admin, collection_id)`: нет → `COLLECTION_NOT_FOUND`; не `draft` → `COLLECTION_NOT_DRAFT`; `def_ids = select(ItemDef.id).where(ItemDef.collection_id == collection.id)`; `delete(CaseDrop).where(CaseDrop.item_def_id.in_(def_ids))`; `delete(ItemDef)...`; `db.delete(collection)`; аудит `collection.delete` `{}`.
- `release_collection(db, admin, collection_id, now)`: нет → 404; не `draft` → `COLLECTION_NOT_DRAFT`; `status="released"`, `released_at=now`; аудит `collection.release` `{}`.
- `retire_collection(db, admin, collection_id, now)`: нет → 404; не `released` → `COLLECTION_NOT_RELEASED`; найти id кейсов: `select(Case.id).join(CaseDrop, CaseDrop.case_id == Case.id).join(ItemDef, ItemDef.id == CaseDrop.item_def_id).where(ItemDef.collection_id == collection.id, Case.status == "active").distinct().order_by(Case.id)`; им `update(Case).where(Case.id.in_(ids)).values(status="closed")` (если список не пуст); `status="retired"`, `retired_at=now`; аудит `collection.retire` payload `{"closed_case_ids": ids}`.
- `patch_item_def(db, admin, item_def_id, body: ItemDefPatchIn) -> ItemDef`: нет → `ITEM_DEF_NOT_FOUND`; если коллекция не `draft` и `"rarity" in body.model_fields_set` → `ITEM_DEF_LOCKED`; применить заданные поля из `name, rarity, value, asset (model_dump()), is_upgrade_target`; аудит `item_def.patch` (как сейчас).
- `create_case(db, admin, body: CaseCreateIn) -> Case`: `Case(code, name, price, sort, status="draft")`; IntegrityError → `CASE_CODE_TAKEN`; аудит `case.create`.
- `patch_case(db, admin, case_id, body: CasePatchIn) -> Case`: поля `name, price, sort`; аудит `case.patch`.
- `delete_case(db, admin, case_id)`: нет → `CASE_NOT_FOUND`; `status != "draft"` → `CASE_LOCKED`; удалить дропы и кейс; аудит `case.delete` `{}`.
- приватный `async def _draft_case(db, case_id) -> Case`: нет → `CASE_NOT_FOUND`; `status != "draft"` → `CASE_LOCKED`.
- приватный `async def _check_available_defs(db, def_ids: list[int]) -> None`: `select(ItemDef.id, Collection.status).join(Collection, ...).where(ItemDef.id.in_(def_ids))`; если найдено меньше уникальных id, чем передано, или у любого статус `retired` → `DROP_ITEM_NOT_AVAILABLE`.
- `set_drops(db, admin, case_id, drops: list[DropIn]) -> Case`: `_draft_case`; `_check_available_defs`; заменить дропы (как сейчас); аудит `case.drops.set` (как сейчас).
- `auto_drops(db, admin, case_id, collection_ids: list[int]) -> Case`: `_draft_case`; загрузить коллекции по id; если найдено меньше, чем передано → `COLLECTION_NOT_FOUND`; любая `retired` → `DROP_ITEM_NOT_AVAILABLE`; скины `select(ItemDef).where(ItemDef.collection_id.in_(collection_ids))`; `auto_weights(list(skins), await get_setting(db, "rarity_weights"))`; заменить дропы; аудит `case.drops.auto` `{"collection_ids": collection_ids}`.
- `activate_case(db, admin, case_id) -> Case`: нет → `CASE_NOT_FOUND`; `status == "active"` → `CASE_NOT_READY`; дропы: `select(func.count()).select_from(CaseDrop).where(CaseDrop.case_id == case.id)` < 1 → `CASE_NOT_READY`; есть дроп со скином коллекции не `released` (`select(func.count()).select_from(CaseDrop).join(ItemDef, ...).join(Collection, ...).where(CaseDrop.case_id == case.id, Collection.status != "released")` > 0) → `CASE_NOT_READY`; `status="active"`; аудит `case.activate` `{}`.
- `close_case(db, admin, case_id) -> Case`: нет → `CASE_NOT_FOUND`; `status != "active"` → `CASE_NOT_ACTIVE`; `status="closed"`; аудит `case.close` `{}`.
- `grant_item` — без изменений.

# Готово, когда
`python3 -m py_compile backend/app/services/catalog_admin.py` без ошибок.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md`. Имена, поля, коды ошибок и тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`.
- Тесты бэкенда в этой волне НЕ запускаются и будут падать — это ожидаемо, их чинит следующая волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
