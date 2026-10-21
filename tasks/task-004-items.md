# task-004 — Коллекции, скины, кейсы, инвентарь, экипировка, апгрейд, админка каталога

Прочитай перед работой: `docs/TZ.md` **версии 1.1**: разделы 4.1–4.6, 5, 8 (collections … case_drops), 9.7, 9.8, 9.10 (только «Каталог (фаза 4)»).
Маркет и дарение (4.7, 4.8) — **не в этой задаче** (task-005), но статус `listed` и поле `acquired_at` заводятся уже здесь.

## Правила для исполнителя
Те же, что в task-001…003:
- время только через `clock.now()`;
- случайность только через `get_rng()`;
- любой `FOR UPDATE` только с `populate_existing=True`;
- баланс меняется только через `apply_delta`;
- каждое действие админа пишет строку в `admin_audit`.

Порядок блокировок: предметы (`inventory_items`) по возрастанию id, затем пользователь (если меняется баланс).

Если что-то неясно или не сходится — остановись и спроси.

---

## 1. Миграция `alembic/versions/0003_items.py` (руками)

Таблицы ровно по TZ §8:
- `collections`;
- `item_defs`;
- `inventory_items`: статусы `owned | listed | burned`, поле `acquired_at timestamptz not null`;
- `loadouts`;
- `cases`;
- `case_drops`.

Индексы:
- `inventory_items (user_id, status)`;
- `item_defs (collection_id)`;
- `cases (collection_id)`.

Добавить в `settings` (и в `DEFAULTS` в `services/settings.py`):
- `rarity_weights` = `{"common": 7992, "uncommon": 1598, "rare": 320, "epic": 64, "legendary": 20, "mythic": 6}`;
- `market_fee` = `0.05`;
- `market_max_listings` = `50`;
- `trade_hold_hours` = `0`.

### Сид: коллекция Genesis (в той же миграции)
Коллекция `code="genesis"`, `name="Genesis"`, `description="Первая коллекция. Скины-заглушки."`, `status="released"`, `released_at=now()`.

Ценность по редкости: common 20, uncommon 60, rare 150, epic 500, legendary 1500, mythic 5000.

Asset у всех piece_skin — `{"type": "stub", "color": "#ffffff"}`, у всех board_skin — `{"type": "stub", "light": "#ffffff", "dark": "#e5e5e5"}`.

**18 скинов фигур:** для каждого `piece_type` и имени фигуры
`P Пешка / pawn`, `N Конь / knight`, `B Слон / bishop`, `R Ладья / rook`, `Q Ферзь / queen`, `K Король / king`:

| code | name | rarity |
|---|---|---|
| `genesis-{slug}-chalk` | `{Имя} \| Мел` | common |
| `genesis-{slug}-frost` | `{Имя} \| Иней` | rare |
| `genesis-{slug}-snow` | `{Имя} \| Снег` | epic |

Пример: `genesis-knight-frost`, `Конь | Иней`, rare, value 150.

**4 доски:**

| code | name | rarity |
|---|---|---|
| `genesis-board-paper` | `Доска \| Бумага` | common |
| `genesis-board-porcelain` | `Доска \| Фарфор` | uncommon |
| `genesis-board-marble` | `Доска \| Мрамор` | epic |
| `genesis-board-albion` | `Доска \| Альбион` | mythic |

**2 кейса** (`is_active=true`):
- `genesis-pieces`, «Genesis: фигуры», цена 100, `sort=1`. Дропы — все 18 скинов фигур с весами: common **1332000**, rare **53333**, epic **10666** (сумма 8375994; шанс одного common ≈ 15.90%).
- `genesis-boards`, «Genesis: доски», цена 250, `sort=2`. Дропы — 4 доски: common **7992000**, uncommon **1598000**, epic **64000**, mythic **6000** (сумма 9660000).

Это ровно результат формулы автозаполнения из п. 3.4. Тест `test_seed_weights_match_auto_formula` это проверяет.

### Где живут сид-данные
Данные Genesis — **один источник** в `app/seed_data.py`: чистый модуль без БД и I/O, функция `genesis_rows() -> dict[str, list[dict]]` с ключами `collections`, `item_defs`, `cases`, `case_drops`. Id проставлены явно:
- коллекция `id=1`;
- `item_defs` `id=1…22` в порядке: pawn chalk/frost/snow, knight …, bishop …, rook …, queen …, king …, затем board paper/porcelain/marble/albion;
- кейсы `genesis-pieces id=1`, `genesis-boards id=2`.

