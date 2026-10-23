# Контракт предметов v3: наборы, коллекции, доски, базовые скины, магазин кейсов, ежедневная награда

Формат `asset` и картинки скинов — в `docs/contracts-skins.md` (заменяет все `stub` ниже).

Заменяет разделы 4.1–4.5 `docs/TZ.md`, эндпоинты предметов и бонуса из §9 и контракт v2 (история — в git). Без изменений остаются: wear/exterior скинов, формула апгрейда, комиссия и логика покупки лота на маркете, trade hold, лента анимации открытия.

## 1. Модель

- **Набор** (`item_sets`) — перечень коллекций и досок. Коллекций и досок вне набора нет. Статусы есть **только у набора**: `draft` → `released` → `retired`. Коллекции и доски добавляются и удаляются только пока набор `draft`.
- **Коллекция** — ровно 12 скинов фигур (`side ∈ {w,b}` × `piece_type ∈ {P,N,B,R,Q,K}`), создаётся одним запросом целиком (как в v2). Принадлежит ровно одному набору.
- **Доска** — скин доски, принадлежит набору напрямую (не коллекции). Создаётся по одной.
- **Скин** (`item_defs`) — `kind ∈ {piece, board}`. У `piece`: `collection_id`, `side`, `piece_type` не null. У `board`: все три null. `set_id` есть у обоих.
- **Базовый набор** — ровно один набор с `is_base = true` (код `base`), создаётся миграцией, через API не создаётся, не удаляется и не снимается. Его 13 скинов (12 фигур + доска) выдаются каждому игроку при регистрации (`source = 'base'`, `wear = 0`) и сразу экипируются. **Базовый предмет** (`source = 'base'`): нельзя выставить на маркет, подарить, использовать во входах апгрейда (`400 ITEM_BOUND` «Базовый предмет нельзя передать или апгрейдить»). Скины базового набора не бывают целью апгрейда, дропом кейса, выдачей админа.
- **Экипировка** — 13 слотов: `wP wN wB wR wQ wK bP bN bB bR bQ bK board`. Слот можно очистить. **В бой нельзя, пока не заполнены все 13 слотов** (`400 LOADOUT_INCOMPLETE` «Экипируйте скины на все фигуры и доску»): проверка при постановке в очередь, создании инвайта, принятии инвайта и в `create_game` для обоих игроков.
- **Кейс** (`cases`) — товар магазина. `kind`: `set` (по набору, `set_id`), `collection` (по коллекции, `collection_id`), `custom` (дропы — любые скины из любых наборов). Статусы: `draft` → `on_sale` ⇄ `off_sale`. Лимиты (необязательные): тираж `stock_limit` (после `stock_limit` продаж статус сам становится `off_sale`) и окно продажи `sale_starts_at` / `sale_ends_at` (вне окна кейс не продаётся и не виден в магазине; статус не меняется).
- **Купленный кейс — предмет инвентаря** (`inventory_items` с `case_id`), автоматически не открывается. Его можно открыть, продать на маркете, подарить; апгрейдить нельзя (`400 ITEM_NOT_UPGRADABLE` «Кейс нельзя апгрейдить»). Открыть можно **всегда**, даже если кейс снят с продажи или набор снят с выпуска: дропы кейса заморожены с момента выхода из `draft`.
- **Ежедневная награда** — после `daily_reward_wins` (3) побед за текущие сутки UTC игрок жмёт «Забрать» и получает **один кейс-предмет**, выбранный случайно по весам из пула (`daily_reward_pool`, задаёт админ). Одна награда в сутки UTC. Старый бонус ◈ по кулдауну (`/me/daily-bonus`) удалён.

## 2. Схема БД (миграция `0007`)

Миграция удаляет все предметы: `DELETE FROM` `item_transfers`, `market_listings`, `loadouts`, `inventory_items`, `case_drops`, `cases`, `item_defs`, `collections` (в этом порядке). Пользователи, партии, леджер, броски остаются.

`item_sets` (новая): `id serial pk`, `code text unique` (`^[a-z0-9-]{2,40}$`), `name text`, `description text`, `status text default 'draft'` check `IN ('draft','released','retired')`, `is_base bool not null default false`, `created_at`, `released_at null`, `retired_at null`. Частичный unique-индекс `uq_item_sets_single_base` на `(is_base) WHERE is_base`.

