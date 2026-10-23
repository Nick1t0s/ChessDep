# ChessDep — как всё устроено

Единый справочник по проекту. Если документы расходятся, **истина — код**, затем этот файл, затем `docs/TZ.md` (исходное ТЗ, часть решений позже изменилась — см. раздел 13).

Карта документации:

| Файл | Зачем |
|---|---|
| `README.md` | Запуск, админ, HTTPS, тесты — коротко для пользователя |
| `docs/ARCHITECTURE.md` | **Этот файл**: устройство, механизмы, решения, рецепты |
| `docs/TZ.md` | Исходное ТЗ v1.1: правила депа, экономика, модель данных, API |
| `docs/contracts-spectate.md` | Контракт зрителей, чата, истории ходов, профилей, HTTPS |
| `docs/contracts-collections.md` | Контракт предметов v3: наборы, коллекции, доски, базовые скины, магазин кейсов, ежедневная награда — заменяет §4 ТЗ |
| `docs/contracts-skins.md` | PNG-скины фигур (128×128, прозрачный фон) и досок (1088×1088, рамка 32 px): загрузка, хранение, раздача, отрисовка |
| `docs/AUDIT.md` | Почему старый фронт (`legacy/`) не используется |
| `tasks/*.md`, `tasks/delegated/` | Задания, по которым писался код (история, очень подробно) |
| `CLAUDE.md` | Правила для Claude Code в этом репозитории |

---

## 1. Что это

Онлайн-шахматы (PvP) с элементами казино:
- **Деп.** В свой ход, до хода, можно рискнуть своей фигурой (кроме короля): с шансом `ценность_из / ценность_в` (P=1, N=B=3, R=5, Q=9) она превращается в более ценную, иначе сгорает. Не больше 1 депа за ход и 10 за партию.
- **Предметы как в CS:** наборы из коллекций (по 12 фигур: 6 белых, 6 чёрных) и досок; кейсы продаются в магазине и лежат в инвентаре до открытия; скины апгрейдятся, продаются на маркете между игроками, дарятся. У каждого игрока есть непередаваемые базовые скины.
- **Зрители, чат партии, история ходов, повтор, профили игроков.**

Валюта ◈ виртуальная: не покупается и не выводится.

**Главный принцип: сервер — единственный источник истины.** Браузер хранит только cookie сессии. Все шансы, броски, легальность ходов, часы, цены считает сервер. Фронт только рисует и отправляет действия.

---

## 2. Контейнеры

```
браузер ──http(s)──▶ nginx ──/api/, /ws/──▶ api (FastAPI, uvicorn) ──▶ postgres
                       │                        │  ▲
                       └─ статика frontend/     ▼  │ pub/sub, ZSET, лимиты, очередь
                                               redis
                                                ▲
                          worker (часы, флаги, матчмейкинг) ──▶ postgres
```

| Сервис | Что делает |
|---|---|
| `nginx` | Единственный, кто опубликован наружу (`HTTP_PORT` 8080 → 80, `HTTPS_PORT` 8443 → 443). Отдаёт `frontend/` (смонтирован, правки видны без пересборки; конфиг `nginx/conf/` вшит в образ — после правки `docker compose up -d --build nginx`), проксирует `/api/` и `/ws/` на `api:8000`, ставит заголовки безопасности, закрывает `admin.html` через `auth_request` |
| `api` | FastAPI: весь REST и WebSocket |
| `worker` | `python -m app.worker`: каждые 200 мс ставит флаги и аннулирует партии по дедлайнам, каждые 500 мс сводит пары в матчмейкинге. **Должен быть ровно один экземпляр** |
| `migrate` | Одноразовый `alembic upgrade head` перед стартом `api` и `worker` |
| `postgres` | PostgreSQL 16, том `pgdata` |
| `redis` | Redis 7 (AOF), том `redisdata` |
| `postgres-test`, `redis-test`, `api-test` | Профиль `test`, только для `make test` |

---

## 3. Репозиторий

```
backend/
  app/
    main.py            FastAPI-приложение: middleware, обработчики ошибок, роутеры
    config.py          настройки из env (pydantic-settings)
    db.py              engine, SessionLocal, get_db, after_commit/run_after_commit
    redis.py           общий клиент Redis
    worker.py          цикл worker: tick_clocks, rebuild_deadlines, matchmaking.tick
    cli.py             make-admin / revoke-admin
    seed_data.py       сид базового набора и Genesis для тестов (миграции — замороженные seed_data_v*.py)
    seed_skins.py      PNG-заглушки сида из app/seed_images/ (генерирует scripts/gen_seed_images.py)
    core/              clock, deps (current_user, optional_user, require_admin), errors,
                       origin (CSRF), ratelimit, security (argon2, токены), sessions
    chess_engine/      ЧИСТЫЕ правила шахмат и депа поверх python-chess (без БД и I/O)
    models/            SQLAlchemy-модели
    schemas/           Pydantic-схемы входа/выхода
    services/          вся бизнес-логика
    api/               роутеры (тонкие: валидация, rate-limit, вызов сервиса)
  alembic/versions/    0001…0005 — миграции, написаны руками
  tests/               pytest
frontend/              HTML-страницы, css/, js/ (ES-модули), js/admin/
nginx/                 Dockerfile, 40-chessdep-conf.sh (выбор режима), conf/
scripts/               check_frontend.sh, test_isolated.sh, gen-dev-cert.sh
certs/                 сюда кладутся fullchain.pem/privkey.pem для HTTPS (в git — только .gitkeep)
docs/, tasks/, legacy/
```