Его используют двое:
- миграция `0003` (`op.bulk_insert`);
- `conftest.py`: перед каждым тестом `TRUNCATE collections, item_defs, inventory_items, loadouts, cases, case_drops RESTART IDENTITY CASCADE` (вместе с прошлыми таблицами), затем вставка `genesis_rows()`. Так тесты могут свободно менять Genesis.

После вставки с явными id (и в миграции, и в conftest) обязательно сдвинуть последовательности: `SELECT setval(pg_get_serial_sequence('<table>', 'id'), (SELECT max(id) FROM <table>))` для `collections`, `item_defs`, `cases`. Иначе следующая вставка упадёт на дубликате id.

Модели: `app/models/items.py` (`Collection`, `ItemDef`, `InventoryItem`, `Loadout`, `Case`, `CaseDrop`), добавить в `app/models/__init__.py`.

## 2. Схемы `app/schemas/items.py` (`extra="forbid"` у входных)

```python
HexColor = constr(pattern=r"^#[0-9a-fA-F]{6}$")
class PieceAsset(BaseModel): type: Literal["stub"]; color: HexColor
class BoardAsset(BaseModel): type: Literal["stub"]; light: HexColor; dark: HexColor
Rarity = Literal["common", "uncommon", "rare", "epic", "legendary", "mythic"]
PieceType = Literal["P", "N", "B", "R", "Q", "K"]
Slot = Literal["P", "N", "B", "R", "Q", "K", "board"]
```
Валидация `asset` в админке: для `piece_skin` — `PieceAsset`, для `board_skin` — `BoardAsset` (несоответствие → 422 `VALIDATION_ERROR`).

Выходные:
- `CollectionRef {code, name}`
- `ItemDefOut {id, code, name, kind, piece_type, rarity, value, asset, collection: CollectionRef}`
- `ItemOut {id, def: ItemDefOut, wear, exterior, status, equipped_slot: Slot | None, source, acquired_at}`
- `LoadoutOut` — dict `slot → ItemOut | None`, все 7 ключей всегда присутствуют.
- `CaseOut {id, code, name, price, collection: CollectionRef}`
- `CaseDetailOut {..., drops: [{def: ItemDefOut, weight, chance, chance_text}]}`, где `chance_text` — `format_chance` из движка. Дропы отсортированы по `item_def_id`.
- `CaseOpenOut {item: ItemOut, strip: list[int], win_index: int, defs: dict[str, ItemDefOut], balance: int}` (ключи `defs` — строки id).
- `UpgradeIn {input_ids: conlist(int, min_length=1, max_length=50), target_def_id: int}`
- `UpgradePreviewOut {chance, chance_text, allowed, reason}`
- `UpgradeOut {success, chance, chance_text, roll_value, roll_id, burned_ids, item: ItemOut | None}`

`exterior(wear)` → `"FN" | "MW" | "FT" | "WW" | "BS"` по границам TZ 4.3 (левая граница включительно).

## 3. Сервисы

### 3.1 `app/services/items.py`
```python
def item_def_out(d: ItemDef, collection: Collection) -> ItemDefOut
async def item_out(db, item: InventoryItem) -> ItemOut        # equipped_slot из loadouts
async def create_item(db, *, user_id, def_id, source, source_ref, now) -> InventoryItem
    # wear = get_rng().random(); created_at = acquired_at = now
async def lock_items(db, user_id, ids: list[int]) -> list[InventoryItem]
    # SELECT … WHERE id IN ids ORDER BY id FOR UPDATE + populate_existing;
    # если найдено не всё, или чужое, или status != "owned" → AppError(400, "ITEM_NOT_OWNED", ...)
async def unequip_items(db, item_ids: list[int]) -> None       # DELETE FROM loadouts WHERE inventory_item_id IN …
async def loadout_snapshot(db, user_id) -> dict                # {slot: {code, name, rarity, asset}} только занятые слоты
def slot_matches(item_def, slot) -> bool                       # board ↔ board_skin; P..K ↔ piece_skin с тем же piece_type
```

### 3.2 Экипировка — `PUT /loadout/{slot}`
1. `inventory_item_id is None` → удалить строку слота (если есть), вернуть лоадаут.
2. Иначе: `lock_items(db, user.id, [id])` (защита от гонки с апгрейдом); `slot_matches` ложно → 400 `ITEM_SLOT_MISMATCH`.
3. Upsert строки `(user_id, slot) → item_id`.

