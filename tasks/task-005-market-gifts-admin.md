# task-005 — Маркет, дарение, лидерборд, админка пользователей и настроек

Прочитай перед работой: `docs/TZ.md` версии 1.1 — разделы 4.3, 4.7, 4.8, 5, 7, 8 (`market_listings`, `item_transfers`), 9.9, 9.10.

## Правила для исполнителя
Те же, что в прошлых задачах:
- время только через `clock.now()`;
- любой `FOR UPDATE` только с `populate_existing=True`;
- баланс меняется только через `apply_delta`;
- действия админа пишутся в `admin_audit`;
- Redis трогаем только через `after_commit`.

**Порядок блокировок в этой задаче (строго, против дедлоков):**
`market_listings` (по возрастанию id) → `inventory_items` (по возрастанию id) → `games` → `users` (по возрастанию id).
Внутри одной операции нельзя взять более «раннюю» сущность после более «поздней».

Если что-то неясно — остановись и спроси.

---

## 1. Миграция `alembic/versions/0004_market.py` (руками)

### `market_listings`
| Колонка | Тип |
|---|---|
| id | bigserial pk |
| item_id | bigint fk inventory_items not null |
| item_def_id | int fk item_defs not null (денормализация для фильтров и истории цен) |
| seller_id | bigint fk users not null |
| price | bigint not null, check `price between 1 and 10000000` |
| status | text not null, check `('active','sold','cancelled')` |
| buyer_id | bigint fk users null |
| fee | bigint null |
| created_at | timestamptz not null default now() |
| closed_at | timestamptz null |

Индексы:
- частичный unique `uq_market_listings_active_item` на `(item_id) WHERE status = 'active'`;
- `(item_def_id, status, price)`;
- `(seller_id, status)`;
- `(status, created_at desc)`.

### `item_transfers`
`id bigserial pk`, `item_id bigint fk not null`, `from_user_id bigint fk not null`, `to_user_id bigint fk not null`, `kind text check ('market','gift')`, `ref text null`, `note text null` (check `length(note) <= 140`), `seen bool not null default false`, `created_at timestamptz not null default now()`.

Индексы: `(to_user_id, kind, created_at desc)`, `(from_user_id, kind, created_at desc)`.

### `ledger.reason`
Пересоздать check-ограничение `ck_ledger_reason_whitelist`: добавить `market_buy`, `market_sale`. Downgrade возвращает старый список.

Модели: `app/models/market.py` (`MarketListing`, `ItemTransfer`). Новые таблицы добавить в TRUNCATE в `conftest.py`.

## 2. Общие хелперы

### 2.1 `app/services/items.py` — добавить
```python
async def lock_item_any(db, item_id: int) -> InventoryItem | None
    # FOR UPDATE + populate_existing, без проверки владельца и статуса
async def items_out(db, items: list[InventoryItem]) -> list[ItemOut]
    # пакетная версия item_out: ровно 3 запроса на любой размер списка —
    # def'ы (IN), коллекции (IN), слоты loadouts (IN); порядок сохраняется
def check_trade_hold(item: InventoryItem, hold_hours: int, now) -> None
    # hold_hours > 0 и now < acquired_at + hold → AppError(400, "TRADE_HOLD", "Предмет можно передать после <дата ISO>")
```
`GET /inventory`, `GET /loadout` и все списки этой задачи используют `items_out` вместо цикла с `item_out`.

### 2.2 Исправление гонки экипировки
`PUT /loadout/{slot}` — вместо «select, затем insert или update» использовать
`insert(Loadout).values(...).on_conflict_do_update(index_elements=["user_id", "slot"], set_={"inventory_item_id": ...})`
(`from sqlalchemy.dialects.postgresql import insert`). Блокировка предмета через `lock_items` остаётся.

### 2.3 `app/services/games.py` — вынести сдачу
```python
async def forfeit(db, game: Game, color: str, now) -> GameOver | None
    # игра уже заблокирована; если не active — ничего не делать и вернуть None;
    # bump, событие resign (actor=color), finish_game(соперник, "resign"), bump,
    # событие game_over, schedule_deadline, publish
```
`do_resign` = `_guard_action` + `forfeit`. Поведение `do_resign` не меняется (старые тесты обязаны пройти).

## 3. Маркет `app/services/market.py`

Ошибки:
| Код | HTTP |
|---|---|
| `LISTING_NOT_FOUND` | 404 |
| `LISTING_NOT_ACTIVE`, `CANNOT_BUY_OWN`, `LISTING_LIMIT`, `TRADE_HOLD` | 400 |