---

## 4. Окружение (`.env`, шаблон `.env.example`)

| Переменная | Смысл |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` | База (пароль в `DATABASE_URL` должен совпадать) |
| `REDIS_URL` | Redis |
| `COOKIE_SECURE` | `false` для http; `true` для HTTPS (cookie тогда называется `__Host-sid` и имеет флаг `Secure`) |
| `ALLOWED_ORIGINS` | Через запятую — адреса, с которых открывают сайт, **точно со схемой и портом** (`http://localhost:8080`, `http://10.208.33.16:8080`, `https://localhost:8443`). Иначе любой POST получит 403 `BAD_ORIGIN` «Запрос с недопустимого источника» |
| `SESSION_TTL_DAYS` | Срок жизни сессии (30) |
| `HTTP_PORT`, `HTTPS_PORT` | Внешние порты nginx (8080, 8443) |

После правки `.env`: `make up`. Если nginx должен сменить режим HTTP/HTTPS — ещё `docker compose restart nginx` (режим выбирается при старте контейнера).

---

## 5. Бэкенд: общие механизмы

### 5.1 Путь запроса
1. **nginx** → `api`.
2. **`OriginMiddleware`** (`core/origin.py`). Для всех методов, кроме GET/HEAD/OPTIONS, и для WebSocket заголовок `Origin` обязан быть в `ALLOWED_ORIGINS`, иначе 403 `BAD_ORIGIN`. Это защита от CSRF вместе с `SameSite=Strict`.
3. **Зависимости FastAPI:**
   - `get_db` открывает **одну транзакцию на запрос**: коммит при успехе, откат при исключении;
   - `current_user` проверяет cookie сессии (401 `UNAUTHENTICATED`, 403 `USER_BANNED`);
   - `optional_user` то же, но без 401;
   - `require_admin` — 403 `FORBIDDEN`.
4. **Роутер** — rate-limit, затем сервис.
5. **После коммита** выполняются хуки `after_commit` (п. 5.4). Проверено: в FastAPI 0.115.6 код зависимости после `yield` выполняется **до** отправки ответа. Поэтому клиент не увидит ответ раньше коммита.

### 5.2 Сессии и пароли
- Пароли — argon2id. При несуществующем логине всё равно делается проверка по фиктивному хешу (выравнивание времени ответа).
- Сессия: случайный токен `secrets.token_urlsafe(32)` в cookie (`HttpOnly`, `SameSite=Strict`, `Path=/`, `Secure` при `COOKIE_SECURE`). В БД (`sessions`) лежит только `sha256(token)`. Роль и прочее в cookie не хранятся, JWT не используется.
- Выход отзывает сессию; смена пароля отзывает все остальные; бан отзывает все.
- Роль `admin` — только в БД, выдаётся **только** CLI: `make make-admin LOGIN=<логин>` (аккаунт должен уже существовать).

### 5.3 Транзакции и блокировки (важно)
- **Любой `SELECT … FOR UPDATE` — только с `.execution_options(populate_existing=True)`.** Иначе SQLAlchemy вернёт объект из identity map со старыми полями. Например, `current_user` уже загрузил пользователя до блокировки, и баланс читается устаревший. Это был реальный баг: 10 параллельных бонусов проходили все. Хелперы: `economy.lock_user`, `games.lock_game`, `items.lock_items`, `items.lock_item_any`.
- **Единый порядок блокировок (против дедлоков):** `market_listings` → `inventory_items` → `games` → `users`, внутри каждого вида — по возрастанию id. Нельзя взять более «раннюю» сущность после более «поздней».
- Партия: `games.version` растёт на 1 при каждом изменении. Клиент может прислать `expected_version`; при несовпадении — 409 `VERSION_CONFLICT`.
- Одна активная партия на игрока гарантируется PK таблицы `active_players(user_id)`.

### 5.4 Redis только после коммита
`after_commit(db, fn)` из `app/db.py` откладывает публикацию в pub/sub и изменения ZSET до успешного коммита. При откате хуки не выполняются. В worker и матчмейкинге, где сессия своя, после `async with db.begin()` нужно вызвать `await run_after_commit(db)`. Это был реальный баг: партия из матчмейкинга не получала дедлайн.

### 5.5 Время и случайность
- Время — только `from app.core import clock` → `clock.now()`. Тесты подменяют `clock.now`.
- Случайность — только `app.services.rolls.get_rng()` (`secrets.SystemRandom`). Тесты подставляют `FixedRng`. Модуль `random` в коде приложения запрещён.
- Каждый бросок (деп, кейс, апгрейд) пишется в `rolls`: шанс, выпавшее значение, вход, исход.