`collections`: удалить `status`, `released_at`, `retired_at` и `ck_collections_status_whitelist`; добавить `set_id int not null` FK → `item_sets`, индекс `ix_collections_set_id`.

`item_defs`:
- добавить `kind text not null` check `IN ('piece','board')` (`ck_item_defs_kind_whitelist`), `set_id int not null` FK → `item_sets` (индекс `ix_item_defs_set_id`);
- `collection_id`, `side`, `piece_type` → nullable; заменить `ck_item_defs_side_whitelist`, `ck_item_defs_piece_type_whitelist` на версии с `IS NULL OR …`;
- check `ck_item_defs_kind_shape`: `(kind = 'piece' AND collection_id IS NOT NULL AND side IS NOT NULL AND piece_type IS NOT NULL) OR (kind = 'board' AND collection_id IS NULL AND side IS NULL AND piece_type IS NULL)`;
- unique `(collection_id, side, piece_type)` остаётся.

`inventory_items`:
- `item_def_id` → nullable; добавить `case_id int null` FK → `cases`; check `ck_inventory_items_one_kind`: `(item_def_id IS NULL) <> (case_id IS NULL)`;
- `wear` → nullable; заменить `ck_inventory_items_wear_range` на `wear IS NULL OR (wear >= 0 AND wear < 1)`;
- `source` whitelist: `('case','upgrade','admin_grant','base','shop','daily_reward')`.

`loadouts`: слоты — 12 фигур + `'board'`.

`cases`: добавить `kind text not null` check `IN ('set','collection','custom')`, `set_id int null` FK, `collection_id int null` FK, check `ck_cases_kind_ref`: `(kind = 'set' AND set_id IS NOT NULL AND collection_id IS NULL) OR (kind = 'collection' AND collection_id IS NOT NULL AND set_id IS NULL) OR (kind = 'custom' AND set_id IS NULL AND collection_id IS NULL)`; `stock_limit int null` check `> 0`, `sold_count int not null default 0` check `>= 0`, `sale_starts_at timestamptz null`, `sale_ends_at timestamptz null`; `status` whitelist → `('draft','on_sale','off_sale')`.

`market_listings`: `item_def_id` → nullable, добавить `case_id int null` FK → `cases`, check `(item_def_id IS NULL) <> (case_id IS NULL)`, индекс `ix_market_listings_case_id_status_price` на `(case_id, status, price)`.

`daily_reward_pool` (новая): `case_id int pk` FK → `cases`, `weight int not null` check `> 0`.

`users`: удалить `last_daily_bonus_at`; добавить `last_daily_reward_on date null`.

`rolls.kind` whitelist: + `'daily_reward'`.

`settings`: удалить ключи `daily_bonus`, `daily_bonus_cooldown_h`; добавить `daily_reward_wins = 3`.

После схемы: вставить сид (п. 4), `setval` для `item_sets`, `collections`, `item_defs`, `cases`; затем **каждому существующему пользователю** выдать 13 базовых предметов и экипировать их (одним `INSERT … SELECT` на предметы и одним на `loadouts`).

`downgrade`: те же `DELETE FROM` + `DELETE FROM daily_reward_pool`, обратная схема до состояния 0006 (данные не восстанавливаются, `users.last_daily_bonus_at` возвращается пустым, ключи настроек возвращаются со старыми значениями 200 и 24).

Новые таблицы `item_sets`, `daily_reward_pool` — в `_TRUNCATE_SQL` в `backend/tests/conftest.py`.

## 3. Коды и имена

- Константы в `app/seed_data.py`: `SIDES`, `PIECE_TYPES`, `PIECE_NAMES`, `CANONICAL_SLOTS` (12, как в v2), **`LOADOUT_SLOTS = CANONICAL_SLOTS + ("board",)`**, `item_code(collection_code, side, piece_type)`, `item_name(collection_name, side, piece_type)` — как в v2.
- Скины фигур: код и имя генерирует сервер (как v2). Доски: `code` и `name` задаёт админ.

## 4. Сид (`app/seed_data.py::seed_rows()` → `{"item_sets", "collections", "item_defs", "cases", "case_drops", "daily_reward_pool"}`)