### 3.1 `create_listing(db, user, item_id, price, now) -> MarketListing`
1. `items = lock_items(db, user.id, [item_id])` (`ITEM_NOT_OWNED`, если не свой или не `owned`);
2. `check_trade_hold(item, trade_hold_hours, now)`;
3. число активных лотов пользователя ≥ `market_max_listings` → `LISTING_LIMIT`;
4. `unequip_items([item.id])`; `item.status = "listed"`;
5. создать лот (`item_def_id` из предмета, `status="active"`, `created_at=now`).

### 3.2 `cancel_listing(db, user, listing_id, now, *, by_admin: User | None = None)`
1. Лот `FOR UPDATE`. Нет лота или (не админ и `seller_id != user.id`) → `LISTING_NOT_FOUND`. `status != "active"` → `LISTING_NOT_ACTIVE`.
2. `lock_item_any(item_id)`; `item.status = "owned"`.
3. `listing.status = "cancelled"`, `closed_at = now`.

### 3.3 `buy_listing(db, buyer, listing_id, now) -> MarketListing`
1. Лот `FOR UPDATE`: нет → `LISTING_NOT_FOUND`; не `active` → `LISTING_NOT_ACTIVE`; `seller_id == buyer.id` → `CANNOT_BUY_OWN`.
2. `item = lock_item_any(listing.item_id)`.
3. `lock_user` покупателя и продавца **по возрастанию id**.
4. `apply_delta(buyer, -price, "market_buy", ref=str(listing.id))` (`INSUFFICIENT_FUNDS` пробрасывается).
5. `fee = math.ceil(Decimal(price) * Decimal(str(market_fee)))`; `seller_amount = price - fee`; если `seller_amount > 0` → `apply_delta(seller, +seller_amount, "market_sale", ref=str(listing.id))`.
6. Предмет: `user_id = buyer.id`, `status = "owned"`, `acquired_at = now`.
7. Лот: `status = "sold"`, `buyer_id`, `fee`, `closed_at = now`.
8. `ItemTransfer(kind="market", ref=str(listing.id), from=seller, to=buyer, seen=True)`.

### 3.4 Выборки (без блокировок)
- `browse(db, viewer_id | None, filters, sort, page, limit) -> (list[ListingOut], total)`. Фильтры: `collection` (code), `kind`, `piece_type`, `rarity`, `def_id`. Сортировка:
  - `price_asc` — `price, id`;
  - `price_desc` — `price desc, id`;
  - `new` (по умолчанию) — `created_at desc, id desc`.

  Пагинация `page ≥ 1`, `limit 1..50` (по умолчанию 20). Только `active`.
- `def_market(db, def_id)` → `{def, stats: {active_count, min_price, last_sale_price}, listings: [active, price asc, до 50], sales: [{price, closed_at}, sold, closed_at desc, до 50]}`. Неизвестный или черновой def → 404 `ITEM_DEF_NOT_FOUND`.
- `my_listings(db, user, status)`.

`ListingOut {id, price, status, created_at, closed_at, seller_login, mine: bool, item: {id, def, wear, exterior}}`. Поле `mine` = `seller_id == viewer_id`; для анонима `false`.

## 4. Дарение `app/services/gifts.py`

Ошибки: `CANNOT_GIFT_SELF` 400, `RECIPIENT_BANNED` 400, `USER_NOT_FOUND` 404, плюс `ITEM_NOT_OWNED`, `TRADE_HOLD`.

`send_gift(db, sender, item_id, to_login, note, now)`:
1. Получатель по логину (citext): нет → `USER_NOT_FOUND`; он же отправитель → `CANNOT_GIFT_SELF`; забанен → `RECIPIENT_BANNED`.
2. `lock_items(db, sender.id, [item_id])`; `check_trade_hold`.
3. `unequip_items`; `item.user_id = recipient.id`; `acquired_at = now`.
4. `ItemTransfer(kind="gift", note=note, seen=False)`.

`list_gifts(db, user, direction, before_id, limit)`:
- `in` — где `to_user_id = user.id`;
- `out` — где `from_user_id = user.id`.

Только `kind="gift"`, сортировка `id desc`, курсор `before_id`.

Элемент: `{id, item: {id, def, wear, exterior}, from_login, to_login, note, seen, created_at}`. Для `in` после формирования ответа все непросмотренные входящие пользователя помечаются `seen = true`. В ответе `seen` — значение **до** пометки.

`unseen_count(db, user) -> int`.