### 3.3 Снапшот в партию
В `services/games.create_game` после загрузки пользователей:
```python
game.white_loadout = await loadout_snapshot(db, white_id)
game.black_loadout = await loadout_snapshot(db, black_id)
```

### 3.4 `app/services/cases.py`
```python
def auto_weights(item_defs: list[ItemDef], rarity_weights: dict[str, int]) -> dict[int, int]
    # для каждой редкости r, у которой в списке n > 0 скинов: вес каждого = rarity_weights[r] * 1000 // n
def weighted_pick(drops: list[CaseDrop], r: float) -> CaseDrop
    # drops отсортированы по item_def_id; total = Σweight; target = r * total;
    # вернуть первый drop, у которого накопленная сумма > target
async def openable_case(db, case_id) -> tuple[Case, Collection, list[CaseDrop]]
    # нет кейса или его коллекция в draft → 404 CASE_NOT_FOUND (черновики публично не существуют);
    # коллекция retired, кейс не is_active или нет дропов → 400 CASE_NOT_AVAILABLE
async def open_case(db, user, case_id, now) -> CaseOpenOut
```
`open_case`, строго в этом порядке (порядок вызовов `rng.random()` фиксирован, на нём держатся тесты):
1. `openable_case`;
2. `apply_delta(db, user.id, -case.price, "case_purchase", ref=str(case.id))` (`INSUFFICIENT_FUNDS` пробрасывается);
3. `r_win = rng.random()`; `winner = weighted_pick(drops, r_win)`;
4. `win_index = 45 + int(rng.random() * 10)`;
5. лента из 60 позиций: для `i` от 0 до 59, если `i == win_index` → `winner.item_def_id`, иначе `weighted_pick(drops, rng.random()).item_def_id`;
6. `create_item(source="case", source_ref=str(case.id))` — здесь расходуется следующий `rng.random()` на `wear`;
7. `record_roll(kind="case_open", ref=str(case.id), chance=winner.weight/total, roll_value=r_win, input={"case_id", "price"}, outcome={"item_def_id", "item_id"})`;
8. ответ: `defs` — все def, встречающиеся в ленте; `balance` — новый баланс.

### 3.5 `app/services/upgrade.py`
```python
async def compute(db, user, input_ids, target_def_id, *, lock: bool) -> tuple[list[InventoryItem], ItemDef, float]
```
Порядок проверок:
1. `len(input_ids) > upgrade_max_inputs` → 400 `TOO_MANY_INPUTS`;
2. повторы id → 400 `DUPLICATE_INPUTS`;
3. предметы: `lock_items`, если `lock`, иначе тот же запрос без `FOR UPDATE` с той же проверкой → `ITEM_NOT_OWNED`;
4. цель: нет `item_def`, её коллекция не `released` или `is_upgrade_target` ложно → 400 `UPGRADE_TARGET_NOT_AVAILABLE`;
5. `chance = sum(values) / target.value * (1 - upgrade_edge)`; вне `[upgrade_min_chance, upgrade_max_chance]` → 400 `UPGRADE_CHANCE_OUT_OF_RANGE`.

`preview` вызывает `compute(lock=False)` и **ловит** `AppError`, возвращая `{chance: <если посчитан, иначе 0>, chance_text, allowed: False, reason: code}`. Исключение — `ITEM_NOT_OWNED`: оно пробрасывается как ошибка.

`execute` (`lock=True`):
1. `compute`;
2. `r = rng.random()`; `success = r < chance`;
3. `unequip_items(inputs)`; всем входам `status="burned"`, `burned_at=now`;
4. `roll_id = record_roll(kind="upgrade", ref=str(target.id), chance=chance, roll_value=r, input={"input_ids", "input_value", "target_def_id"}, outcome={"success": success, "item_id": None})`;
5. если `success`: `item = create_item(source="upgrade", source_ref=str(roll_id))` (wear — следующий `rng.random()`), затем у строки `rolls` с `roll_id` заменить `outcome` на `{"success": True, "item_id": item.id}` (новый dict целиком, чтобы SQLAlchemy увидел изменение JSONB);
6. ответ с `roll_value=r`, `burned_ids` по возрастанию.