**Базовый набор**: `item_sets` id 1 `{"code": "base", "name": "Базовый", "description": "Стартовые скины каждого игрока.", "status": "released", "is_base": True, "released_at": now}`. Коллекция id 1 `{"set_id": 1, "code": "base", "name": "Базовая", "description": ""}`. Скины id 1–12 — коллекция `base` в каноническом порядке, `rarity "common"`, `value 1`, `is_upgrade_target False`, asset белых `{"type":"stub","color":"#f4f6ff"}`, чёрных `{"type":"stub","color":"#ff5470"}`. Скин id 13 — доска `{"kind": "board", "set_id": 1, "code": "base-board", "name": "Базовая доска", "rarity": "common", "value": 1, "asset": {"type":"stub","light":"#454f77","dark":"#262e4d"}, "is_upgrade_target": False}`.

**Genesis**: набор id 2 `{"code":"genesis","name":"Genesis","description":"Первый набор. Скины-заглушки.","status":"released","is_base":False}`. Коллекция id 2 `{"set_id":2,"code":"genesis","name":"Genesis","description":""}`, скины id 14–25 — как v2 (`GENESIS_RARITY`, `RARITY_VALUES`, белые `#ffffff`, чёрные `#ffc93c`, `is_upgrade_target True`). Доски: id 26 `{"code":"genesis-board-paper","name":"Genesis | Бумага","rarity":"uncommon","value":60,"asset":{"type":"stub","light":"#ffffff","dark":"#e5e5e5"}}`, id 27 `{"code":"genesis-board-albion","name":"Genesis | Альбион","rarity":"mythic","value":5000,"asset":{"type":"stub","light":"#ffffff","dark":"#c9d1e0"}}`, обе `is_upgrade_target True`, `set_id 2`.

Кейс id 1 `{"code":"genesis","name":"Genesis","kind":"set","set_id":2,"collection_id":None,"price":100,"status":"on_sale","sort":1,"stock_limit":None,"sold_count":0,"sale_starts_at":None,"sale_ends_at":None}`; дропы — все скины id 14–27, вес `GENESIS_WEIGHTS[rarity]` = `{"common":3996000,"uncommon":319600,"rare":160000,"epic":32000,"legendary":10000,"mythic":6000}` (сумма 10 000 000; это результат `auto_weights` при весах по умолчанию).

Пул награды: `[{"case_id": 1, "weight": 1}]`.

Константы: `BASE_SET_ID = 1`, `BASE_DEF_IDS = tuple(range(1, 14))` (порядок = `LOADOUT_SLOTS`).

## 5. Правила

**Набор:** создание — `draft`. Выпуск: только `draft` (иначе `400 SET_NOT_DRAFT` «Действие только для черновика»), нужна хотя бы одна коллекция или доска (иначе `400 SET_EMPTY` «В наборе нет коллекций и досок»). Снятие: только `released` (иначе `400 SET_NOT_RELEASED` «Снять можно только выпущенный»); все кейсы `on_sale`, у которых есть дроп из этого набора, → `off_sale`. Удаление: только `draft`; удаляет дропы со скинами набора из всех кейсов, кейсы с `set_id`/`collection_id` этого набора (они могут быть только `draft`), скины, коллекции, набор. Базовый набор: снятие/удаление → `400 SET_IS_BASE` «Базовый набор нельзя менять».

**Коллекция / доска:** добавить или удалить — только в `draft`-наборе (`400 SET_NOT_DRAFT`). Удаление коллекции удаляет её скины и их дропы. Удаление скина фигуры отдельно запрещено (`400 ITEM_DEF_LOCKED`). Правка скина (`PATCH /admin/item-defs/{id}`): `name`, `rarity` (только `draft`-набор, иначе `400 ITEM_DEF_LOCKED`), `value`, `asset` (вид должен соответствовать `kind`, иначе `422 VALIDATION_ERROR`), `is_upgrade_target`.

