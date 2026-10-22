# Контракт: коллекции v2 (12 фигур) и кейсы v2

Заменяет разделы 4.1, 4.2, 4.4, 4.5 `docs/TZ.md` и соответствующие эндпоинты 9.7/админки. Всё, что здесь не упомянуто (экземпляры, wear, апгрейд, маркет-логика, дарение), не меняется.

## 1. Модель

**Коллекция** — ровно 12 скинов фигур одного стиля: по одному на каждую пару `(side, piece_type)`, где `side ∈ {w, b}` (белые, чёрные), `piece_type ∈ {P, N, B, R, Q, K}`.
- Скинов вне коллекции нет. Неполных коллекций нет: коллекция создаётся сразу с 12 скинами одним запросом. Добавлять и удалять отдельные скины нельзя.
- Скинов досок нет. Доска у всех стандартная (`DEFAULT_BOARD` во фронте).
- Редкость и ценность задаются вручную для каждого из 12 скинов, ограничений на сочетания нет.
- Статусы коллекции прежние: `draft` → `released` → `retired`.

**Кейс** не принадлежит коллекции. Дропы кейса — любые скины любых коллекций.
- «Кейс коллекции» — кейс, все дропы которого из одной коллекции. «Смешанный кейс» — дропы из нескольких. Это не отдельный тип, а производное от дропов (`collections` в выдаче).
- Статусы кейса: `draft` → `active` ⇄ `closed`.

## 2. Схема БД (миграция `0006`)

Миграция **удаляет все текущие предметы**: `DELETE FROM` `item_transfers`, `market_listings`, `loadouts`, `inventory_items`, `case_drops`, `cases`, `item_defs`, `collections` (в этом порядке), затем меняет схему и вставляет новую Genesis из `app.seed_data.genesis_rows()`, затем `setval` последовательностей `collections`, `item_defs`, `cases` (как в 0003).

`item_defs`:
- удалить колонку `kind` и ограничения `ck_item_defs_kind_piece_type_consistency`, `ck_item_defs_kind_whitelist`;
- добавить `side CHAR(1) NOT NULL`, `CHECK (side IN ('w','b'))` с именем `ck_item_defs_side_whitelist`;
- `piece_type` → `NOT NULL`; заменить `ck_item_defs_piece_type_whitelist` на `piece_type IN ('P','N','B','R','Q','K')`;
- `UNIQUE (collection_id, side, piece_type)` с именем `uq_item_defs_collection_id_side_piece_type`.

`cases`:
- удалить `collection_id` (FK `fk_cases_collection_id_collections`, индекс `ix_cases_collection_id`) и `is_active`;
- добавить `status TEXT NOT NULL DEFAULT 'draft'`, `CHECK (status IN ('draft','active','closed'))` с именем `ck_cases_status_whitelist`.

`loadouts`: заменить `ck_loadouts_slot_whitelist` на `slot IN ('wP','wN','wB','wR','wQ','wK','bP','bN','bB','bR','bQ','bK')`.

`downgrade`: те же `DELETE FROM`, обратное изменение схемы (`kind` возвращается как `TEXT NOT NULL`, `piece_type` nullable, у `cases` — `collection_id INTEGER NOT NULL` с FK и индексом и `is_active BOOLEAN NOT NULL DEFAULT true`, старый whitelist слотов). Данные не восстанавливаются.

Миграция 0003 должна по-прежнему работать на чистой БД: старые сид-данные переносятся без изменений в `backend/app/seed_data_v1.py` (функция `genesis_rows_v1()`), 0003 импортирует их оттуда.

## 3. Имена и коды скинов (сервер генерирует сам)

- `code` = `f"{collection.code}-{side}{piece_type.lower()}"`, например `genesis-wn`, `genesis-bk`.
- `name` = `f"{collection.name} | {PIECE_NAMES[side + piece_type]}"`; после создания редактируется.
- `PIECE_NAMES` (в `app/seed_data.py`, используется и сидом, и админкой):
  `wP` «Белая пешка», `wN` «Белый конь», `wB` «Белый слон», `wR` «Белая ладья», `wQ` «Белый ферзь», `wK` «Белый король», `bP` «Чёрная пешка», `bN` «Чёрный конь», `bB` «Чёрный слон», `bR` «Чёрная ладья», `bQ` «Чёрный ферзь», `bK` «Чёрный король».
- `SIDES = ("w", "b")`, `PIECE_TYPES = ("P", "N", "B", "R", "Q", "K")`. Канонический порядок 12 скинов: сначала `w` по `PIECE_TYPES`, затем `b`.

## 4. Сид Genesis (`app/seed_data.py::genesis_rows()`)

Одна коллекция `{"id": 1, "code": "genesis", "name": "Genesis", "description": "Первая коллекция. Скины-заглушки.", "status": "released", "released_at": now}`.