### 3.6 `app/services/catalog_admin.py`
Все функции принимают `admin: User` и пишут `admin_audit(admin_id=admin.id, action=..., target=..., payload=тело запроса)`.

Ошибки:

| Код | HTTP |
|---|---|
| `COLLECTION_NOT_FOUND`, `ITEM_DEF_NOT_FOUND`, `CASE_NOT_FOUND`, `USER_NOT_FOUND` | 404 |
| `COLLECTION_CODE_TAKEN`, `ITEM_CODE_TAKEN`, `CASE_CODE_TAKEN` | 409 |
| `COLLECTION_NOT_DRAFT` (действие только для черновика), `COLLECTION_NOT_READY` (выпуск без скинов или с кейсом без дропов), `COLLECTION_NOT_RELEASED` (снять можно только выпущенную), `ITEM_DEF_LOCKED` (изменение `kind`/`piece_type`/`rarity` или удаление после выпуска), `CASE_LOCKED` (изменение дропов или удаление кейса после выпуска), `DROP_ITEM_NOT_IN_COLLECTION`, `ITEM_DEF_NOT_AVAILABLE` (выдача скина не из `released` коллекции) | 400 |

Правила:
- коды (`code`) у коллекций, скинов и кейсов — slug `^[a-z0-9-]{2,40}$`; `name` 1–60 символов; `description` ≤ 500; `price`/`value` — `1 … 10_000_000`;
- `PATCH /admin/item-defs/{id}`: в черновике можно менять все поля; после выпуска — только `name`, `asset`, `value`, `is_upgrade_target`, иначе `ITEM_DEF_LOCKED`. Если меняется `kind`, `asset` валидируется по новому `kind`;
- `PATCH /admin/cases/{id}`: `name`, `price`, `is_active`, `sort` — в любом статусе;
- `PUT /admin/cases/{id}/drops` (тело `[{item_def_id, weight}]`, `weight ≥ 1`, без повторов) — только черновик; полностью заменяет дропы;
- `POST /admin/cases/{id}/drops/auto` — только черновик; заменяет дропы на `auto_weights(все скины коллекции подходящего вида)`. Тело `{"kind": "piece_skin" | "board_skin" | null}`: `null` — все скины коллекции;
- `release`: статус должен быть `draft` (иначе `COLLECTION_NOT_DRAFT`), проверка готовности → `released`, `released_at = now`;
- `retire`: статус должен быть `released` → `retired`, `retired_at = now`;
- `DELETE` коллекции, скина, кейса — только черновик;
- `grant-item`: скин из `released` коллекции, иначе 400 `ITEM_DEF_NOT_AVAILABLE`; `create_item(source="admin_grant", source_ref=str(admin.id))`.

## 4. Роутеры

### `app/api/items.py` (публичное — без авторизации; остальное — `current_user`)
| Метод | Путь | Авторизация |
|---|---|---|
| GET | `/api/v1/collections` | нет; только `released` и `retired`, сортировка `released_at desc` |
| GET | `/api/v1/collections/{code}` | нет; черновик → 404 `COLLECTION_NOT_FOUND`; ответ `{code, name, description, status, released_at, items: [ItemDefOut]}` (сортировка: редкость по возрастанию ценности, затем `code`) |
| GET | `/api/v1/item-defs?upgrade_target=true` | да; при `true` — только цели апгрейда, сортировка по `value` |
| GET | `/api/v1/inventory?kind=&slot=&sort=rarity\|value\|new` | да; только `owned` и `listed` (сгоревшие не показываются). `sort`: `rarity` (по умолчанию) — редкость по убыванию, затем `value` по убыванию, затем `id`; `value` — `value` по убыванию, затем `id`; `new` — `acquired_at` по убыванию, затем `id` по убыванию. `slot=N` — только предметы, подходящие в этот слот |
| GET | `/api/v1/loadout` | да |
| PUT | `/api/v1/loadout/{slot}` | да |
| GET | `/api/v1/cases` | нет; только открываемые, сортировка `sort, id` |
| GET | `/api/v1/cases/{id}` | нет; любой неоткрываемый (в т.ч. retired/неактивный) → 404 `CASE_NOT_FOUND` |
| POST | `/api/v1/cases/{id}/open` | да; rate-limit `hit(f"rl:items:{user.id}", 3, 1)` |
| POST | `/api/v1/upgrade/preview` | да |
| POST | `/api/v1/upgrade` | да; rate-limit тот же |