### 5.6 Деньги
Баланс меняется **только** через `economy.apply_delta(db, user_id, delta, reason, ref, actor_id)`. Функция блокирует пользователя, не даёт уйти в минус (400 `INSUFFICIENT_FUNDS`) и пишет строку в `ledger`. Причины: `signup_bonus`, `daily_bonus`, `game_win`, `game_draw`, `case_purchase`, `admin_adjust`, `market_buy`, `market_sale`. Инвариант: сумма `ledger.delta` пользователя = его баланс.

### 5.7 Настройки
Таблица `settings` (ключ → JSON), значения по умолчанию — `services/settings.py::DEFAULTS`. Чтение `get_setting(db, key)` с кэшем в памяти процесса на 5 секунд, поэтому в другом процессе изменение применяется с задержкой до 5 с. Админ меняет через `PUT /api/v1/admin/settings/{key}`. Валидатор — `SETTINGS_SCHEMA`: тип, границы и перекрёстная проверка `upgrade_min_chance ≤ upgrade_max_chance`.

| Ключ | По умолчанию |
|---|---|
| `starting_balance` | 1000 |
| `daily_bonus` / `daily_bonus_cooldown_h` | 200 / 24 |
| `game_win_reward` / `game_draw_reward` | 100 / 30 |
| `reward_min_plies` / `reward_games_per_day` | 10 / 20 |
| `dep_multiplier` | 1.0 |
| `upgrade_edge` / `upgrade_min_chance` / `upgrade_max_chance` / `upgrade_max_inputs` | 0.05 / 0.01 / 0.80 / 10 |
| `time_controls` | `["3+2","5+0","10+0"]` |
| `abort_first_move_s` | 30 |
| `rarity_weights` | common 7992, uncommon 1598, rare 320, epic 64, legendary 20, mythic 6 |
| `market_fee` / `market_max_listings` / `trade_hold_hours` | 0.05 / 50 / 0 |

Константы в коде (не настройки): ценности фигур, `DEP_LIMIT_PER_GAME = 10`, «0 или 1 деп за ход».

### 5.8 Rate-limit (Redis, фиксированное окно, `core/ratelimit.py`)
| Ключ | Лимит | Где |
|---|---|---|
| `rl:register:{ip}` | 5 / час | регистрация |
| `rl:login:{ip}` | 10 / мин | логин |
| `rl:loginfail:{login}` | 5 неудач / 15 мин | логин |
| `rl:game:{user}` | 10 / с | все POST партии |
| `rl:items:{user}` | 3 / с | открытие кейса, апгрейд |
| `rl:market:{user}` | 5 / с | выставить, снять лот (покупка не ограничена) |
| `rl:gift:{user}` | 10 / мин | подарок |
| `rl:chat:{user}`, `rl:chatm:{user}` | 1 / с и 20 / мин | чат |

Сбросить на dev: `docker compose exec redis sh -c 'redis-cli --scan --pattern "rl:*" | xargs -r redis-cli del'`.

### 5.9 Ошибки
Все ошибки — `{"error": {"code": "SNAKE_UPPER", "message": "по-русски"}}` (`core/errors.py`, класс `AppError`). Коды HTTP:
- 400 — бизнес-ошибки;
- 401 `UNAUTHENTICATED`;
- 403 — `BAD_ORIGIN`, `USER_BANNED`, `FORBIDDEN`;
- 404 — не найдено, в том числе «не твоя партия» для действий;
- 409 — `VERSION_CONFLICT`, `ALREADY_IN_GAME`, `*_TAKEN`;
- 422 `VALIDATION_ERROR` (Pydantic, `extra="forbid"`);
- 429 `RATE_LIMITED`;
- 500 `INTERNAL` (стек только в лог).

---

## 6. Шахматы и деп

### 6.1 Движок `app/chess_engine/` (чистый, без БД)
- `dep.py`:
  - `dep_chance` — `v_from / v_to × multiplier`, обрезка в [0, 1];
  - `validate_dep`;
  - `list_dep_options`;
  - `resolve_dep(board, square, target, roll_value, multiplier)` — успех ⇔ `roll < chance`;
  - `apply_dep_outcome`: снять фигуру, при успехе поставить новую, пересчитать права рокировки, сбросить невозможное взятие на проходе, обнулить счётчик 50 ходов.
- **Запрет депа:** если хотя бы в одном исходе (успех **или** провал) король соперника под шахом — `WOULD_CHECK_OPPONENT`. Учитываются и вскрытые шахи при сгорании. Провал, вскрывающий шах **своему** королю, разрешён: это риск игрока.
- После депа ход всё ещё за тем же игроком. Поэтому «мат» после депа — мат ему самому. Пат и недостаточность материала — ничья.
- `game.py`: `apply_move`, `game_outcome` (порядок: мат, пат, недостаточность материала, 50 ходов, троекратное повторение), `legal_moves_uci`, `board_squares`, `position_key`, `can_win_on_time`.
- Движок проверен дифференциальным прогоном против эталонной реализации: 3000 партий, 78 тыс. депов.