**Кейс:**
- Создание — `draft`, `sold_count = 0`. `kind = set` требует существующий небазовый `set_id`, `collection` — `collection_id` из небазового набора (иначе `404 SET_NOT_FOUND` / `404 COLLECTION_NOT_FOUND`, базовый → `400 SET_IS_BASE`).
- Дропы — только в `draft` (`400 CASE_LOCKED` «Дропы можно менять только у черновика кейса»). Допустимые скины: из небазовых не `retired` наборов; для `kind = set` — только скины этого набора, для `collection` — только этой коллекции (иначе `400 DROP_ITEM_NOT_AVAILABLE` «Скин недоступен для кейса»). Автовеса (`POST …/drops/auto`): `set` — все скины набора (12 × коллекций + доски), `collection` — 12 скинов коллекции, `custom` — все скины из `set_ids` и `collection_ids` тела (хотя бы один id, иначе `422`); веса — `auto_weights`.
- Публикация (`POST …/publish`): из `draft` или `off_sale`; нужны дропы, все наборы дропов `released`, и если `stock_limit` задан — `sold_count < stock_limit` (иначе `400 CASE_NOT_READY` «Кейс не готов: нет дропов, есть невыпущенные наборы или тираж исчерпан»). Из `on_sale` → `400 CASE_NOT_READY`.
- Снятие (`POST …/unpublish`): только `on_sale` (`400 CASE_NOT_ON_SALE` «Кейс не в продаже»).
- `PATCH`: `name`, `price`, `sort`, `stock_limit` (null или ≥ max(1, `sold_count`), иначе `422`), `sale_starts_at`, `sale_ends_at` (если оба заданы — `starts < ends`, иначе `422`) — в любом статусе.
- Удаление — только `draft` (`400 CASE_LOCKED`); также удаляет его строку из пула награды.
- **Продаётся сейчас** (`on_sale_now`) ⇔ `status = 'on_sale'` и (`sale_starts_at` null или `now ≥ sale_starts_at`) и (`sale_ends_at` null или `now < sale_ends_at`) и (`stock_limit` null или `sold_count < stock_limit`).
- Покупка (`POST /cases/{id}/buy`), одна транзакция: кейса нет или `draft` → `404 CASE_NOT_FOUND`; не `on_sale_now` → `400 CASE_NOT_AVAILABLE` «Кейс сейчас не продаётся»; атомарно `UPDATE cases SET sold_count = sold_count + 1 WHERE id = :id AND status = 'on_sale' AND (stock_limit IS NULL OR sold_count < stock_limit) RETURNING sold_count, stock_limit` (0 строк → `CASE_NOT_AVAILABLE`); если `sold_count == stock_limit` — в этом же запросе/транзакции `status = 'off_sale'`; списание `apply_delta(-price, "case_purchase", ref=str(case.id))`; создание предмета-кейса (`source = 'shop'`, `wear = NULL`). Порядок блокировок: `cases` раньше `users`.
- Открытие (`POST /inventory/{item_id}/open`): `lock_items` предмета (свой, `owned`), не кейс → `400 ITEM_NOT_CASE` «Это не кейс»; дропы кейса (пусто — невозможно, но → `400 CASE_NOT_AVAILABLE`); предмет-кейс → `burned` (`burned_at = now`), снимается со слота не нужно (кейсы не экипируются); бросок и лента — как раньше (`weighted_pick`, порядок RNG прежний, затем `wear` нового скина); новый скин `source = 'case'`, `source_ref = str(case.id)`; `rolls` `kind = 'case_open'`, `input = {"case_id", "inventory_item_id"}`. Баланс не меняется.

**Экипировка:** предмет-кейс в слот → `400 ITEM_SLOT_MISMATCH`. Скин подходит в слот ⇔ (`kind = piece` и `slot == side + piece_type`) или (`kind = board` и `slot == 'board'`).

**Снапшот в партию:** `white_loadout` = белые слоты белого игрока без префикса + `"board"`; `black_loadout` = чёрные слоты чёрного + `"board"`. Формат значения прежний `{code, name, rarity, asset}`.

**Доска в партии:** каждый игрок видит свою доску (`players[you].loadout.board`); зритель — доску белого.

**Маркет и подарки:** предметы-кейсы выставляются и дарятся как скины; базовые → `ITEM_BOUND`.

**Апгрейд:** входы — только скины не `base` (кейс → `ITEM_NOT_UPGRADABLE`, базовый → `ITEM_BOUND`); цель — скин (фигура или доска) из `released` небазового набора с `is_upgrade_target` (иначе `UPGRADE_TARGET_NOT_AVAILABLE`); все входы — из того же набора, что и цель (иначе `400 UPGRADE_SET_MISMATCH` «Апгрейд возможен только внутри одного набора»).