### `app/api/admin_catalog.py` (всё через `require_admin`)
- `GET /api/v1/admin/collections` — все, с `items_count`, `cases_count`;
- `GET /api/v1/admin/collections/{id}` — коллекция + скины + кейсы с дропами;
- `POST /api/v1/admin/collections` `{code, name, description}` → 201;
- `PATCH /api/v1/admin/collections/{id}` `{name?, description?}`;
- `DELETE /api/v1/admin/collections/{id}` → 204;
- `POST /api/v1/admin/collections/{id}/release`, `/retire`;
- `POST /api/v1/admin/collections/{id}/items` `{code, name, kind, piece_type, rarity, value, asset, is_upgrade_target=true}` → 201;
- `PATCH|DELETE /api/v1/admin/item-defs/{id}`;
- `POST /api/v1/admin/collections/{id}/cases` `{code, name, price, sort=0}` → 201;
- `PATCH|DELETE /api/v1/admin/cases/{id}`;
- `PUT /api/v1/admin/cases/{id}/drops`, `POST /api/v1/admin/cases/{id}/drops/auto`;
- `POST /api/v1/admin/users/{id}/grant-item` `{item_def_id}` → `ItemOut`.

## 5. Тесты

В `conftest.py`: фикстура `admin` — зарегистрированный клиент, которому роль `admin` выставлена напрямую в БД. Хелпер `async def give_items(user_login, codes: list[str]) -> list[int]` создаёт предметы через `create_item` в отдельной сессии. Для wear 0.5 он временно ставит `FixedRng([0.5])`, а затем **восстанавливает тот RNG, что был до вызова** (`prev = get_rng()` … `set_rng(prev)`): иначе сломается фикстура `rng` в тесте.

### `tests/test_catalog.py` (публичное и сид)
- `test_seed_genesis` — `/collections` содержит `genesis` с `items_count == 22`; `/cases` — ровно 2 кейса в порядке `genesis-pieces`, `genesis-boards`; у всех скинов asset белый stub.
- `test_seed_weights_match_auto_formula` — для обоих кейсов веса в БД == `auto_weights(скины кейса, DEFAULTS["rarity_weights"])`; сумма весов фигур 8375994, досок 9660000.
- `test_case_detail_chances` — у `genesis-boards` 4 дропа, сумма `chance` ≈ 1 (`approx`, abs 1e-9), шанс mythic `chance_text == "0.06%"`.
- `test_exterior_boundaries` — 0.0→FN, 0.0699→FN, 0.07→MW, 0.15→FT, 0.38→WW, 0.45→BS, 0.9999→BS.

### `tests/test_cases_open.py`
- `test_open_case_deterministic` — `rng.values=[0.0]`: alice открывает `genesis-pieces` → баланс 900; ledger `case_purchase -100`; выпал `genesis-pawn-chalk` (id 1 — минимальный среди дропов); `win_index == 45`; `strip[45] == item.def.id`; `len(strip) == 60`; все id ленты есть в `defs`; `item.wear == 0.0`; строка `rolls` kind `case_open`, `roll_value == 0.0`, `chance ≈ 1332000/8375994`.
- `test_weighted_pick_boundaries` (чистый) — три дропа с весами 10, 20, 70 (id 1, 2, 3): `r=0.0`→1, `0.0999`→1, `0.1`→2, `0.2999`→2, `0.3`→3, `0.9999`→3.
- `test_open_case_insufficient_funds` — баланс выставить 50 → 400 `INSUFFICIENT_FUNDS`; предметов, ledger-записей и rolls нет.
- `test_open_case_concurrent` — баланс 300, 6 параллельных открытий (кейс за 100) → ровно 3 успеха, баланс 0, 3 предмета, `sum(ledger.delta) == balance`.
- `test_open_unavailable_case` — кейс черновой коллекции (создан админом): `GET /cases/{id}` и `POST open` → 404 `CASE_NOT_FOUND`; админ делает `retire` у genesis → `/cases` пуст, `GET /cases/1` → 404, `POST /cases/1/open` → 400 `CASE_NOT_AVAILABLE`, баланс не изменился.