### 6.2 Партия (`services/games.py`)
- **Создание** (`create_game`): цвет случаен (`get_rng`), Elo фиксируется в `*_elo_before`, лоадауты обоих игроков снапшотятся в `white_loadout/black_loadout`, `abort_deadline = now + abort_first_move_s`, вставляются строки `active_players`.
- **Каждое действие** начинается с `_guard_action`:
  1. `lock_game`;
  2. игрок ли (иначе 404);
  3. `expected_version`;
  4. партия активна;
  5. время не истекло — иначе 400 `TIME_EXPIRED`; флаг ставит worker, а не запрос.
- **Ход:** `apply_move` → часы → `ply += 1`, `dep_used_this_turn = False`; ход соперника снимает его предложение ничьей; повторения: необратимый ход сбрасывает словарь `repetition`.
- **Деп:** сначала валидация, **потом** бросок; `record_roll`; `repetition` сбрасывается; часы не трогаются.
- **Ничья:** одно активное предложение; повторно — только через 2 полухода (`*_last_offer_ply`).
- **Отмена партии:** пока `ply < 2`.
- **Финиш** (`finish_game`): фиксирует часы, удаляет `active_players`; для `aborted` — без Elo и наград. Иначе: Elo (K=32) и награды (только если `ply ≥ reward_min_plies` и за сегодня по UTC игрок получил награды меньше чем за `reward_games_per_day` партий). Событие `game_over`.
- `forfeit(db, game, color, now)` — сдача уже заблокированной партии. Используется в `do_resign` и при бане.

### 6.3 Часы
Хранятся `white_ms`, `black_ms` — остаток на момент `turn_started_at`. Остаток ходящего = `ms − (now − turn_started_at)`.
- Часы запускаются после **первого хода чёрных** (`clock_running = True`). До этого действует `abort_deadline`: 30 с на первый ход каждой стороны, иначе партия аннулируется (`abort_no_first_move`).
- На ходе: `ms = остаток + инкремент`.
- `game_clock.deadline(game)` — момент флага или аннулирования. После каждого изменения `schedule_deadline` кладёт его в Redis ZSET `clock:deadlines`.
- **Worker** каждые 200 мс забирает просроченные id:
  - блокирует партию, **перепроверяет по БД** (Redis — только подсказка) и вызывает `check_timeout`;
  - флаг: соперник побеждает (`timeout`) или ничья, если ему нечем поставить мат (`timeout_vs_insufficient`, проверка `can_win_on_time`);
  - сбой одной партии не останавливает остальные; мусорные id удаляются из ZSET;
  - при старте worker пересобирает ZSET из БД (`rebuild_deadlines`).

### 6.4 Матчмейкинг и приглашения
- **Очередь:** Redis LIST `mm:queue:{tc}` плюс ключ-сердцебиение `mm:user:{id}` с TTL 10 с. Поллинг `/matchmaking/status` раз в секунду продлевает TTL. Кто закрыл вкладку — выпадает.
- Worker парит по FIFO. Если создать партию не удалось, пара возвращается в начало очереди. Если ключ жив, а в LIST игрока нет, `enqueue` или `status` возвращают его в очередь (самовосстановление).
- **Приглашение:** код из 10 символов `[a-z2-9]` (без похожих), живёт 10 минут, принять своё нельзя.

### 6.5 WebSocket `/ws/games/{id}` и pub/sub
- Пускает любого залогиненного (игроков и зрителей). Проверка `Origin`. Отказ — на handshake (HTTP 403), поэтому браузер видит обычный обрыв 1006. Фронт после любого обрыва делает `GET /games/{id}`, чтобы отличить «нет доступа» от «нет сети».
- Все изменения партии публикуются в канал `game:{id}` после коммита:
  - `{"version": N, "dep": {...} | null, "game_over": {...} | null}` — сервер перечитывает состояние и шлёт клиенту по порядку `dep` → `state` → `game_over`;
  - `{"chat": ChatMessageOut}` — клиенту уходит только `{"type": "chat", "data": ...}`, состояние не перечитывается.
- Клиент шлёт только `{"type": "ping"}` раз в 25 с, сервер отвечает `pong`.

### 6.6 Зрители, история, чат (`docs/contracts-spectate.md`)
- `GET /games/{id}` для не-игрока возвращает `you: "spectator"`, `legal_moves: []`. Действия и `dep-options` — 404.
- `GET /games/live` — активные партии. В роутере объявлен **раньше** `/games/{game_id}`, иначе `live` попадёт в параметр и получит 422.
- `GET /games/{id}/events?after_seq=` — все события партии, у каждого готовая позиция (`board`, `check_square`). Фронт не разбирает FEN.
- `GET /users/{login}`, `GET /users/{login}/games` — публичный профиль и партии.
- Чат: таблица `game_messages`, 1–300 символов, роль автора (`white` / `black` / `spectator`). Писать можно в любом статусе партии.

---

## 7. Предметы