12 скинов, `id` 1…12 в каноническом порядке (`wP`=1 … `wK`=6, `bP`=7 … `bK`=12), `collection_id` 1, `is_upgrade_target` true. Редкость по типу фигуры (одинаково у обеих сторон): P `common`, N `uncommon`, B `uncommon`, R `rare`, Q `epic`, K `legendary`. `value` = `RARITY_VALUES[rarity]` (таблица прежняя). `asset`: белые `{"type": "stub", "color": "#ffffff"}`, чёрные `{"type": "stub", "color": "#ffc93c"}`.

Один кейс `{"id": 1, "code": "genesis", "name": "Genesis", "price": 100, "status": "active", "sort": 1}`. Дропы — все 12 скинов, веса по `auto_weights` с весами редкостей по умолчанию: `GENESIS_WEIGHTS = {"common": 3996000, "uncommon": 399500, "rare": 160000, "epic": 32000, "legendary": 10000}` (вес скина = `GENESIS_WEIGHTS[rarity]`).

Возвращает `{"collections": [...], "item_defs": [...], "cases": [...], "case_drops": [...]}` — как раньше.

## 5. Правила

**Коллекция:**
- Создание (`POST /admin/collections`): статус `draft` и 12 скинов в одной транзакции.
- Выпуск: только из `draft` (иначе `400 COLLECTION_NOT_DRAFT`). Других условий нет: полнота гарантирована созданием.
- Снятие: только из `released` (иначе `400 COLLECTION_NOT_RELEASED`). Все кейсы со статусом `active`, у которых есть дроп из этой коллекции, переходят в `closed`.
- Удаление: только `draft` (иначе `400 COLLECTION_NOT_DRAFT`). Удаляет дропы с её скинами из всех кейсов, затем скины, затем коллекцию.

**Скин (`PATCH /admin/item-defs/{id}`):** поля `name`, `rarity`, `value`, `asset`, `is_upgrade_target`. `rarity` — только пока коллекция `draft`, иначе `400 ITEM_DEF_LOCKED` «После выпуска можно менять только name, asset, value, is_upgrade_target». `side`, `piece_type`, `code` не меняются никогда (полей нет во входной схеме).

**Кейс:**
- Создание: статус `draft`, без дропов.
- `PATCH`: `name`, `price`, `sort` — в любом статусе.
- Дропы (`PUT …/drops`, `POST …/drops/auto`): только `draft`, иначе `400 CASE_LOCKED` «Дропы можно менять только у черновика кейса». Каждый скин должен существовать и его коллекция не `retired`, иначе `400 DROP_ITEM_NOT_AVAILABLE` «Скин недоступен для кейса».
- Активация (`POST …/activate`): из `draft` или `closed`. Нужен хотя бы один дроп, и коллекции всех дропов `released`, иначе `400 CASE_NOT_READY` «Кейс не готов: нет дропов или есть скины невыпущенных коллекций». Из `active` → `400 CASE_NOT_READY`.
- Закрытие (`POST …/close`): только из `active`, иначе `400 CASE_NOT_ACTIVE` «Кейс не активен».
- Удаление: только `draft`, иначе `400 CASE_LOCKED`.
- Публично виден и открывается только `active`. `draft` — `404 CASE_NOT_FOUND` везде; `closed` — `GET /cases/{id}` → `404 CASE_NOT_FOUND`, `POST /cases/{id}/open` → `400 CASE_NOT_AVAILABLE`.

**Экипировка:** 12 слотов `wP…wK`, `bP…bK`. Предмет подходит в слот ⇔ `slot == def.side + def.piece_type`, иначе `400 ITEM_SLOT_MISMATCH`.

**Снапшот в партию:** при старте `white_loadout` = белые слоты игрока белыми, `black_loadout` = чёрные слоты игрока чёрными, ключи — **без префикса стороны**: `{"P": {code, name, rarity, asset}, …}`. Формат снапшота, `game_view`, повтор и `frontend/js/pieces.js::pieceColor` не меняются.

## 6. API (префикс `/api/v1`)

### 6.1 Выходные схемы

`ItemDefOut`: `{id, code, name, side, piece_type, rarity, value, asset, collection: {code, name}}` — поле `kind` удалено, `side: "w"|"b"`, `piece_type` не null, `asset` только `{"type":"stub","color":"#rrggbb"}`.

`LoadoutOut`: 12 полей `wP, wN, wB, wR, wQ, wK, bP, bN, bB, bR, bQ, bK`, каждое `ItemOut | null`. `ItemOut.equipped_slot` — один из 12 слотов или `null`.

`CaseOut`: `{id, code, name, price, collections: [{code, name}]}` — список различных коллекций дропов, по возрастанию `collection.id`. `CaseDetailOut` = `CaseOut` + `drops` (как раньше).

`AdminCaseOut`: `{id, code, name, price, status, sort, collections: [{code, name}], drops: [{item_def_id, weight}]}`.

`AdminCollectionOut`: `{id, code, name, description, status, created_at, released_at, retired_at, items_count}` (поле `cases_count` удалено). `AdminCollectionDetailOut` = `AdminCollectionOut` + `items: [ItemDefOut]` в каноническом порядке (поле `cases` удалено).

`CollectionDetailOut` (публичный): `items` в каноническом порядке.

### 6.2 Входные схемы