### `tests/test_inventory.py`
- `test_inventory_and_equip` — alice получает `genesis-knight-chalk` и `genesis-board-paper`; `PUT /loadout/N` → в лоадауте; `equipped_slot == "N"` в инвентаре; `PUT /loadout/B` тем же предметом → `ITEM_SLOT_MISMATCH`; `PUT /loadout/board` доской → ок; `PUT /loadout/N {null}` → слот пуст.
- `test_equip_foreign_or_burned` — предмет bob → `ITEM_NOT_OWNED`; сгоревший предмет alice → `ITEM_NOT_OWNED`.
- `test_loadout_snapshot_in_game` — alice экипирует `genesis-pawn-chalk`, партия через `start_game` (alice белые) → `state.players.white.loadout.P == {"code": "genesis-pawn-chalk", "name": "Пешка | Мел", "rarity": "common", "asset": {"type": "stub", "color": "#ffffff"}}`; у чёрных `loadout == {}`; после снятия скина в состоянии партии ничего не меняется.
- `test_inventory_hides_burned` — сгоревшие не попадают в `/inventory`; сортировка `value` — по убыванию ценности.

### `tests/test_upgrade.py`
- `test_upgrade_preview` — 2 rare (150+150) → цель epic 500: `chance == approx(300/500*0.95) == 0.57`, `allowed`; цель mythic 5000 у досок: `300/5000*0.95 = 0.057` → allowed; 1 common (20) → mythic: `0.0038` < 0.01 → `allowed=False`, `UPGRADE_CHANCE_OUT_OF_RANGE`; 10 epic → epic: `9.5` > 0.8 → out of range.
- `test_upgrade_validation` — 11 предметов → `TOO_MANY_INPUTS`; `[id, id]` → `DUPLICATE_INPUTS`; чужой → `ITEM_NOT_OWNED`; цель из черновой коллекции → `UPGRADE_TARGET_NOT_AVAILABLE`; цель с `is_upgrade_target=false` → то же.
- `test_upgrade_success` — `rng.values=[0.0, 0.3]`: два rare (один экипирован) → epic: `success`, оба входа `burned`, слот пуст, новый предмет `source="upgrade"`, `wear == 0.3`; строка `rolls` kind `upgrade` с `outcome.item_id == новый id`.
- `test_upgrade_fail` — `rng.values=[0.99]`: входы сгорели, `item is None`, новых предметов нет.
- `test_upgrade_concurrent_same_inputs` — два параллельных апгрейда с одними и теми же входами → ровно один 200, второй 400 `ITEM_NOT_OWNED`.

### `tests/test_catalog_admin.py`
- `test_admin_required` — обычный пользователь: `GET /admin/collections` → 403; аноним → 401.
- `test_collection_lifecycle` — админ создаёт `winter` → в публичном `/collections` её нет; добавляет 2 common piece_skin (`P`, `N`) и 1 epic `Q`; создаёт кейс; `release` без дропов → `COLLECTION_NOT_READY`; `drops/auto` → веса 3996000, 3996000, 64000; `release` → коллекция видна, кейс в `/cases`, открывается; `retire` → кейс пропал, у игрока выпавший предмет остался и экипируется; скины `winter` больше не цели апгрейда.
- `test_item_def_validation` — piece_skin без `piece_type` → 422; board_skin с `piece_type` → 422; board_skin с `PieceAsset` → 422; цвет `#fff` → 422; повтор `code` → 409 `ITEM_CODE_TAKEN`.
- `test_item_def_locked_after_release` — на `genesis-pawn-chalk`: `PATCH {name, value, asset: {"type":"stub","color":"#ff0000"}}` → ок, новый asset виден в `/collections/genesis`; `PATCH {rarity: "epic"}` → `ITEM_DEF_LOCKED`; `DELETE` → `ITEM_DEF_LOCKED`.
- `test_drops_validation` — черновой кейс: дроп со скином другой коллекции → `DROP_ITEM_NOT_IN_COLLECTION`; повтор `item_def_id` → 422; `weight: 0` → 422; у genesis-кейса `PUT drops` → `CASE_LOCKED`.
- `test_grant_item_and_audit` — `grant-item` скина genesis → у пользователя предмет `source="admin_grant"`; скин черновой коллекции → `ITEM_DEF_NOT_AVAILABLE`; несуществующий пользователь → 404; в `admin_audit` есть строки по всем успешным действиям теста с `admin_id` админа.

## 6. Проверка (приложить вывод)
```bash
make test        # 105 старых + новые, все зелёные
make up && docker compose ps
```
В конце: список файлов, отступления (или «отступлений нет»), вопросы.