Подробный контракт — `docs/contracts-collections.md` (v3).
- **Набор** (`item_sets`) — перечень коллекций и досок; вне набора их нет. Статус `draft` → `released` → `retired` есть только у набора; коллекции и доски добавляются только в черновик. Снятие набора снимает с продажи все кейсы с его скинами.
- **Коллекция** — ровно 12 скинов фигур (`side` ∈ `w`/`b` × `piece_type`), создаётся одним запросом целиком; коды и имена генерирует сервер (`seed_data.item_code/item_name`). **Доска** — скин `kind = board`, принадлежит набору напрямую. У игрока нет страницы наборов: набор и коллекция видны только подписью на карточке скина.
- **Скин** (`item_defs`): `kind` (`piece`/`board`), `set_id`, у фигур — `collection_id`, `side`, `piece_type`; редкость задаётся вручную; `asset` — `{"type": "png", "image": "<sha256>"}` (ссылка на `skin_images`, см. ниже).
- **Базовый набор** (`is_base`, id 1): 12 фигур + доска, выдаются при регистрации (`source = 'base'`, `wear = 0`) и сразу надеты. Базовый предмет (`bound`) нельзя продать, подарить, апгрейдить (`ITEM_BOUND`).
- **Экземпляр** (`inventory_items`): `wear` в [0, 1) (exterior FN/MW/FT/WW/BS — косметика), статус `owned` | `listed` | `burned`, `acquired_at`. Экипировать, апгрейдить, выставлять и дарить можно только `owned`.
- **Экипировка:** 13 слотов (`wP…bK` + `board`). Слот можно очистить, но **в бой нельзя без всех 13** (`LOADOUT_INCOMPLETE`): проверки в очереди, инвайтах и `create_game`; воркер выкидывает из очереди игрока с неполной экипировкой. Снапшот в партию — слоты своей стороны без префикса + `board`; каждый видит свою доску, зритель — доску белых.
- **Кейс** — товар магазина: `kind` `set` / `collection` / `custom`, статусы `draft` → `on_sale` ⇄ `off_sale`, лимиты — тираж (`stock_limit`, по исчерпании сам `off_sale`; атомарный `UPDATE … sold_count + 1`, `cases` блокируется раньше `users`) и окно продаж (`sale_starts_at/ends_at`). Покупка (`/cases/{id}/buy`) кладёт **предмет-кейс** в инвентарь (`inventory_items.case_id`); его можно открыть, продать, подарить. Дропы заморожены после выхода из черновика, поэтому купленный кейс открывается всегда.
- **Открытие** (`services/cases.py::open_case_item`, `POST /inventory/{id}/open`). Порядок вызовов RNG **зафиксирован**, на нём держатся тесты:
  1. предмет-кейс → `burned`;
  2. `r_win` → победитель (`weighted_pick` по дропам, отсортированным по `item_def_id`);
  3. `win_index = 45 + int(r × 10)`;
  4. 60 позиций ленты-филлера;
  5. `wear`.

  Ответ содержит ленту для анимации.
- **Автовеса:** вес скина = `rarity_weights[редкость] × 1000 // число скинов этой редкости в кейсе`.
- **Апгрейд:** 1–10 разных `owned` предметов → цель **из того же набора** (входы из чужого набора — `UPGRADE_SET_MISMATCH`). `chance = Σvalue / target.value × (1 − upgrade_edge)`, допустимо только в `[min, max]`. Входы сгорают при любом исходе. Колесо на фронте останавливается на `roll_value`. Проверка набора — в `services/upgrade.py::compute` до расчёта шанса, поэтому preview отдаёт её как `reason`. Следствие: скины `retired`-набора апгрейдить не во что (цель только из `released`). Страница `upgrade.js` показывает цели только из набора первого выбранного входа и не даёт добавить вход из другого набора.
- **Ежедневная награда** (`services/daily_reward.py`): после `daily_reward_wins` (3) побед за сутки UTC (`ply ≥ reward_min_plies`) — кнопка «Забрать»: один предмет-кейс по весам из `daily_reward_pool` (админка), бросок в `rolls` (`daily_reward`), раз в сутки (`users.last_daily_reward_on`).
- **Картинки скинов** (`services/skin_images.py`, `docs/contracts-skins.md`): PNG хранится в таблице `skin_images` (`id` = sha256 перекодированных байт, `kind`, `data`). Фигура — ровно 128×128, четыре угловых пикселя прозрачные; доска — ровно 1088×1088, рамка 32 px, клетка 128 px, a8 в левом верхнем углу поля. Админ грузит файл `POST /admin/skin-images?kind=…` (сырые байты `image/png`, до 2 МБ; Pillow проверяет и перекодирует в RGBA). Раздача — `GET /skins/<sha>.png` публично с `Cache-Control: immutable`. При создании коллекции/доски и правке asset сервер проверяет, что картинка есть и её вид совпадает со скином.
- **Сид** (`app/seed_data.py::seed_rows`): базовый набор (скины 1–13) и Genesis (коллекция — скины 14–25, доски 26–27, кейс 1 по набору), пул награды; asset — картинки из `app/seed_images/<code>.png` (id через `app/seed_skins.py`). Использует `conftest.py` (вместе с `seed_image_rows()` для `skin_images`). Сиды миграций заморожены: `seed_data_v1.py` (0003), `seed_data_v2.py` (0006), `seed_data_v3.py` (0007, цветные заглушки) — не менять.