**Ежедневная награда:**
- `wins_today` — число партий `status = 'finished'`, где `result` = цвет игрока, `ply ≥ reward_min_plies`, `finished_at` в текущих сутках UTC (`[00:00, 24:00)` от `clock.now()`).
- `claimed_today` ⇔ `last_daily_reward_on == clock.now().date()` (UTC).
- `POST /me/daily-reward`: блокировка пользователя (`economy.lock_user`); `claimed_today` → `400 DAILY_REWARD_CLAIMED` «Награда за сегодня уже получена»; `wins_today < wins_required` → `400 DAILY_REWARD_NOT_READY` «Нужно победить в N партиях за сегодня» (N = `daily_reward_wins`); пул пуст → `400 DAILY_REWARD_EMPTY` «Пул наград пуст»; иначе `r = get_rng().random()`, `weighted_pick` по пулу (отсортирован по `case_id`), предмет-кейс `source = 'daily_reward'`, `rolls` `kind = 'daily_reward'` (`chance = weight / Σ`, `input = {"pool": [[case_id, weight], …]}`, `outcome = {"case_id", "item_id"}`), `last_daily_reward_on = today`.
- Пул: кейсы не `draft`. Кейс в пуле может быть снят с продажи — награда всё равно выдаётся.

## 6. API (префикс `/api/v1`)

### 6.1 Выходные схемы

- `SetRef {code, name}`, `CollectionRef {code, name}`.
- `ItemDefOut {id, code, name, kind: "piece"|"board", side: "w"|"b"|null, piece_type|null, rarity, value, asset, set: SetRef, collection: CollectionRef|null}`; `asset` — `SkinAsset {type:"png", image}` (`docs/contracts-skins.md`).
- `CaseRefOut {id, code, name, kind, price}`.
- `ItemOut {id, kind: "skin"|"case", def: ItemDefOut|null, case: CaseRefOut|null, wear: float|null, exterior: str|null, status, equipped_slot|null, source, bound: bool, acquired_at}` — `bound = (source == 'base')`.
- `LoadoutOut` — 13 полей (`wP`…`bK`, `board`) `ItemOut|null` + `complete: bool`.
- `ShopCaseOut {id, code, name, kind, set: SetRef|null, collection: CollectionRef|null, price, stock_limit|null, stock_left|null, sale_starts_at|null, sale_ends_at|null}` (`stock_left = stock_limit − sold_count`).
- `CaseDetailOut` = `ShopCaseOut` + `on_sale_now: bool`, `drops: [{def: ItemDefOut, weight, chance, chance_text}]`.
- `CaseBuyOut {item: ItemOut, balance}`. `CaseOpenOut {item: ItemOut, strip: [int], win_index, defs: {str: ItemDefOut}}`.
- `PublicSetOut {code, name, description, status, released_at, collections_count, boards_count}`; `SetDetailOut {code, name, description, status, released_at, collections: [{code, name, description, items: [ItemDefOut×12]}], boards: [ItemDefOut]}`.
- `CollectionDetailOut {code, name, description, set: SetRef, items: [ItemDefOut×12]}`.
- `DailyRewardOut {wins_today, wins_required, claimed_today, available}` (`available = !claimed && wins ≥ required`); `DailyRewardClaimOut {case: CaseRefOut, item: ItemOut, roll_id}`.
- `MeOut` — без `daily_bonus_available_at`.
- Маркет: `ListingItemOut {id, kind, def: ItemDefOut|null, case: CaseRefOut|null, wear|null, exterior|null}`; `DefMarketOut` прежний; новый `CaseMarketOut {case: CaseRefOut, stats, listings, sales}`.
- Админ: `AdminSetOut {id, code, name, description, status, is_base, created_at, released_at, retired_at, collections_count, boards_count}`; `AdminSetDetailOut` = `AdminSetOut` + `collections: [{id, code, name, description, items: [ItemDefOut×12]}]` + `boards: [ItemDefOut]`; `AdminCaseOut {id, code, name, kind, set: SetRef|null, collection: CollectionRef|null, price, sort, status, stock_limit, sold_count, sale_starts_at, sale_ends_at, on_sale_now, drops: [{item_def_id, weight}]}`; `DailyPoolEntryOut {case: CaseRefOut, weight}`.