`PieceIn`: `{side: "w"|"b", piece_type: P|N|B|R|Q|K, rarity, value: 1…10 000 000, asset: {"type":"stub","color":"#rrggbb"}, is_upgrade_target: bool = true}`.

`CollectionCreateIn`: `{code, name, description, pieces: [PieceIn]}` — ровно 12 элементов, каждая пара `(side, piece_type)` ровно один раз, иначе `422 VALIDATION_ERROR`.

`ItemDefPatchIn`: `{name?, rarity?, value?, asset?, is_upgrade_target?}`.

`CaseCreateIn`: `{code, name, price, sort = 0}`. `CasePatchIn`: `{name?, price?, sort?}`.

`AutoDropsIn`: `{collection_ids: [int]}` — от 1 до 20 различных id. Все коллекции должны существовать (иначе `404 COLLECTION_NOT_FOUND`) и не быть `retired` (иначе `400 DROP_ITEM_NOT_AVAILABLE`). Веса — `auto_weights` по всем скинам этих коллекций вместе.

### 6.3 Эндпоинты

Игрок / публично:
| Метод | Путь | Изменение |
|---|---|---|
| GET | `/inventory?side=&slot=&sort=` | фильтр `kind` заменён на `side` (`w`/`b`); `slot` — один из 12 |
| GET | `/loadout`, PUT `/loadout/{slot}` | 12 слотов |
| GET | `/cases` | только `status = 'active'`, порядок `sort, id` |
| GET | `/cases/{id}`, POST `/cases/{id}/open` | правила п. 5 |
| GET | `/market?collection=&side=&piece_type=&rarity=&def_id=&sort=&cursor=` | фильтр `kind` заменён на `side` |

Админ:
| Метод | Путь | |
|---|---|---|
| GET | `/admin/collections` | `[AdminCollectionOut]` |
| GET | `/admin/collections/{id}` | `AdminCollectionDetailOut` |
| POST | `/admin/collections` | `CollectionCreateIn` → 201 `AdminCollectionDetailOut` |
| PATCH | `/admin/collections/{id}` | без изменений |
| DELETE | `/admin/collections/{id}` | п. 5 |
| POST | `/admin/collections/{id}/release`, `/retire` | п. 5, → `AdminCollectionOut` |
| PATCH | `/admin/item-defs/{id}` | `ItemDefPatchIn` → `ItemDefOut` |
| GET | `/admin/item-defs` | **новый**: все скины коллекций не `retired` (включая `draft`), порядок `collection_id`, затем канонический → `[ItemDefOut]` |
| GET | `/admin/cases` | **новый**: все кейсы, порядок `sort, id` → `[AdminCaseOut]` |
| POST | `/admin/cases` | **новый путь** (был `/admin/collections/{id}/cases`): `CaseCreateIn` → 201 `AdminCaseOut` |
| PATCH | `/admin/cases/{id}` | `CasePatchIn` → `AdminCaseOut` |
| DELETE | `/admin/cases/{id}` | 204 |
| PUT | `/admin/cases/{id}/drops` | `[{item_def_id, weight}]` → `AdminCaseOut` |
| POST | `/admin/cases/{id}/drops/auto` | `AutoDropsIn` → `AdminCaseOut` |
| POST | `/admin/cases/{id}/activate`, `/close` | **новые** → `AdminCaseOut` |

Удалены: `POST /admin/collections/{id}/items`, `DELETE /admin/item-defs/{id}`, `POST /admin/collections/{id}/cases`.

Все действия админа пишутся в `admin_audit`: `collection.create` (payload — тело запроса), `collection.patch`, `collection.delete`, `collection.release`, `collection.retire` (payload `{"closed_case_ids": [...]}`), `item_def.patch`, `case.create`, `case.patch`, `case.delete`, `case.drops.set`, `case.drops.auto` (payload `{"collection_ids": [...]}`), `case.activate`, `case.close`.

## 7. Фронт

- `pieces.js`: `boardColors()` всегда возвращает копию `DEFAULT_BOARD` (скинов досок нет).
- Карточка скина (`items.js`): глиф `glyph(def.piece_type, def.side === 'b' ? 'black' : 'white')`; ветки доски нет. Подписи слотов: `wP` «Белая пешка» … `bK` «Чёрный король» (как `PIECE_NAMES`).
- Инвентарь: 12 слотов в два ряда (белые, чёрные); фильтр «Все / Белые / Чёрные» (`side`); «Надеть» шлёт `PUT /loadout/{def.side + def.piece_type}`.
- Маркет: фильтр вида заменён на сторону («Все / Белые / Чёрные», параметр `side`).
- Список кейсов: подпись `«Коллекция X»`, если в `collections` одна, иначе `«Смешанный: X, Y, …»`.
- Админка: вкладка «Коллекции» — создание коллекции формой из 12 строк (сторона и фигура фиксированы; редкость, ценность, цвет), карточка с 12 скинами и правкой; без кейсов. Новая вкладка «Кейсы» — список, создание, правка, дропы вручную и автоматом по выбранным коллекциям, активация, закрытие, удаление.