## 8. Маркет и подарки
- **Лот:** предмет переходит в `listed`, с экипировки снимается. Лимит активных лотов — `market_max_listings`. Задержка передачи `trade_hold_hours` считается по `acquired_at`.
- **Покупка:** блокировки лот → предмет → оба пользователя по возрастанию id. Покупатель платит `price`, продавец получает `price − ceil(price × market_fee)` (через `Decimal`; если 0 — строки в `ledger` нет). Предмет переходит покупателю с новым `acquired_at`, пишется строка в `item_transfers`.
- **Подарок:** мгновенная передача по логину, записка до 140 символов, флаг `seen` (просмотренные помечаются при чтении входящих). Подарок сбрасывает `trade_hold` получателю.

## 9. Админка и аудит
- API: `/api/v1/admin/*` (`api/admin.py`, `api/admin_catalog.py`), всё через `require_admin`; каждое изменение пишется в `admin_audit` (CLI пишет с `admin_id = NULL`).
- **Бан** (`services/admin_users.py::ban_user`), строго в таком порядке:
  1. снять все активные лоты;
  2. засчитать поражение в активной партии;
  3. заблокировать пользователя, `is_banned = true`, отозвать все сессии;
  4. после коммита убрать его из очереди матчмейкинга.

  Нельзя забанить себя и другого админа.
- `admin.html` дополнительно закрыт на nginx: `auth_request` к `/api/v1/internal/require-admin`. Снаружи этот путь отдаёт 404. Гостя редиректит на `/login.html?next=/admin.html` относительным `Location` (`absolute_redirect off`), чтобы не терялся нестандартный порт.

---

## 10. Модель данных (миграции `backend/alembic/versions/`)

| Миграция | Таблицы |
|---|---|
| 0001 | `users`, `sessions`, `settings` (+ сид значений), `ledger`, `admin_audit` |
| 0002 | `games`, `game_events`, `active_players`, `invites`, `rolls` |
| 0003 | `collections`, `item_defs`, `inventory_items`, `loadouts`, `cases`, `case_drops` + сид Genesis + новые настройки |
| 0004 | `market_listings` (частичный unique активного лота на предмет), `item_transfers`; причины `market_buy`/`market_sale` в `ledger` |
| 0005 | `game_messages` |
| 0006 | коллекции v2: **удаляет все предметы** (лоты, передачи, инвентарь, кейсы, скины, коллекции); `item_defs.kind` → `side`, у `cases` вместо `collection_id`/`is_active` — `status`, 12 слотов лоадаута; сид Genesis v2 |
| 0007 | наборы v3: **удаляет все предметы**; `item_sets`, `daily_reward_pool`, доски, предметы-кейсы (`inventory_items.case_id`, лоты кейсов), виды и лимиты кейсов, `users.last_daily_reward_on`; сид; выдача базовых скинов всем пользователям |
| 0008 | `skin_images` + PNG сида; все asset `stub` (в `item_defs` и снапшотах `games.*_loadout`) → `png`: скины сида по своему коду, прочие — базовая картинка того же слота |

Поля таблиц — в моделях `backend/app/models/*.py` и в `docs/TZ.md` §8. Миграции пишутся **руками** (не autogenerate), у каждой есть `downgrade`.

## 11. API (все пути с префиксом `/api/v1`)

| Группа | Эндпоинты | Доступ |
|---|---|---|
| Служебное | `GET /health`, `GET /config` (`time_controls`, `dep_limit`), `GET /internal/require-admin` | публично / для nginx |
| Аккаунт | `POST /auth/register`, `/auth/login`, `/auth/logout`; `GET /me`, `POST /me/password`, `GET/POST /me/daily-reward`, `GET /me/ledger`, `/me/games`, `/me/active-game`, `/me/listings`, `/me/gifts`, `/me/gifts/unseen-count` | залогиненный (кроме register/login) |
| Игра | `POST/DELETE /matchmaking/queue`, `GET /matchmaking/status`; `POST /invites`, `POST /invites/{code}/accept`, `DELETE /invites/{code}` | залогиненный |
| Партия | `GET /games/live`, `GET /games/{id}`, `GET /games/{id}/events`, `GET/POST /games/{id}/chat` | любой залогиненный |
| Действия в партии | `GET /games/{id}/dep-options`, `POST /games/{id}/move`, `/dep`, `/resign`, `/draw/offer`, `/draw/accept`, `/draw/decline`, `/abort` | только игроки |
| Игроки | `GET /users/{login}`, `/users/{login}/games`, `GET /leaderboard` | залогиненный / лидерборд публичный |
| Предметы | `GET /sets`, `/sets/{code}`, `/collections/{code}`, `/shop`, `/cases/{id}`, `/skins/{sha}.png` (публично); `GET /item-defs`, `/inventory`, `/loadout`, `PUT /loadout/{slot}`, `POST /cases/{id}/buy`, `POST /inventory/{id}/open`, `POST /upgrade/preview`, `/upgrade` | см. слева |
| Маркет и подарки | `GET /market`, `/market/defs/{def_id}` (публично); `POST /market/listings`, `DELETE /market/listings/{id}`, `POST /market/listings/{id}/buy`, `POST /gifts` | залогиненный |
| Админ | `/admin/sets…`, `/admin/collections/{id}`, `/admin/item-defs…`, `/admin/skin-images`, `/admin/cases…` (`publish`/`unpublish`), `/admin/daily-reward-pool`, `/admin/users…` (поиск, карточка, ban/unban, balance, grant-item), `/admin/settings…`, `/admin/rolls`, `/admin/games/{id}/events`, `/admin/market…`, `/admin/audit` | admin |
| WebSocket | `/ws/games/{id}` | любой залогиненный |