### 6.2 Входные схемы

- `SetCreateIn {code, name, description}`, `SetPatchIn {name?, description?}`.
- `CollectionCreateIn {code, name, description, pieces: [PieceIn×12]}` — как v2 (`PieceIn` без изменений); `CollectionPatchIn {name?, description?}`.
- `BoardCreateIn {code, name, rarity, value: 1…10 000 000, asset: SkinAsset, is_upgrade_target = true}`.
- `ItemDefPatchIn {name?, rarity?, value?, asset?: SkinAsset, is_upgrade_target?}`.
- `CaseCreateIn {code, name, price: 1…10 000 000, sort = 0, kind, set_id: int|null = null, collection_id: int|null = null, stock_limit: int|null = null (≥1), sale_starts_at: datetime|null = null, sale_ends_at: datetime|null = null}` — валидатор: поля ссылки по `kind` как в `ck_cases_kind_ref`, окно `starts < ends` если оба.
- `CasePatchIn {name?, price?, sort?, stock_limit?, sale_starts_at?, sale_ends_at?}` (явный `null` у трёх последних — снять лимит).
- `DropIn`/`DropsIn` — как v2. `AutoDropsIn {set_ids: [int] = [], collection_ids: [int] = []}` (до 20 каждого, без повторов).
- `DailyPoolIn` — список `{case_id, weight ≥ 1}` без повторов `case_id`, до 50.
- `GrantItemIn {item_def_id: int|null = null, case_id: int|null = null}` — ровно одно.

### 6.3 Эндпоинты

Игрок / публично:
| Метод | Путь | |
|---|---|---|
| GET | `/sets` | выпущенные и снятые небазовые наборы `[PublicSetOut]`, порядок `released_at desc, id` |
| GET | `/sets/{code}` | `SetDetailOut`; `draft` → `404 SET_NOT_FOUND` «Набор не найден» |
| GET | `/collections/{code}` | `CollectionDetailOut`; набор `draft` → `404 COLLECTION_NOT_FOUND` |
| GET | `/shop` | кейсы `on_sale_now`, порядок `sort, id` → `[ShopCaseOut]` |
| GET | `/cases/{id}` | `CaseDetailOut` любого не `draft` кейса |
| POST | `/cases/{id}/buy` | → `CaseBuyOut` (rate limit `rl:items`) |
| POST | `/inventory/{item_id}/open` | → `CaseOpenOut` (rate limit `rl:items`) |
| GET | `/inventory?kind=piece\|board\|case&side=&slot=&sort=` | `[ItemOut]`, статусы `owned`/`listed` |
| GET | `/loadout`, PUT `/loadout/{slot}` | 13 слотов |
| GET | `/item-defs?upgrade_target=` | скины небазовых наборов не `draft` (с `upgrade_target=true` — только `released` и `is_upgrade_target`) |
| GET / POST | `/me/daily-reward` | `DailyRewardOut` / `DailyRewardClaimOut` |
| GET | `/market?kind=piece\|board\|case&set=&collection=&side=&piece_type=&rarity=&def_id=&case_id=&sort=&page=&limit=` | как раньше + новые фильтры |
| GET | `/market/defs/{def_id}`, `/market/cases/{case_id}` | `DefMarketOut` / `CaseMarketOut` |

Удалены: `GET /collections` (список), `GET /cases` (заменён `/shop`), `POST /cases/{id}/open` (заменён открытием предмета), `POST /me/daily-bonus`.