## 5. Лидерборд
`GET /api/v1/leaderboard?by=elo|balance&limit=1..100` (по умолчанию `elo`, 50), без авторизации. Забаненные исключены. Сортировка по полю `desc`, затем `id asc`. Ответ `[{rank, login, elo, balance}]`, rank с 1.

## 6. Админка пользователей и настроек `app/services/admin_users.py`, роутер `app/api/admin.py`
Всё через `require_admin`, каждое изменение → `admin_audit`.

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/v1/admin/users?q=&page=&limit=` | `q` — подстрока логина или email (`ILIKE '%q%'`), `limit ≤ 50`; элемент `{id, login, email, role, is_banned, balance, elo, created_at, active_game_id}` + `total` |
| GET | `/api/v1/admin/users/{id}` | то же + `items_owned`, `active_listings`, `ledger` (последние 20) |
| POST | `/api/v1/admin/users/{id}/ban` | `{reason: 1..200}` |
| POST | `/api/v1/admin/users/{id}/unban` | |
| POST | `/api/v1/admin/users/{id}/balance` | `{delta: int ≠ 0, |delta| ≤ 1_000_000_000, comment: 1..200}` |
| GET | `/api/v1/admin/settings` | `[{key, value, default, updated_at, updated_by}]` по всем ключам `DEFAULTS` |
| PUT | `/api/v1/admin/settings/{key}` | `{value}` |
| GET | `/api/v1/admin/rolls?user_id=&kind=&before_id=&limit=` | броски, `id desc` |
| GET | `/api/v1/admin/games/{id}/events` | все события партии по `seq` |
| GET | `/api/v1/admin/market?status=&seller_id=&before_id=&limit=` | лоты, `id desc` |
| POST | `/api/v1/admin/market/listings/{id}/cancel` | `{reason: 1..200}` → `cancel_listing(by_admin=admin)` |
| GET | `/api/v1/admin/audit?before_id=&limit=` | журнал действий админов, `id desc`, с `admin_login` |

### 6.1 Бан — `ban_user(db, admin, user_id, reason, now)`
Строго в этом порядке (порядок блокировок!):
1. Пользователь не найден → 404 `USER_NOT_FOUND`; он сам → 400 `CANNOT_BAN_SELF`; `role == "admin"` → 400 `CANNOT_BAN_ADMIN` (сначала снять роль через CLI); уже забанен → ничего не делать, вернуть как есть.
2. Все активные лоты пользователя по возрастанию id → `cancel_listing(by_admin=admin)`.
3. Активная партия (`ActivePlayer`) → `lock_game` → `forfeit(db, game, его_цвет, now)`.
4. `lock_user(user_id)`; `is_banned = True`; `revoke_all(db, user_id)`.
5. `after_commit`: `matchmaking.dequeue(user)` (убрать из очереди).
6. `admin_audit("user.ban", payload={"reason"})`.

`unban` — `is_banned = False`, audit.

### 6.2 Баланс
`apply_delta(user_id, delta, "admin_adjust", ref=comment, actor_id=admin.id)`. `INSUFFICIENT_FUNDS` пробрасывается.

### 6.3 Настройки — валидация `app/services/settings.py`
Добавить `SETTINGS_SCHEMA: dict[str, Callable[[Any], Any]]` — валидатор на каждый ключ `DEFAULTS` (через `pydantic.TypeAdapter` с `Annotated[..., Field(ge=, le=)]`). Валидатор возвращает нормализованное значение или бросает `ValidationError`. Ошибка валидации → 422 `VALIDATION_ERROR`, неизвестный ключ → 404 `SETTING_NOT_FOUND`.

| Ключ | Тип и границы |
|---|---|
| `starting_balance` | int 0..10 000 000 |
| `daily_bonus` | int 0..1 000 000 |
| `daily_bonus_cooldown_h` | int 1..168 |
| `game_win_reward`, `game_draw_reward` | int 0..1 000 000 |
| `reward_min_plies` | int 0..500 |
| `reward_games_per_day` | int 0..1000 |
| `dep_multiplier` | float, `0 < x ≤ 2.0` |
| `upgrade_edge` | float 0..0.5 |
| `upgrade_min_chance`, `upgrade_max_chance` | float 0.0001..1.0 |
| `upgrade_max_inputs` | int 1..50 |
| `time_controls` | list из 1..10 уникальных строк, каждая `^\d{1,3}\+\d{1,3}$` и `parse_time_control` не падает, база > 0 |
| `abort_first_move_s` | int 10..600 |
| `rarity_weights` | dict ровно с 6 ключами редкостей, значения int 0..10 000 000, хотя бы одно > 0 |
| `market_fee` | float 0..0.5 |
| `market_max_listings` | int 1..1000 |
| `trade_hold_hours` | int 0..720 |

Перекрёстная проверка: после изменения `upgrade_min_chance ≤ upgrade_max_chance` (сравнить с текущим значением второго ключа), иначе 400 `SETTINGS_INCONSISTENT`.

Запись — upsert строки `settings` (`updated_at = now`, `updated_by = admin.id`), затем `clear_cache()`.

## 7. Роутеры
- `app/api/market.py`:
  - `GET /api/v1/market` — без авторизации; `mine` для залогиненного, cookie необязательна: сделай `optional_user` в `core/deps.py`, который возвращает `None` вместо 401;
  - `GET /api/v1/market/defs/{def_id}` — без авторизации;
  - `POST /api/v1/market/listings` `{item_id, price: 1..10_000_000}`;
  - `DELETE /api/v1/market/listings/{id}`;
  - `POST /api/v1/market/listings/{id}/buy`;
  - `GET /api/v1/me/listings?status=active|sold|cancelled`.
  
  На POST/DELETE — rate-limit `hit(f"rl:market:{user.id}", 5, 1)`.
- `app/api/gifts.py`:
  - `POST /api/v1/gifts` `{item_id, to_login: 1..64, note: str | None, max 140}`, rate-limit `hit(f"rl:gift:{user.id}", 10, 60)`;
  - `GET /api/v1/me/gifts?direction=in|out&before_id=&limit=`;
  - `GET /api/v1/me/gifts/unseen-count`.
- `app/api/leaderboard.py`, `app/api/admin.py`.

## 8. Тесты

`conftest.py`:
- `give_items` уже использует `clock.now()` — проверь, что с фикстурой `frozen` `acquired_at` совпадает с замороженным временем;
- добавить фикстуру `carol` (третий клиент);
- хелпер `async def set_balance(login, value)`;
- хелпер `async def count_queries()` — контекстный менеджер, считающий SQL через `event.listen(engine.sync_engine, "before_cursor_execute", ...)`.

### `tests/test_market.py`
- `test_list_and_cancel` — alice экипирует предмет и выставляет за 1000 → слот пуст, `status listed`, в `/inventory` виден со статусом `listed`; апгрейд с ним → `ITEM_NOT_OWNED`; экипировка → `ITEM_NOT_OWNED`; подарок → `ITEM_NOT_OWNED`; снять → `owned`; снять второй раз → `LISTING_NOT_ACTIVE`; bob снимает чужой → `LISTING_NOT_FOUND`.
- `test_list_validation` — цена 0 и 10_000_001 → 422; чужой предмет → `ITEM_NOT_OWNED`; повторно выставить выставленный → `ITEM_NOT_OWNED`; `market_max_listings=1` → второй лот → `LISTING_LIMIT`.
- `test_trade_hold` (`frozen`) — `trade_hold_hours=24`; свежий предмет → `TRADE_HOLD`; `frozen.advance(24*3600 + 1)` → выставляется.
- `test_buy_flow` — alice выставляет за 1000, bob покупает:
  - bob 1000 → 0, alice 1000 → 1950;
  - ledger: `market_buy -1000` у bob и `market_sale +950` у alice, оба с `ref == str(listing_id)`;
  - предмет у bob, `owned`, `acquired_at` = момент покупки;
  - лот `sold`, `buyer_id = bob`, `fee = 50`;
  - есть `item_transfers` kind `market`;
  - в `/market/defs/{def}` `sales[0].price == 1000`, `last_sale_price == 1000`.
- `test_fee_rounding` — цена 1 → `fee 1`, продавец получает 0, строки `market_sale` нет; цена 21 → `fee 2`, продавец +19.
- `test_buy_errors` — свой лот → `CANNOT_BUY_OWN`; баланс 10 → `INSUFFICIENT_FUNDS`, ничего не изменилось (лот `active`, предмет у продавца, ledger без новых строк); снятый лот → `LISTING_NOT_ACTIVE`; несуществующий → `LISTING_NOT_FOUND`.
- `test_buy_concurrent` — bob и carol одновременно покупают один лот → ровно один 200, второй 400 `LISTING_NOT_ACTIVE`; у всех троих `sum(ledger.delta) == balance`.
- `test_buy_vs_cancel_concurrent` — 10 повторов: alice снимает и bob покупает одновременно → ровно одно действие успешно; состояние согласовано: (`cancelled`, предмет у alice, `owned`) или (`sold`, предмет у bob, `owned`).
- `test_market_browse` — 3 лота с разными ценами и редкостью: `sort=price_asc` даёт возрастание; фильтр `rarity`, `piece_type`, `collection=genesis`; `total`; `mine=true` только у своих; аноним видит ленту, `mine=false`.

### `tests/test_gifts.py`
- `test_gift_flow` — alice дарит экипированный предмет bob с запиской «с днём рождения» → у alice слот пуст, предмет у bob, `acquired_at` обновлён; `unseen-count` у bob = 1; `GET /me/gifts?direction=in` → один элемент, `seen=false`, `note` совпадает; повторный GET → `seen=true`, `unseen-count = 0`; у alice `direction=out` — один элемент.
- `test_gift_errors` — себе → `CANNOT_GIFT_SELF`; неизвестный логин → 404 `USER_NOT_FOUND`; забаненному → `RECIPIENT_BANNED`; выставленный предмет → `ITEM_NOT_OWNED`; записка 141 символ → 422.
- `test_gift_resets_trade_hold` (`frozen`) — `trade_hold_hours=24`; у alice предмет с `acquired_at` двое суток назад (выставить в БД); дарит bob → bob сразу выставить не может (`TRADE_HOLD`).

### `tests/test_leaderboard.py`
- `test_leaderboard_order` — elo 1300/1250/1250/1100 (выставить в БД); порядок по elo desc, при равенстве — меньший id выше; забаненный исключён; `by=balance` сортирует по балансу; `limit=2` → 2 строки, `rank` 1 и 2.

### `tests/test_admin_users.py`
- `test_admin_endpoints_require_admin` — для каждого GET из таблицы п. 6 обычный пользователь получает 403.
- `test_admin_users_search` — `q=ali` находит alice по логину, `q=@example` — всех; `total` верный; в детальной карточке есть `ledger`.
- `test_ban_flow` — у bob активная партия с alice и активный лот. Через API встать в очередь, будучи в партии, нельзя, поэтому «зависший» в очереди bob имитируется напрямую в Redis: `SET mm:user:{bob} 3+2` + `RPUSH mm:queue:3+2 {bob}`. Админ банит bob:
  - партия `finished`, побеждает alice, `resign`;
  - лот `cancelled`, предмет у bob в статусе `owned`;
  - `mm:user:{bob}` удалён, bob нет в LIST;
  - старая cookie bob → 401 `UNAUTHENTICATED` (сессии отозваны);
  - логин bob → 403 `USER_BANNED`;
  - в `admin_audit` есть `user.ban`.

  После `unban` логин успешен.
- `test_ban_restrictions` — бан себя → `CANNOT_BAN_SELF`; бан другого админа → `CANNOT_BAN_ADMIN`; несуществующего → 404.
- `test_admin_balance` — `+500` → ledger `admin_adjust`, `actor_id` админа, `ref` = comment; `-1_000_000` → `INSUFFICIENT_FUNDS`; `delta 0` → 422.
- `test_admin_settings` — список содержит все ключи `DEFAULTS` с `default`; `PUT dep_multiplier 0.5` → у ходящего в `dep-options` шанс N→Q = `1/6` (approx); `PUT dep_multiplier "abc"` → 422; `PUT dep_multiplier 0` → 422; неизвестный ключ → 404; `upgrade_min_chance = 0.9` при `max 0.8` → `SETTINGS_INCONSISTENT`; `time_controls ["3+2", "bad"]` → 422; `rarity_weights` без `mythic` → 422; в `admin_audit` есть запись.
- `test_admin_rolls_events_market_audit` — после депа (`rng`) админ видит бросок с `kind=dep` и фильтром `user_id`; события партии по порядку `seq`; админ снимает чужой лот → `cancelled`, предмет `owned`; в `/admin/audit` действия последними сверху с `admin_login`.

### `tests/test_inventory.py` — добавить
- `test_loadout_concurrent_put` — 5 параллельных `PUT /loadout/N` одним и тем же предметом → все 200, в `loadouts` одна строка.
- `test_inventory_query_count` — у alice 30 предметов; `GET /inventory` внутри `count_queries()` → не больше 12 SQL-запросов на весь запрос.

## 9. Проверка (приложить вывод)
```bash
make test        # 129 старых + новые, все зелёные
make up && docker compose ps
```
В конце: список файлов, отступления (или «отступлений нет»), вопросы.