Формы запросов и ответов — в `backend/app/schemas/*.py`, `docs/TZ.md` §9, `docs/contracts-spectate.md`.

---

## 12. Фронтенд

### 12.1 Принципы (проверяются тестом)
- Чистые HTML, CSS и ES-модули, без сборки, фреймворков и CDN. Одна страница = `*.html` + `js/<страница>.js` + свой CSS.
- DOM строится **только** через `h(tag, attrs, ...children)` из `js/dom.js` и `textContent`. Запрещены `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`, инлайн-скрипты и стили. Динамические цвета — только `el.style.setProperty('--var', …)`: это разрешает CSP `style-src 'self'`.
- Фронт **ничего не вычисляет** из игровой логики. Ходы — из `legal_moves`, шансы — из ответов, позиции истории — из `events[].board`.
- Проверки: `bash scripts/check_frontend.sh` (синтаксис через node и запреты) и `backend/tests/test_frontend_static.py`.

### 12.2 Общие модули `frontend/js/`
| Модуль | Что делает |
|---|---|
| `api.js` | `api(method, path, body, {redirectOn401})`, `ApiError`, `safeNext`; запрос, оборванный уходом со страницы, не отклоняется (промис просто не завершается); то же при 401 с редиректом на логин — без необработанного `pageerror` |
| `dom.js` | `h()` (белый список атрибутов; `href` только относительный), `clear()` |
| `layout.js` | `initLayout({auth, active})` — шапка, баланс, бейдж подарков, мобильный таб-бар (4 раздела + кнопка «Ещё» с остальными разделами, профилем и выходом) — вместо верхнего меню при ширине < 900px или высоте ≤ 500px; `setBalance`. На `game.html` таб-бара нет; телефон в альбомной ориентации (высота ≤ 500px) — доска слева во всю высоту, панели игроков справа, шапка скрыта |
| `toast.js`, `modal.js` | уведомления (не больше 4 одновременно), модалки, `confirmModal` |
| `format.js` | `fmtCrystals`, `fmtClock`, словари русских названий |
| `pieces.js` | `skinUrl`, `pieceNode` (картинка скина фигуры, без картинки — глиф), `boardUrl`; размеры PNG |
| `items.js` | `itemCard` (с подписью «Набор · Коллекция»), `skinPreview`, названия редкостей, износа и видов кейсов (`CASE_KIND_RU`) |
| `board.js` | доска: 64 кнопки, создаются один раз; ориентация; подсветки; доска-картинка (`.board-zone.skinned`, отступ рамки 2.9412 %, подписи a–h/1–8 поверх рамки); `pieceElement` для анимации депа |
| `ws.js` | WebSocket с ping и переподключением 1/2/5/10 с |
| `dep-fx.js` | анимация депа: бар до `roll_value`, затем превращение или сгорание |
| `game-moves.js`, `game-chat.js` | список ходов с выбором позиции; чат |

### 12.3 Игровой экран (`js/game.js`) — главное
- **Правило версий:** `applyState(s)` применяет состояние только при `s.version > текущей`. HTTP-ответы и WS-сообщения могут приходить в любом порядке.
- **Единая очередь событий** `enqueue()`: все `state`, `dep`, `game_over` и собственные действия выполняются строго последовательно. Анимация депа (~2.6 с) показывается **обоим** игрокам и зрителям **до** новой позиции. Свой деп анимируется по HTTP-ответу, а свой же WS-`dep` игнорируется.
- Часы тикают локально от момента получения состояния, флаг ставит только сервер.
- Зритель (`you === "spectator"`): белые внизу, кнопок действий нет, клики игнорируются.
- Просмотр позиции: клик по ходу показывает `events[].board`. Живые обновления продолжают приходить, но доску не перерисовывают до «К текущей позиции».

### 12.4 Страницы
`index` (лобби: поиск, приглашение, ежедневная награда), `game`, `live`, `replay`, `user`, `invite`, `login`, `register`, `inventory`, `cases` (магазин; «Содержимое» кейса — модалка поверх магазина), `case` (открытие кейса из инвентаря `?item=`; карточка кейса по прямой ссылке `?id=`), `upgrade`, `market`, `market-item`, `gifts`, `profile`, `leaderboard`, `admin` (вкладки грузятся динамически из `js/admin/*.js`: catalog = наборы, cases = кейсы и пул награды, users, settings, misc = маркет + журнал).