Админ:
| Метод | Путь | |
|---|---|---|
| GET / POST | `/admin/sets` | `[AdminSetOut]` / `SetCreateIn` → 201 `AdminSetOut` |
| GET / PATCH / DELETE | `/admin/sets/{id}` | `AdminSetDetailOut` / `AdminSetOut` / 204 |
| POST | `/admin/sets/{id}/release`, `/retire` | `AdminSetOut` |
| POST | `/admin/sets/{id}/collections` | `CollectionCreateIn` → 201 `AdminSetDetailOut` |
| PATCH / DELETE | `/admin/collections/{id}` | `CollectionPatchIn` → `AdminSetDetailOut` / 204 |
| POST | `/admin/sets/{id}/boards` | `BoardCreateIn` → 201 `ItemDefOut` |
| PATCH / DELETE | `/admin/item-defs/{id}` | `ItemDefOut` / 204 (только доска в `draft`-наборе) |
| GET | `/admin/item-defs` | скины небазовых не `retired` наборов, порядок `set_id, id` |
| GET / POST | `/admin/cases` | `[AdminCaseOut]` / `CaseCreateIn` → 201 |
| PATCH / DELETE | `/admin/cases/{id}` | |
| PUT | `/admin/cases/{id}/drops` | `DropsIn` |
| POST | `/admin/cases/{id}/drops/auto` | `AutoDropsIn` |
| POST | `/admin/cases/{id}/publish`, `/unpublish` | `AdminCaseOut` |
| GET / PUT | `/admin/daily-reward-pool` | `[DailyPoolEntryOut]` (порядок `case_id`); PUT — `DailyPoolIn`, кейс не найден/`draft` → `400 CASE_NOT_AVAILABLE` |
| POST | `/admin/users/{id}/grant-item` | `GrantItemIn` → `ItemOut`; скин базового или невыпущенного набора / кейс `draft` → `400 ITEM_DEF_NOT_AVAILABLE` |

Удалены: `/admin/collections` (список, создание, release, retire), `/admin/cases/{id}/activate`, `/close`.

Аудит: `set.create`, `set.patch`, `set.delete`, `set.release`, `set.retire` (`{"unpublished_case_ids": [...]}`), `collection.create`, `collection.patch`, `collection.delete`, `board.create`, `item_def.patch`, `item_def.delete`, `case.create`, `case.patch`, `case.delete`, `case.drops.set`, `case.drops.auto`, `case.publish`, `case.unpublish`, `daily_pool.set`, `user.grant_item`.

## 7. Фронт

- `pieces.js`: `boardColors(loadout)` снова читает `loadout.board.asset` (`{light, dark}`), иначе `DEFAULT_BOARD`. `board.js`: доска — `players[you].loadout`, зритель — `players.white.loadout`.
- `items.js`: превью доски возвращается; карточка предмета-кейса; подписи `SLOT_RU` + `board: 'Доска'`, `LOADOUT_SLOTS`.
- Инвентарь: 13 слотов (белые, чёрные, доска), предупреждение «Экипируйте скины на все фигуры и доску — без этого нельзя играть», если `complete === false`; фильтр «Все / Фигуры / Доски / Кейсы»; у кейса кнопка «Открыть» (→ `/case.html?item=<id>`); у базовых — метка «Базовый», без «Продать»/«Подарить».
- Магазин (`/cases.html`, в меню «Магазин»): кейсы из `/shop`, сгруппированы: «Наборы» (`kind = set`), «Коллекции», «Особые» (`custom`); у лимитированных — «Осталось N» и/или «До <дата>»; кнопка «Купить» прямо в карточке и ссылка на страницу кейса.
- `/case.html?id=` — содержимое кейса (дропы с шансами), кнопка «Купить», если `on_sale_now`. `/case.html?item=` — открытие своего кейса-предмета (анимация ленты как раньше).
- Наборы — без отдельной страницы для игрока: на карточке скина подпись «Набор · Коллекция» (`def.set`, `def.collection`).
- Лобби: вместо бонуса — блок «Ежедневная награда»: «Побед сегодня: X / 3», кнопка «Забрать» (активна при `available`), после получения — модалка с выпавшим кейсом и ссылкой «Открыть». Ошибка `LOADOUT_INCOMPLETE` при поиске/инвайте показывается тостом со ссылкой на инвентарь.
- Маркет: фильтр вида «Все / Фигуры / Доски / Кейсы»; карточка лота-кейса; страница `market-item.html?def=` или `?case=`.
- Админка: вкладка «Наборы» (вместо «Коллекции»): наборы → набор (коллекции 12 фигур, доски), выпуск/снятие/удаление; вкладка «Кейсы»: вид кейса, источник, лимиты, дропы, публикация/снятие, пул ежедневной награды; выдача предмета пользователю — скин или кейс.
