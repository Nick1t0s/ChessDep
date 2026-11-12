# Цель
Переписать `backend/tests/test_catalog_admin.py` под админ-API каталога v2.

# Контекст
Прочитай: `docs/contracts-collections.md` (весь), текущий `backend/tests/test_catalog_admin.py` (стиль, фикстуры `admin`, `alice`, `client`, `db`, `rng`), `backend/tests/conftest.py`, `backend/app/api/admin_catalog.py`, `backend/app/services/catalog_admin.py`.

# Область
Только `backend/tests/test_catalog_admin.py`.

# Что сделать
Добавь в файл хелпер:
```python
SLOTS = [s + p for s in "wb" for p in "PNBRQK"]

def pieces_body(rarity: str = "common", value: int = 20) -> list[dict]:
    return [
        {"side": s[0], "piece_type": s[1], "rarity": rarity, "value": value,
         "asset": {"type": "stub", "color": "#ffffff"}}
        for s in SLOTS
    ]

async def create_collection(admin, code: str = "winter", name: str = "Winter") -> dict:
    resp = await admin.post("/api/v1/admin/collections", json={
        "code": code, "name": name, "description": "", "pieces": pieces_body()})
    assert resp.status_code == 201, resp.text
    return resp.json()
```
Тесты (оставить `test_admin_required` как есть, если проходит; остальные заменить):
1. `test_collection_create_shape` — `create_collection`: `status == "draft"`, `items_count == 12`, `len(items) == 12`, коды по порядку `["winter-wp", "winter-wn", "winter-wb", "winter-wr", "winter-wq", "winter-wk", "winter-bp", …, "winter-bk"]`, `items[0]["name"] == "Winter | Белая пешка"`, `items[11]["name"] == "Winter | Чёрный король"`, у всех `side`/`piece_type` соответствуют коду; повторный код коллекции → 409 `COLLECTION_CODE_TAKEN`. Черновик не виден публично: `GET /api/v1/collections/winter` (через `client`) → 404.
2. `test_collection_create_validation` — 11 фигур → 422; 12 фигур с повтором `wP` (и без `bK`) → 422; `rarity: "bogus"` → 422; `asset` с полем `light` → 422.
3. `test_collection_lifecycle` — создать коллекцию; кейс `POST /api/v1/admin/cases` `{code:"winter-case", name:"Winter", price:50}` → 201, `status == "draft"`, `drops == []`, `collections == []`; `POST /cases/{id}/drops/auto` `{collection_ids:[winter_id]}` → `len(drops) == 12`, `collections == [{"code":"winter","name":"Winter"}]`; активация при `draft`-коллекции → 400 `CASE_NOT_READY`; выпуск коллекции → `released`; повторный выпуск → 400 `COLLECTION_NOT_DRAFT`; активация → `status == "active"`; повторная активация → 400 `CASE_NOT_READY`; кейс виден в `GET /api/v1/cases` с `collections == [{"code":"winter","name":"Winter"}]`; `PUT drops` у активного → 400 `CASE_LOCKED`; `DELETE` активного → 400 `CASE_LOCKED`; снятие коллекции → `retired`, кейс в `GET /api/v1/admin/cases` имеет `status == "closed"`, а в `admin_audit` у действия `collection.retire` payload `{"closed_case_ids": [case_id]}`; повторное снятие → 400 `COLLECTION_NOT_RELEASED`; активация закрытого (коллекция retired) → 400 `CASE_NOT_READY`.
4. `test_mixed_case` — создать и выпустить две коллекции `winter` и `summer`; кейс с `drops/auto` `{collection_ids:[winter_id, summer_id]}` → 24 дропа, `collections` — обе в порядке возрастания id; повтор id `{collection_ids:[1, 1]}` → 422; `{collection_ids:[999]}` → 404 `COLLECTION_NOT_FOUND`; ручные дропы `PUT /cases/{id}/drops` `[{"item_def_id": 1, "weight": 5}, {"item_def_id": <первый скин winter>, "weight": 5}]` → 200, `len(drops) == 2`, `collections` = genesis и winter; `[{"item_def_id": 99999, "weight": 1}]` → 400 `DROP_ITEM_NOT_AVAILABLE`; активация → `active`; `POST /close` → `closed`; `POST /close` ещё раз → 400 `CASE_NOT_ACTIVE`; `POST /activate` → `active` снова.
5. `test_retired_collection_not_droppable` — коллекция создана, выпущена, снята; новый кейс: `drops/auto` с её id → 400 `DROP_ITEM_NOT_AVAILABLE`; `PUT drops` с её скином → 400 `DROP_ITEM_NOT_AVAILABLE`.
6. `test_item_def_patch` — у черновика `PATCH /api/v1/admin/item-defs/{id}` `{"rarity":"mythic","value":999,"name":"X","asset":{"type":"stub","color":"#123456"},"is_upgrade_target":false}` → 200, поля изменились; `{"side":"b"}` → 422; `{"piece_type":"Q"}` → 422; после выпуска `{"rarity":"rare"}` → 400 `ITEM_DEF_LOCKED`, а `{"value": 77, "name": "Y"}` → 200. Удалённые эндпоинты: `POST /api/v1/admin/collections/{id}/items` → 404 или 405; `DELETE /api/v1/admin/item-defs/{id}` → 405.
7. `test_delete_draft_collection` — черновик-коллекция, черновик-кейс с её дропами (`drops/auto`); `DELETE /admin/collections/{id}` → 204; кейс остался, `drops == []`; удаление выпущенной (`/admin/collections/1`) → 400 `COLLECTION_NOT_DRAFT`.
8. `test_admin_lists` — `GET /api/v1/admin/item-defs` содержит 12 скинов genesis + 12 скинов созданного черновика (всего 24); затем выпусти и сними созданную коллекцию — теперь 12 (только genesis). `GET /api/v1/admin/cases` — кейс genesis первым с `status == "active"` и 12 дропами.
9. `test_grant_item_and_audit` — сохранить существующий тест, заменив коды скинов по таблице и удалив проверки, связанные с удалёнными эндпоинтами; выдача скина из черновой коллекции → 400 `ITEM_DEF_NOT_AVAILABLE`.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_catalog_admin.py` — все тесты проходят.

# Новые сид-данные (одинаковы в каждом тесте, `tests/conftest.py` их вставляет)
Коллекция `genesis` (id 1, released). 12 скинов, id и код:
| id | code | side | piece_type | rarity | value |
|---|---|---|---|---|---|
| 1 | genesis-wp | w | P | common | 20 |
| 2 | genesis-wn | w | N | uncommon | 60 |
| 3 | genesis-wb | w | B | uncommon | 60 |
| 4 | genesis-wr | w | R | rare | 150 |
| 5 | genesis-wq | w | Q | epic | 500 |
| 6 | genesis-wk | w | K | legendary | 1500 |
| 7 | genesis-bp | b | P | common | 20 |
| 8 | genesis-bn | b | N | uncommon | 60 |
| 9 | genesis-bb | b | B | uncommon | 60 |
| 10 | genesis-br | b | R | rare | 150 |
| 11 | genesis-bq | b | Q | epic | 500 |
| 12 | genesis-bk | b | K | legendary | 1500 |
Имена: `"Genesis | Белая пешка"`, `"Genesis | Белый конь"`, … `"Genesis | Чёрный король"`. asset белых `{"type":"stub","color":"#ffffff"}`, чёрных `{"type":"stub","color":"#ffc93c"}`.
Один кейс: id 1, code `genesis`, name `Genesis`, price 100, status `active`, дропы — все 12 скинов, веса: common 3996000, uncommon 399500, rare 160000, epic 32000, legendary 10000 (сумма 9 994 000). Скинов досок и мифических скинов НЕТ.

# Замена старых кодов (сохраняет value)
| старый | новый |
|---|---|
| genesis-pawn-chalk | genesis-wp |
| genesis-knight-chalk, genesis-bishop-chalk, genesis-board-paper | genesis-bp |
| genesis-board-porcelain | genesis-wn |
| genesis-pawn-frost | genesis-wr |
| genesis-knight-frost | genesis-br |
| genesis-queen-snow | genesis-wq |
| genesis-pawn-snow, genesis-board-marble | genesis-bq |
| genesis-board-albion (mythic 5000) | genesis-wk, но в начале теста выставить ему value 5000: `async with SessionLocal() as s, s.begin(): await s.execute(update(ItemDef).where(ItemDef.code == "genesis-wk").values(value=5000))` |
Если тест проверял `kind`, `piece_type`, имя, редкость или слот старого скина — поменять ожидание на значение нового скина из таблицы выше. Старые кейсы `genesis-pieces` (id 1) и `genesis-boards` (id 2) заменены одним кейсом id 1.

# Правила
- Контракт: `docs/contracts-collections.md`. Код приложения (`backend/app/**`) НЕ менять — только тесты из «Область». Если тест падает из-за кода приложения, а не теста — не «чинить» тест под баг: оставить тест правильным по контракту и описать расхождение в SUMMARY.
- Не удалять тесты и не ослаблять проверки, кроме тех, что проверяют удалённое (доски, `kind`, удалённые эндпоинты).
- Проверка: `bash scripts/test_isolated.sh <твои файлы тестов>` (например `bash scripts/test_isolated.sh tests/test_market.py`; пути — относительно `backend/`). Это Docker, ~1–2 минуты. Должно пройти без `failed`/`error`. Другие файлы тестов сейчас могут падать — их чинят параллельно, не трогай.
- Если что-то не сходится — остановиться и описать в SUMMARY, не придумывать.