## 13. nginx и HTTPS
- `nginx/40-chessdep-conf.sh` при старте контейнера выбирает шаблон: есть `/etc/nginx/certs/fullchain.pem` и `privkey.pem` — `https.conf.template` (443 + 301 с 80 на `https://$host:${HTTPS_PORT}`, HSTS), иначе `http.conf.template`. Общая часть — `nginx/conf/app.locations`.
- Заголовки: CSP `default-src 'self'…`, `X-Content-Type-Options`, `Referrer-Policy`. В `location` нельзя добавлять свои `add_header`, иначе пропадут общие.
- Адрес `api` переспрашивается у DNS Docker каждые 10 с (`resolver 127.0.0.11` + переменная в `proxy_pass`). Поэтому пересоздание контейнера `api` не роняет сайт в 502.
- Самоподписанный сертификат для разработки: `bash scripts/gen-dev-cert.sh`.

## 14. Тесты
- `make test` — весь pytest в контейнерах профиля `test` (~1.5–2 мин, 223 теста на момент написания).
- `bash scripts/test_isolated.sh` — то же, но в отдельном compose-проекте (`-p t<хеш пути>`). Можно запускать параллельно из нескольких git worktree.
- Фикстуры `backend/tests/conftest.py`:
  - перед каждым тестом `TRUNCATE` всех таблиц, заново настройки по умолчанию и Genesis, `flushdb` Redis;
  - клиенты `alice`, `bob`, `carol`, `admin`, `client`;
  - `rng` (`FixedRng`), `frozen` (время);
  - хелперы `start_game` (alice всегда белые), `set_fen`, `give_items`, `set_balance`, `set_setting`, `count_queries`.
- **Новую таблицу добавлять в `_TRUNCATE_SQL`.** Картинки сида (`skin_images`) заливаются заново перед каждым тестом; id картинки сида в тестах — `seed_image_id("<code>")`.
- Браузерные прогоны в репозиторий не входят. Делались через контейнер `mcr.microsoft.com/playwright:v1.49.1-noble` в сети `chessdep_default` с TCP-прокси `localhost:8080 → nginx:80` внутри контейнера, чтобы `Origin` совпадал.

## 15. Отступления от `docs/TZ.md` (актуальное поведение)
- `GET /me/games` и `/users/{login}/games` листаются по времени (`before=<iso>`, `next_before`), а не по id: у партий uuid.
- Зрители, чат, история ходов, публичные профили, HTTPS — добавлены сверх ТЗ v1.1 (`docs/contracts-spectate.md`).
- Маркет и подарки были «вне скоупа» в ТЗ 1.0, в 1.1 включены и реализованы.
- `h(tag, null, …)` допустим (`null` = без атрибутов).
- Покупка на маркете не ограничена rate-limit (защищена блокировками).
- Asset скина — только PNG (`docs/contracts-skins.md`), тип `stub` из ТЗ §4 удалён; сторона фигуры задаётся самой картинкой скина, а не формой глифа.

## 16. Известные ограничения
- Нет бота, модерации чата (удаление, мут), зрителей без аккаунта.
- Скины сида — сгенерированные PNG-заглушки (глифы DejaVu); настоящие картинки грузятся через админку. Неиспользуемые картинки из `skin_images` не удаляются.
- `worker` рассчитан на один экземпляр (матчмейкинг без Lua-атомарности).
- Кэш настроек — 5 с на процесс.
- HTTPS-сертификаты нужно продлевать вручную (Let's Encrypt не автоматизирован).

## 17. Рецепты
- **Сайт с другой машины:** добавить её адрес со схемой и портом в `ALLOWED_ORIGINS` → `make up`. Симптом, если забыть: «Запрос с недопустимого источника» на любой форме.
- **Админ:** зарегистрироваться на сайте → `make make-admin LOGIN=<логин>` → обновить страницу.
- **Новая настройка:** `DEFAULTS` и `SETTINGS_SCHEMA` в `services/settings.py` + вставка значения в новой миграции.
- **Новая таблица:** модель в `models/`, импорт в `models/__init__.py`, миграция руками с `downgrade`, таблица в `_TRUNCATE_SQL` в `conftest.py`.
- **Новый эндпоинт:** схема в `schemas/`, логика в `services/`, роутер в `api/` (подключить в `main.py`), тест. Ошибки — через `AppError`, изменения баланса — через `apply_delta`, Redis — через `after_commit`.
- **Новая страница:** скопировать каркас `index.html`, модуль `js/<имя>.js` с `initLayout`, свой CSS; прогнать `scripts/check_frontend.sh`.
- **Сбросить dev-базу** (удалит всё, Genesis создастся заново): `docker compose down -v && make up`.
- **Логи:** `docker compose logs -f api worker nginx`.
- **SQL:** `docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'`.
- **Разработка через исполнителей GLM:** `~/.claude/skills/delegate/oc-dispatch.sh` (см. `CLAUDE.md`). Контракты пишутся заранее в `docs/`, задания — в `.delegate/tasks/<фича>/`, копии сохраняются в `tasks/delegated/`.
