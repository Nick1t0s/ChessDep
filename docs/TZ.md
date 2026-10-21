# ChessDep — техническое задание

Версия: 1.1 · 2026-10-22 (коллекции, маркет, дарение)

Документ обязателен для любого исполнителя. Всё, что здесь не описано, исполнитель **не придумывает сам**, а задаёт вопрос. Термины «ДОЛЖЕН», «ЗАПРЕЩЕНО» понимаются буквально.

---

## 1. Цель и глоссарий

ChessDep — онлайн-шахматы (PvP) с элементами казино:
1. **Деп** — во время партии перед своим ходом игрок может рискнуть своей фигурой: с шансом она превращается в более ценную, иначе сгорает.
2. **CS-система предметов** — скины фигур и досок, кейсы, апгрейд скинов.

| Термин | Значение |
|---|---|
| ◈ (кристаллы) | Виртуальная валюта. Не покупается и не выводится за реальные деньги. |
| Деп | Попытка превратить свою фигуру на доске в фигуру большей ценности. |
| Ценность | P=1, N=3, B=3, R=5, Q=9. Король — без ценности, депать нельзя. |
| Ход (turn) | Право одной стороны совершить один шахматный ход. «Перед ходом» = в свой ход, до отправки хода. |
| Ply | Полуход. |
| Item def | Описание вида предмета (каталог). |
| Inventory item | Конкретный экземпляр предмета у игрока. |
| Loadout | Экипировка игрока: по одному скину на каждый тип фигуры + скин доски. |
| Roll | Любой случайный бросок на сервере (деп, кейс, апгрейд). Всегда логируется. |

## 2. Роли

| Роль | Может |
|---|---|
| guest | Видеть страницы входа/регистрации, публичный лидерборд, каталог кейсов (без открытия). |
| user | Играть, депать, открывать кейсы, апгрейдить, экипировать, смотреть свою историю. |
| admin | Всё, что user, + админ-API (раздел 9.9). |

Роль хранится **только** в БД (`users.role`). Назначение админа — **только** CLI-командой внутри контейнера: `docker compose exec api python -m app.cli make-admin <login>`. Через API/UI роль не меняется. «Первый зарегистрированный = админ» — ЗАПРЕЩЕНО.

---

## 3. Шахматы и деп

### 3.1 Базовые правила
Классические правила FIDE (ходы, рокировка, взятие на проходе, превращение пешки, шах, мат, пат, недостаточность материала, правило 50 ходов, троекратное повторение — автоматическая ничья без заявления). Реализация на `python-chess`.

### 3.2 Деп — определение
- Деп делает игрок, **чей сейчас ход**, **до** отправки хода.
- Выбирается **своя** фигура на доске (кроме короля) и **целевой тип** со **строго большей** ценностью.
  - Допустимые пары: P→N, P→B, P→R, P→Q, N→R, N→Q, B→R, B→Q, R→Q.
  - N↔B (3→3), понижения, ферзь (9 — выше некуда), король — запрещены.
- Шанс успеха: `chance = (v_from / v_to) × dep_multiplier`, где `dep_multiplier` — настройка (по умолчанию `1.0`), итог обрезается в `[0, 1]`.

| Пара | Шанс |
|---|---|
| P→N, P→B | 33.33% |
| P→R | 20.00% |
| P→Q | 11.11% |
| N→R, B→R | 60.00% |
| N→Q, B→Q | 33.33% |
| R→Q | 55.56% |

- Бросок: `r = secrets.SystemRandom().random()`; успех ⇔ `r < chance`. Значение `r` сохраняется в `rolls`.
- **Успех**: фигура на той же клетке заменяется фигурой целевого типа того же цвета.
- **Провал**: фигура снимается с доски (сгорает).

### 3.3 Лимиты
- За один ход — **0 или 1** деп.
- За партию — **не более 10** депов на игрока (константа `DEP_LIMIT_PER_GAME = 10` в коде).
- После депа игрок **обязан** сделать ход (если ходов нет — см. 3.5). Деп после хода в тот же ход невозможен (ход уже передан сопернику).

### 3.4 Ограничения легальности
Сторона, которая не ходит, никогда не может стоять под шахом. Поэтому:
- Деп **запрещён** (`reason = "WOULD_CHECK_OPPONENT"`), если **хотя бы в одном** из двух исходов (успех ИЛИ провал) король соперника оказывается под атакой. Учитываются:
  - прямой шах новой фигурой (например, P→Q рядом с королём);
  - вскрытый шах при снятии фигуры (провал) — например, свой слон стоит за своим конём на диагонали короля соперника.
- Деп, при провале которого **свой** король оказывается под шахом (снята защищавшая фигура / вскрылась связка) — **разрешён**. Это риск игрока; дальше он обязан уйти от шаха ходом.
- Деп разрешён, даже если игрок сейчас под шахом.

### 3.5 Последствия депа
После применения исхода сервер пересчитывает позицию (ход всё ещё за тем же игроком):
- нет легальных ходов и свой король под шахом → **мат**, игрок проиграл (`end_reason = "checkmate"`);
- нет легальных ходов без шаха → **пат**, ничья (`end_reason = "stalemate"`);
- недостаточность материала у обеих сторон → ничья (`end_reason = "insufficient_material"`).
Прочее:
- Деп ладьи (успех или провал) снимает право рокировки с этой ладьёй. Если на клетке a1/h1/a8/h8 после депа нет исходной ладьи — соответствующее право рокировки сбрасывается.
- Поле взятия на проходе сохраняется, только если взятие по-прежнему легально (делегировать `python-chess`, поле не трогать вручную, кроме случая, когда сгорела/превратилась пешка, которую можно взять на проходе — тогда поле сбрасывается; это невозможно для своих пешек, но проверка обязательна в коде как assert-инвариант).
- Деп — **необратимое действие**: обнуляет счётчик полуходов правила 50 ходов и очищает историю позиций для троекратного повторения.
- Время, потраченное на деп, идёт с часов ходящего (часы не останавливаются).

### 3.6 Что отдаёт сервер для UI депа
`GET /api/v1/games/{id}/dep-options` (только ходящему игроку): по каждой своей фигуре — список целей с шансом и флагом допустимости (формат в 9.5). **Фронт ничего не считает** — ни шансов, ни легальности.

### 3.7 Часы и прочие события партии
- Пресеты: `3+2`, `5+0`, `10+0` (база минуты + добавка секунды за ход). Список — настройка `time_controls`.
- Часы считает сервер. На каждом ходе: `elapsed = now − turn_started_at`; `left −= elapsed`; если `left ≤ 0` → флаг; иначе `left += increment`.
- Часы запускаются только после первого хода чёрных. У каждой стороны есть `abort_first_move_s` (30 с) на первый ход, иначе партия **аннулируется** (`status = aborted`, без Elo и наград).
- Флаг ставит `worker` по дедлайну (раздел 6). Если у соперника недостаточно материала для мата — флаг даёт ничью (`timeout_vs_insufficient`).
- Сдача — в любой момент своей активной партии.
- Предложение ничьей: одно активное; действует до ответа соперника или до следующего хода соперника; повторно предложить — только после своего следующего хода.
- Abort вручную: пока любая сторона не сделала первый ход.
- Отключение игрока на часы не влияет.
- Elo: стандартная формула, K=32, старт 1200. Для aborted не меняется.
- У игрока может быть **только одна** активная партия.

### 3.8 Рейтинг и награды за партию
- Победа: `+game_win_reward` ◈, ничья: `+game_draw_reward` ◈ каждому, поражение: 0.
- Награда начисляется, только если в партии ≥ `reward_min_plies` полуходов и игрок сегодня (UTC) получил награды меньше чем за `reward_games_per_day` партий. Защита от фарма.

---

## 4. Предметы: коллекции, скины, кейсы, апгрейд, маркет, дарение

### 4.1 Коллекции
- Скины выпускаются **коллекциями**. Коллекция создаётся и наполняется в админке, затем выпускается.
- `collections.status`: `draft` → `released` → `retired`.
  - `draft` — не видна игрокам; можно свободно создавать, править и удалять её скины и кейсы.
  - `released` — видна игрокам, её кейсы открываются, её скины — цели апгрейда.
  - `retired` — снята с выпуска: кейсы больше не открываются, скины перестают быть целями апгрейда. Уже выпавшие предметы остаются у игроков, их можно экипировать, продавать и дарить.
- Выпуск (`release`) разрешён только если в коллекции есть хотя бы один скин и у каждого её кейса есть хотя бы один дроп.
- После выпуска у скина можно менять только `name`, `asset`, `value`, `is_upgrade_target`. Менять `kind`, `piece_type`, `rarity` и удалять скин нельзя: экземпляры уже у игроков.
- Сид-данные: выпущенная коллекция **Genesis** со скинами-заглушками и двумя кейсами (список — в task-004).

### 4.2 Скины (item_defs)
- `kind`: `piece_skin` (обязателен `piece_type ∈ {P,N,B,R,Q,K}`) или `board_skin` (`piece_type = NULL`). Скин короля допустим — запрещён только деп короля.
- `rarity`: `common, uncommon, rare, epic, legendary, mythic`. Цвета редкости (для рамок и карточек UI): `#9aa4b2, #38e8ff, #8b5cf6, #ffc93c, #ff7847, #ff5470`.
- `value` — ценность в ◈ (целое > 0). Используется для апгрейда.
- `asset` (jsonb) — внешний вид. Пока поддерживается только тип `stub` (заглушка):
  - piece_skin: `{"type": "stub", "color": "#ffffff"}`;
  - board_skin: `{"type": "stub", "light": "#ffffff", "dark": "#e5e5e5"}`.
  - **Все текущие скины — белые заглушки.** Различаются названием и редкостью. Реальные скины позже заменят `asset` у тех же item_defs через админку (поэтому `asset` редактируется и после выпуска). Новые типы `asset` добавляются отдельной задачей.

### 4.3 Экземпляры
- `inventory_items`: владелец, `item_def_id`, `wear ∈ [0,1)` (CSPRNG при создании), источник (`case | upgrade | admin_grant`), статус (`owned | listed | burned`), `acquired_at` (время получения текущим владельцем). Сгоревшие предметы физически не удаляются.
- Exterior по `wear`: FN `[0,0.07)`, MW `[0.07,0.15)`, FT `[0.15,0.38)`, WW `[0.38,0.45)`, BS `[0.45,1)`. Пока чисто косметика, на `value` не влияет.
- Экипировать, апгрейдить, выставлять и дарить можно только предмет в статусе `owned`.

### 4.4 Экипировка (loadout)
- Слоты: `P, N, B, R, Q, K, board`. В слот кладётся только свой `owned` предмет подходящего вида.
- При старте партии лоадауты обоих игроков **снапшотятся** в `games.white_loadout / black_loadout`: `{slot: {code, name, rarity, asset}}`. Смена экипировки во время партии на текущую партию не влияет.
- В партии фигуры каждого игрока рисуются его скинами (соперник видит твои скины). Доску каждый видит **своим** скином доски. Фигура после успешного депа рисуется скином нового типа.
- Сторона различается **формой глифа**, а не цветом: белые — контурные глифы U+2654–2659, чёрные — сплошные U+265A–265F; скин задаёт цвет заливки/контура. Поэтому белые заглушки не ломают читаемость.

### 4.5 Кейсы
- Кейс принадлежит одной коллекции и роняет только её скины. `cases`: цена в ◈, `is_active`, порядок. `case_drops`: `(case_id, item_def_id, weight > 0)`.
- Кейс открывается, только если `is_active` и коллекция `released`.
- Шансы дропа публичны: `GET /cases/{id}` отдаёт проценты (`weight / Σweight`).
- Автозаполнение весов по редкости: настройка `rarity_weights` (по умолчанию common 7992, uncommon 1598, rare 320, epic 64, legendary 20, mythic 6 — доли CS). Вес редкости делится поровну между скинами этой редкости в кейсе; редкости без скинов пропускаются.
- Открытие (`POST /cases/{id}/open`), одна транзакция: блокировка пользователя → списание (`ledger case_purchase`) → взвешенный выбор CSPRNG → создание `inventory_item` → запись в `rolls` → лента для анимации: 60 def-id, победитель на `win_index ∈ [45, 54]`, филлеры по тем же весам.
- Ответ содержит предмет, ленту, `win_index`, новый баланс. Фронт только проигрывает анимацию.

### 4.6 Апгрейд скинов
- Вход: от 1 до `upgrade_max_inputs` (10) **разных** своих `owned` предметов + целевой `item_def` (коллекция `released`, `is_upgrade_target = true`).
- `chance = Σ(value_inputs) / target.value × (1 − upgrade_edge)`. Допустимо, только если `upgrade_min_chance ≤ chance ≤ upgrade_max_chance` (0.01 … 0.80), иначе `400 UPGRADE_CHANCE_OUT_OF_RANGE`.
- Экипированные входы автоматически снимаются со слотов.
- Бросок `r`; успех ⇔ `r < chance`. **Все входы сгорают** при любом исходе; при успехе создаётся экземпляр цели (source=`upgrade`).
- Ответ: `success`, `chance`, `roll_value = r` (колесо/бар останавливается на `r`, win-зона `[0, chance)`), сгоревшие id, новый предмет или `null`. `POST /upgrade/preview` считает шанс без броска.

### 4.7 Маркет (игрок ↔ игрок)
- Выставить: свой `owned` предмет (экипированный снимается со слота) за цену `1 … 10 000 000` ◈. Предмет переходит в статус `listed`. Активных лотов у игрока не больше `market_max_listings` (50).
- Купить: одна транзакция. Блокируются лот, предмет, затем покупатель и продавец по возрастанию id. Покупатель ≠ продавец, баланса хватает. Покупатель `−price` (`ledger market_buy`), продавец `+(price − fee)` (`ledger market_sale`), где `fee = ceil(price × market_fee)` (0.05). Предмет переходит к покупателю (`owned`, новый `acquired_at`), лот → `sold`, запись в `item_transfers`.
- Снять лот может только продавец: предмет снова `owned`.
- Просмотр: лента лотов с фильтрами (коллекция, тип, фигура, редкость, скин) и сортировкой (цена ↑/↓, новые); по каждому скину — активные лоты и история цен продаж.
- Комиссия маркета — единственный «сток» ◈ из оборота игроков, её размер в настройках.

### 4.8 Дарение
- Подарить свой `owned` предмет другому игроку по логину, с запиской до 140 символов. Нельзя себе, нельзя забаненному. Экипированный предмет снимается со слота.
- Передача мгновенная, запись в `item_transfers` (kind `gift`). У получателя подарок отмечен как непросмотренный, пока он не откроет список подарков.
- Против отмывания: предмет, полученный меньше `trade_hold_hours` назад (по `acquired_at`), нельзя выставить или подарить. По умолчанию 0 — без задержки; админ может включить.

### 4.9 Вне скоупа (не делать)
Trade-up 10→1, обмен предмет-на-предмет, торги/ставки на маркете, продажа предметов системе, слоты, crash, mines, plinko, coinflip, колесо дня, квесты, промокоды, реальные платежи, депозит/вывод, зрители партий, бот, чат.

---

## 5. Экономика и настройки

Таблица `settings` (key → jsonb). Значения по умолчанию заливаются миграцией. Читаются сервером на каждую операцию (кэш в памяти процесса не дольше 5 с).

| Ключ | По умолчанию | Описание |
|---|---|---|
| `starting_balance` | 1000 | ◈ при регистрации |
| `daily_bonus` | 200 | Ежедневный бонус |
| `daily_bonus_cooldown_h` | 24 | Кулдаун бонуса |
| `game_win_reward` | 100 | Награда за победу |
| `game_draw_reward` | 30 | Награда за ничью |
| `reward_min_plies` | 10 | Мин. полуходов для награды |
| `reward_games_per_day` | 20 | Макс. награждаемых партий в сутки (UTC) |
| `dep_multiplier` | 1.0 | Множитель шанса депа |
| `upgrade_edge` | 0.05 | Комиссия апгрейда |
| `upgrade_min_chance` | 0.01 | Мин. шанс апгрейда |
| `upgrade_max_chance` | 0.80 | Макс. шанс апгрейда |
| `upgrade_max_inputs` | 10 | Макс. предметов на вход |
| `time_controls` | `["3+2","5+0","10+0"]` | Пресеты |
| `abort_first_move_s` | 30 | Время на первый ход |
| `rarity_weights` | `{"common":7992,"uncommon":1598,"rare":320,"epic":64,"legendary":20,"mythic":6}` | Веса редкостей для автозаполнения кейсов |
| `market_fee` | 0.05 | Комиссия маркета |
| `market_max_listings` | 50 | Макс. активных лотов на игрока |
| `trade_hold_hours` | 0 | Задержка перед продажей/дарением полученного предмета |

Константы в коде (не настройки): ценности фигур, `DEP_LIMIT_PER_GAME = 10`, «0 или 1 деп за ход».

Любое изменение баланса — только через сервис `economy.apply_delta(user_id, delta, reason, ref, actor_id=None)`, который в одной транзакции блокирует пользователя, проверяет `balance + delta ≥ 0`, пишет `ledger`. Прямой `UPDATE users SET balance` в коде вне этого сервиса ЗАПРЕЩЁН.

---

## 6. Архитектура

### 6.1 Стек (фиксирован)
- Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2.x (async, asyncpg), Alembic, Pydantic v2, pydantic-settings, argon2-cffi, redis-py (asyncio), python-chess.
- PostgreSQL 16, Redis 7.
- Фронт: чистые HTML + CSS + ES-модули JS, **без сборки, без фреймворков, без CDN**.
- nginx 1.27.
- Тесты: pytest, pytest-asyncio, httpx.

### 6.2 Контейнеры (docker-compose.yml)
| Сервис | Образ | Роль |
|---|---|---|
| `postgres` | postgres:16-alpine | БД, том `pgdata`, healthcheck `pg_isready` |
| `redis` | redis:7-alpine | pub/sub, очереди, rate-limit, том `redisdata`, AOF |
| `migrate` | backend | `alembic upgrade head`, одноразовый, `depends_on: postgres healthy` |
| `api` | backend | `uvicorn app.main:app`, `depends_on: migrate completed_successfully, redis healthy` |
| `worker` | backend | `python -m app.worker`: часы/флаги/abort, паринг матчмейкинга |
| `nginx` | nginx (свой Dockerfile) | статика `frontend/`, прокси `/api/` и `/ws/` на `api:8000` |

- Наружу публикуется **только** nginx (по умолчанию `8080:80`; HTTPS `8443:443`, если в `./certs` есть `fullchain.pem`/`privkey.pem`). Postgres и Redis наружу не публикуются.
- Конфиг через `.env` (шаблон `.env.example`): `POSTGRES_*`, `REDIS_URL`, `DATABASE_URL`, `COOKIE_SECURE`, `ALLOWED_ORIGINS`, `SESSION_TTL_DAYS`.
- Профиль `test`: сервис `postgres-test` (tmpfs) и запуск `docker compose --profile test run --rm api-test pytest`.
- Основная среда — Linux; на хосте нужен только Docker + Compose v2.

### 6.3 Структура репозитория
```
docker-compose.yml  .env.example  Makefile  README.md
backend/
  Dockerfile  pyproject.toml  alembic.ini
  alembic/versions/
  app/
    main.py            # FastAPI app, роутеры, middleware
    config.py          # pydantic-settings
    db.py              # engine, session
    redis.py
    worker.py
    cli.py
    core/              # security (sessions, hashing), deps (current_user), errors, ratelimit, origin
    models/            # SQLAlchemy модели
    schemas/           # Pydantic схемы запросов/ответов
    api/               # роутеры: auth, me, matchmaking, invites, games, items, cases, upgrade, leaderboard, admin, ws
    chess_engine/      # ЧИСТЫЙ модуль: правила депа поверх python-chess, без БД и I/O
    services/          # games, economy, items, cases, upgrade, rolls, settings
  tests/
frontend/
  *.html  css/  js/api.js  js/<page>.js  assets/
nginx/
  Dockerfile  nginx.conf
docs/  TZ.md  AUDIT.md
tasks/ task-NNN-*.md
legacy/  site/  templates/       # старый фронт, только как визуальный референс
```

### 6.4 Потоки
- **Все действия** клиента — через REST. WebSocket — **только** сервер→клиент (push состояния) + ping/pong. Так валидация живёт в одном месте.
- После любого изменения партии сервис публикует в Redis `game:{id}` событие; каждый процесс `api` ретранслирует его своим WS-подключениям этой партии.
- Изменения партии сериализуются: `SELECT … FROM games WHERE id = … FOR UPDATE` + проверка `version`; после изменения `version += 1`.
- **Часы**: при каждом изменении активной партии сервис кладёт в Redis ZSET `clock:deadlines` член `game_id` со score = ближайший дедлайн (флаг или abort) в ms. Worker каждые 200 мс забирает просроченные (`ZRANGEBYSCORE … -inf now`), для каждой блокирует партию, **перепроверяет по БД** и завершает (флаг/abort). Redis — только подсказка, истина — БД.
- **Матчмейкинг**: Redis LIST `mm:queue:{tc}`. Worker каждые 500 мс парит FIFO, цвет — CSPRNG. Пользователь, у которого есть активная партия, в очередь не встаёт.

---

## 7. Безопасность (чек-лист, всё обязательно)

1. **Единственное, что хранит браузер** — cookie сессии. Имя: `__Host-sid` при `COOKIE_SECURE=true`, `sid` при `false` (локальная разработка по http). Флаги: `HttpOnly; SameSite=Strict; Path=/; Secure` (если COOKIE_SECURE). Max-Age = `SESSION_TTL_DAYS` (30).
2. Значение cookie — непрозрачный токен `secrets.token_urlsafe(32)`. В БД хранится только `sha256(token)`. JWT и любые данные (роль, id, баланс) в cookie ЗАПРЕЩЕНЫ.
3. Сессия проверяется на каждом запросе: существует, не отозвана, не истекла, пользователь не забанен. `last_seen_at` обновляется не чаще раза в минуту. Logout и смена пароля отзывают сессию(и). Бан отзывает все сессии.
4. Пароли — argon2id (`argon2-cffi`, параметры по умолчанию библиотеки). Длина 8–128.
5. CSRF: для всех методов кроме GET/HEAD/OPTIONS сервер проверяет заголовок `Origin` ∈ `ALLOWED_ORIGINS`; отсутствие `Origin` → 403. Плюс SameSite=Strict. WS-handshake тоже проверяет `Origin`.
6. Во фронте ЗАПРЕЩЕНЫ `localStorage`, `sessionStorage`, `indexedDB`, `document.cookie`. Тест `tests/test_frontend_static.py` грепает `frontend/` и падает при нахождении.
7. XSS: во фронте данные с сервера вставляются **только** через `textContent` / `setAttribute` / создание элементов. `innerHTML` с данными сервера ЗАПРЕЩЁН (тот же grep-тест запрещает `innerHTML` с шаблонными строками `${`).
8. nginx-заголовки: `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`. Инлайн-скрипты и инлайн-стили во фронте запрещены (CSP).
9. `admin.html` отдаётся nginx только через `auth_request /api/v1/internal/require-admin` (возвращает 204 / 403). Все `/api/v1/admin/*` дополнительно проверяют роль на сервере.
10. Весь RNG — `secrets.SystemRandom()` через единый модуль `services/rolls.py`, который в тестах подменяется детерминированным. `random` и `Math.random` для игровых исходов ЗАПРЕЩЕНЫ.
11. Каждый бросок — строка в `rolls`. Каждое изменение баланса — строка в `ledger`. Каждое действие админа — строка в `admin_audit`.
12. Rate-limit (Redis, фиксированное окно): регистрация 5/час/IP; логин 10/мин/IP и 5 неудач/15 мин/логин; игровые действия 10/с/пользователь; открытие кейса и апгрейд 3/с/пользователь; остальное 30/с/пользователь. Ответ `429 RATE_LIMITED`.
13. Все входы валидируются Pydantic-схемами, лишние поля → 422 (`extra="forbid"`).
14. Ошибки не раскрывают стек; формат единый (9.1).
15. Проверка владения на каждый объект: партия — только её игроки; предметы — только владелец.

---

## 8. Модель данных (PostgreSQL)

Все времена `timestamptz`, все деньги `bigint`. Расширение `citext`.

**users**: `id bigserial pk`, `login citext unique not null` (3–16, `^[A-Za-z0-9_-]+$`), `email citext unique not null`, `password_hash text not null`, `role text not null default 'user' check in ('user','admin')`, `is_banned bool not null default false`, `balance bigint not null check (balance >= 0)`, `elo int not null default 1200`, `last_daily_bonus_at timestamptz null`, `created_at`.

**sessions**: `id bigserial pk`, `user_id fk users`, `token_hash bytea unique not null`, `created_at`, `expires_at`, `last_seen_at`, `revoked_at null`, `ip inet`, `user_agent text`. Индекс `(user_id)`.

**settings**: `key text pk`, `value jsonb not null`, `updated_at`, `updated_by fk users null`.

**invites**: `code text pk` (10 символов base32, CSPRNG), `creator_id fk`, `time_control text`, `created_at`, `expires_at` (+10 мин), `game_id uuid null`.

**games**: `id uuid pk`, `status text check in ('active','finished','aborted')`, `time_control text`, `base_ms int`, `inc_ms int`, `white_id fk`, `black_id fk`, `fen text not null`, `ply int not null default 0`, `repetition jsonb not null default '{}'` (ключ позиции → счётчик, очищается при необратимых действиях), `white_ms bigint`, `black_ms bigint`, `turn_started_at timestamptz`, `clock_running bool` (false до первого хода чёрных), `dep_used_this_turn bool not null default false`, `white_deps smallint not null default 0`, `black_deps smallint not null default 0`, `draw_offer_by text null check in ('white','black')`, `result text null check in ('white','black','draw')`, `end_reason text null`, `white_loadout jsonb`, `black_loadout jsonb`, `white_elo_before int`, `black_elo_before int`, `white_elo_after int null`, `black_elo_after int null`, `version int not null default 0`, `created_at`, `finished_at null`. Индексы: `(white_id, status)`, `(black_id, status)`.

**game_events**: `id bigserial pk`, `game_id fk`, `seq int` (уникален в партии), `ply int`, `actor text` (`white|black|system`), `kind text check in ('move','dep','resign','draw_offer','draw_accept','draw_decline','abort','flag','game_over')`, `payload jsonb` (move: `{uci, san}`; dep: `{square, from, to, chance, success, roll_id}`; game_over: `{result, end_reason}`), `fen_after text`, `white_ms bigint`, `black_ms bigint`, `created_at`. Unique `(game_id, seq)`.

**rolls**: `id bigserial pk`, `user_id fk`, `kind text check in ('dep','case_open','upgrade')`, `ref text` (game_id / case_id), `chance numeric(10,8) null`, `roll_value double precision not null`, `input jsonb`, `outcome jsonb`, `created_at`. Индекс `(user_id, created_at desc)`.

**ledger**: `id bigserial pk`, `user_id fk`, `delta bigint not null`, `balance_after bigint not null`, `reason text check in ('signup_bonus','daily_bonus','game_win','game_draw','case_purchase','admin_adjust','market_buy','market_sale')`, `ref text null`, `actor_id fk users null`, `created_at`. Индекс `(user_id, created_at desc)`.

**collections**: `id serial pk`, `code text unique` (slug `^[a-z0-9-]{2,40}$`), `name text`, `description text`, `status text check in ('draft','released','retired') default 'draft'`, `created_at`, `released_at null`, `retired_at null`.

**item_defs**: `id serial pk`, `collection_id fk not null`, `code text unique`, `name text`, `kind text check in ('piece_skin','board_skin')`, `piece_type char(1) null check in ('P','N','B','R','Q','K')`, check `(kind='piece_skin') = (piece_type is not null)`, `rarity text check in (...)`, `value int check > 0`, `asset jsonb`, `is_upgrade_target bool default true`, `created_at`.

**inventory_items**: `id bigserial pk`, `user_id fk`, `item_def_id fk`, `wear real check (wear >= 0 and wear < 1)`, `status text check in ('owned','listed','burned') default 'owned'`, `source text check in ('case','upgrade','admin_grant')`, `source_ref text`, `created_at`, `acquired_at`, `burned_at null`. Индекс `(user_id, status)`.

**loadouts**: `user_id fk`, `slot text check in ('P','N','B','R','Q','K','board')`, `inventory_item_id fk unique`, pk `(user_id, slot)`.

**cases**: `id serial pk`, `collection_id fk not null`, `code text unique`, `name`, `price int check > 0`, `is_active bool default true`, `sort int default 0`.

**case_drops**: `case_id fk`, `item_def_id fk`, `weight int check > 0`, pk `(case_id, item_def_id)`; скин обязан быть из коллекции кейса.

**market_listings**: `id bigserial pk`, `item_id fk inventory_items`, `seller_id fk`, `price bigint check 1..10000000`, `status text check in ('active','sold','cancelled')`, `buyer_id fk null`, `fee bigint null`, `created_at`, `closed_at null`. Частичный unique-индекс `(item_id) where status='active'`.

**item_transfers**: `id bigserial pk`, `item_id fk`, `from_user_id fk`, `to_user_id fk`, `kind text check in ('market','gift')`, `ref text` (listing id), `note text null` (≤140), `seen bool default false`, `created_at`.

**admin_audit**: `id bigserial`, `admin_id fk`, `action text`, `target text`, `payload jsonb`, `created_at`.

---

## 9. API

### 9.1 Общее
- Префикс `/api/v1`, JSON, UTF-8. Аутентификация — cookie сессии.
- Ошибка: `{"error": {"code": "SNAKE_UPPER", "message": "человекочитаемо по-русски"}}`. Коды HTTP: 400 бизнес-ошибка, 401 нет сессии, 403 нет прав/Origin/бан, 404, 409 конфликт (`VERSION_CONFLICT`, `ALREADY_IN_GAME`), 422 валидация, 429.
- Пагинация: `?cursor=<id>&limit=<1..100>` → `{"items": [...], "next_cursor": id|null}`.
- Деньги — целые ◈. Шансы — `float` в `[0,1]` + `chance_text` (строка с сервером отформатированным процентом, 2 знака).

### 9.2 Auth и профиль
| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| POST | `/auth/register` | `{login, email, password}` | 201 `Me`, ставит cookie; начисляет `starting_balance` (ledger `signup_bonus`) |
| POST | `/auth/login` | `{login, password}` | 200 `Me`, ставит cookie |
| POST | `/auth/logout` | — | 204, отзывает сессию, удаляет cookie |
| GET | `/me` | — | `Me` |
| POST | `/me/password` | `{old_password, new_password}` | 204, отзывает все прочие сессии |
| POST | `/me/daily-bonus` | — | `{balance, next_available_at}` или 400 `BONUS_COOLDOWN` |
| GET | `/me/ledger` | пагинация | ledger-записи |
| GET | `/me/games` | пагинация | `{id, opponent_login, color, result, end_reason, time_control, finished_at, elo_delta}` |
| GET | `/me/active-game` | — | `{game_id}` или `{game_id: null}` |

`Me = {id, login, role, balance, elo, daily_bonus_available_at}`.

### 9.3 Матчмейкинг и приглашения
| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| POST | `/matchmaking/queue` | `{time_control}` | 202 `{status:"queued"}`; 409 `ALREADY_IN_GAME` |
| DELETE | `/matchmaking/queue` | — | 204 |
| GET | `/matchmaking/status` | — | `{status: "idle"|"queued"|"matched", time_control, game_id}` |
| POST | `/invites` | `{time_control}` | `{code, expires_at}` |
| POST | `/invites/{code}/accept` | — | `{game_id}`; нельзя принять своё |
| DELETE | `/invites/{code}` | — | 204 (только создатель) |

Клиент узнаёт о найденной партии поллингом `/matchmaking/status` раз в 1 с (просто и без отдельного WS).

### 9.4 Партия — состояние
`GET /games/{id}` (только игроки) → `GameState`:
```json
{
  "id": "6f1c…", "version": 17, "status": "active",
  "time_control": "3+2", "you": "white", "turn": "white", "ply": 12,
  "board": [{"square": "e1", "piece": "K", "color": "white"}, …],
  "legal_moves": ["e2e4", "g1f3", "e7e8q", …],
  "check_square": null,
  "last_action": {"kind": "move", "uci": "c7c5", "san": "c5"},
  "clocks": {"white_ms": 151230, "black_ms": 162004, "running": "white", "server_time_ms": 1792500000000},
  "deps": {"limit": 10, "white_used": 2, "black_used": 0, "used_this_turn": false},
  "draw_offer_by": null,
  "result": null, "end_reason": null,
  "players": {
    "white": {"login": "nik", "elo": 1216, "loadout": {"P": {"color": "#9aa4b2"}, "board": {"light": "#454f77", "dark": "#262e4d", "accent": "#ffc93c"}, …}},
    "black": {"login": "opp", "elo": 1190, "loadout": {…}}
  }
}
```
`legal_moves` заполнено только для ходящего игрока (иначе `[]`). Фронт подсвечивает ходы по этому списку и **не** парсит FEN. `server_time_ms` нужен только для плавного тикания часов на клиенте.

### 9.5 Партия — действия
Все требуют, чтобы игрок был участником; ходовые — чтобы был его ход. Тело может содержать `expected_version` (int); при несовпадении 409 `VERSION_CONFLICT`.

| Метод | Путь | Тело | Ответ / ошибки |
|---|---|---|---|
| GET | `/games/{id}/dep-options` | — | `DepOptions` |
| POST | `/games/{id}/dep` | `{square:"c3", target:"Q"}` | `DepResult`; `NOT_YOUR_TURN`, `DEP_ALREADY_USED_THIS_TURN`, `DEP_LIMIT_REACHED`, `DEP_INVALID_PIECE`, `DEP_INVALID_TARGET`, `WOULD_CHECK_OPPONENT` |
| POST | `/games/{id}/move` | `{uci:"e2e4"}` | `GameState`; `NOT_YOUR_TURN`, `ILLEGAL_MOVE` |
| POST | `/games/{id}/resign` | — | `GameState` |
| POST | `/games/{id}/draw/offer` | — | `GameState`; `DRAW_OFFER_NOT_ALLOWED` |
| POST | `/games/{id}/draw/accept` | — | `GameState` |
| POST | `/games/{id}/draw/decline` | — | `GameState` |
| POST | `/games/{id}/abort` | — | `GameState`; `ABORT_NOT_ALLOWED` |

`DepOptions`:
```json
{
  "available": true, "unavailable_reason": null,
  "deps_left": 8,
  "pieces": [
    {"square": "c3", "piece": "N", "targets": [
      {"piece": "R", "chance": 0.6, "chance_text": "60.00%", "allowed": true, "reason": null},
      {"piece": "Q", "chance": 0.33333333, "chance_text": "33.33%", "allowed": false, "reason": "WOULD_CHECK_OPPONENT"}
    ]}
  ]
}
```
`unavailable_reason ∈ {NOT_YOUR_TURN, DEP_ALREADY_USED_THIS_TURN, DEP_LIMIT_REACHED, GAME_NOT_ACTIVE}`. Ферзи и король в `pieces` не включаются.

`DepResult`:
```json
{"success": false, "square": "c3", "from": "N", "to": "Q",
 "chance": 0.33333333, "chance_text": "33.33%", "roll_value": 0.71204,
 "roll_id": 5512, "state": { …GameState… }}
```
`roll_value` отдаётся, чтобы анимация (колесо/бар) остановилась ровно там, где выпал бросок: win-зона `[0, chance)`.

### 9.6 WebSocket `/ws/games/{id}`
- Auth — cookie, проверка `Origin`, пользователь должен быть игроком (иначе close 4403).
- При подключении сервер шлёт `{"type":"state","data":GameState}`.
- Далее сервер шлёт:
  - `{"type":"state","data":GameState}` — после любого изменения;
  - `{"type":"dep","data":{"by":"white","square":"c3","from":"N","to":"Q","success":false,"chance":0.333,"roll_value":0.712}}` — перед соответствующим `state`, чтобы **оба** игрока увидели анимацию депа;
  - `{"type":"game_over","data":{"result":"black","end_reason":"timeout","elo_delta":{"white":-16,"black":16},"rewards":{"white":0,"black":100}}}`.
- Клиент шлёт только `{"type":"ping"}`, сервер отвечает `{"type":"pong"}`. Любое другое сообщение клиента игнорируется.
- Клиент отбрасывает `state` с `version` меньше уже показанной. После переподключения — `GET /games/{id}`.

### 9.7 Коллекции, предметы и экипировка
| Метод | Путь | Ответ |
|---|---|---|
| GET | `/collections` | выпущенные и снятые коллекции `[{code, name, description, status, released_at, items_count}]` |
| GET | `/collections/{code}` | коллекция + её скины |
| GET | `/item-defs?upgrade_target=true` | каталог целей апгрейда |
| GET | `/inventory?kind=&slot=&sort=rarity\|value\|new` | `[{id, def, wear, exterior, status, equipped_slot, acquired_at}]` |
| GET | `/loadout` | `{P: Item\|null, …, board: Item\|null}` |
| PUT | `/loadout/{slot}` | тело `{inventory_item_id: int\|null}` → `Loadout`; `ITEM_NOT_OWNED`, `ITEM_SLOT_MISMATCH` |

### 9.8 Кейсы и апгрейд
| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/cases` | — | открываемые кейсы `[{id, code, name, price, collection}]` |
| GET | `/cases/{id}` | — | `{id, name, price, collection, drops:[{def, chance, chance_text}]}` |
| POST | `/cases/{id}/open` | — | `{item, strip: [def_id×60], win_index, defs: {def_id: def}, balance}`; `INSUFFICIENT_FUNDS`, `CASE_NOT_AVAILABLE` |
| POST | `/upgrade/preview` | `{input_ids, target_def_id}` | `{chance, chance_text, allowed, reason}` |
| POST | `/upgrade` | `{input_ids, target_def_id}` | `{success, chance, chance_text, roll_value, roll_id, burned_ids, item\|null}` |

### 9.9 Маркет и дарение (фаза 5)
- `GET /market?collection=&kind=&piece_type=&rarity=&def_id=&sort=price_asc|price_desc|new&cursor=` — активные лоты.
- `GET /market/defs/{def_id}` — активные лоты скина + последние 50 продаж `{price, closed_at}`.
- `POST /market/listings` `{item_id, price}`; `DELETE /market/listings/{id}`; `POST /market/listings/{id}/buy`; `GET /me/listings`.
- `POST /gifts` `{item_id, to_login, note}`; `GET /me/gifts?direction=in|out` (входящие при чтении помечаются `seen`); `GET /me/gifts/unseen-count`.

### 9.10 Лидерборд и админ
- `GET /leaderboard?by=elo|balance&limit=50` → `[{rank, login, elo, balance}]` (публично).
- Админ (роль admin, всё пишет в `admin_audit`):
  - **Каталог (фаза 4):** CRUD `/admin/collections`, `POST /admin/collections/{id}/release`, `POST /admin/collections/{id}/retire`; скины `POST /admin/collections/{id}/items`, `PATCH|DELETE /admin/item-defs/{id}`; кейсы `POST /admin/collections/{id}/cases`, `PATCH|DELETE /admin/cases/{id}`, `PUT /admin/cases/{id}/drops`, `POST /admin/cases/{id}/drops/auto`; `POST /admin/users/{id}/grant-item`.
  - **Пользователи и прочее (фаза 5):** `GET /admin/users?q=`, бан/разбан (бан отзывает сессии и сдаёт активную партию), `POST /admin/users/{id}/balance` `{delta, comment}`, `GET|PUT /admin/settings`, `GET /admin/rolls`, `GET /admin/games/{id}/events`, `GET /admin/market` (лоты и продажи), снятие лота админом.
- `GET /internal/require-admin` → 204/403 (для nginx `auth_request`; наружу nginx этот путь не проксирует).

---

## 10. Фронтенд

### 10.1 Принципы
- Фронт — **тонкий рендерер**. Он хранит в памяти только то, что получил последним ответом сервера, и ID из query-строки. После перезагрузки страницы всё запрашивается заново.
- Один модуль `js/api.js`: `fetch` с `credentials: "same-origin"`, `Content-Type: application/json`, разбор ошибок по 9.1, на 401 → редирект на `/login.html?next=…` (только относительные пути, проверка на `/` в начале и отсутствие `//`).
- Каждая страница: `<script type="module" src="js/<page>.js">`; никаких инлайн-скриптов/стилей (CSP).
- Анимации и косметическая случайность (искры, конфетти) допустимы, игровые исходы — нет.
- Мобильная вёрстка до 360 px, тапы ≥ 44 px. Шрифт `system-ui`, цифры `ui-monospace`.
- Глифы фигур: U+2654..265F + U+FE0E.

### 10.2 Страницы
| Страница | Данные | Визуальная основа из `legacy/` |
|---|---|---|
| `login.html`, `register.html` | `/auth/*` | `site/auth.html`, `site/css/style.css` |
| `index.html` (лобби) | `/me`, `/me/active-game`, `/matchmaking/*`, `/invites`, `/me/daily-bonus` | `site/index.html` (hero), `templates/layout/mobile-layout.html` |
| `game.html?id=` | `/games/{id}`, WS, `/dep-options`, `/dep`, `/move`, … | `templates/layout/board-skeleton.html`, `templates/chess/match-hud.html`, `templates/chess/board-upgrade-fx.html`, `templates/chess/upgrade-linear-race.html` |
| `inventory.html` | `/inventory`, `/loadout` | `templates/skins/skin-inventory.html`, `templates/skins/item-cards.html`, `templates/skins/board-skins.html` |
| `cases.html`, `case.html?id=` | `/cases`, `/cases/{id}`, `/open` | `templates/layout/lobby-case-grid.html`, `templates/cases/case-strip-horizontal.html` |
| `collections.html`, `collection.html?code=` | `/collections` | `templates/skins/skin-gallery.html` |
| `market.html`, `market-item.html?def=` | `/market/*` | `templates/skins/skin-gallery.html`, `templates/skins/skin-detail.html` |
| `gifts.html` | `/gifts`, `/me/gifts` | `templates/skins/gift-flow.html` |
| `upgrade.html` | `/inventory`, `/item-defs`, `/upgrade/preview`, `/upgrade` | `site/upgrade.html` (разметка колеса), `templates/wheels/wheel-conic-gradient.html` |
| `profile.html` | `/me`, `/me/ledger`, `/me/games`, `/me/password` | `site/profile.html` |
| `leaderboard.html` | `/leaderboard` | `site/leaderboard.html` |
| `admin.html` | `/admin/*`: пользователи, настройки, **коллекции → скины → кейсы → дропы → выпуск** | `site/admin.html` (только разметка) |
| общие | тосты, модалки, счётчик баланса | `templates/fx/*` |

Палитра: bg `#0b0e16`, панель `#131725`, бордер `#242b3d`, золото `#ffc93c` + цвета редкостей (4.1).

### 10.3 Игровой экран (поведение)
1. Загрузка `GET /games/{id}` → рендер, открыть WS.
2. Свой ход: клик по фигуре → подсветка ходов из `legal_moves` с этой клетки; клик по цели → `POST /move`. Превращение пешки — выбор фигуры в модалке, если в `legal_moves` есть варианты с суффиксом.
3. Кнопка «Деп» активна, если `deps.used_this_turn == false`, ход свой, `deps_left > 0`. По нажатию → `GET /dep-options` → режим выбора: фигура → цель (недопустимые показаны серым с причиной) → подтверждение с шансом → `POST /dep` → анимация бара/колеса до `roll_value` → морфинг или сгорание фигуры → новое `state`.
4. Часы: тикают локально от `clocks` + `server_time_ms`, при каждом `state` пересинхронизируются.
5. `game_over` → модалка результата с Elo и наградой.

---

## 11. Тесты и приёмка

### 11.1 Обязательные автотесты (pytest, в контейнере)
- `chess_engine` (чистые unit-тесты, без БД):
  - `test_dep_pairs_and_chances` — все 9 пар, точные шансы, запрещённые пары (N→B, Q→*, K→*, понижения).
  - `test_dep_success_replaces_piece` / `test_dep_fail_removes_piece`.
  - `test_dep_forbidden_direct_check` (P→Q рядом с королём соперника).
  - `test_dep_forbidden_discovered_check_on_fail` (слон за конём).
  - `test_dep_allowed_self_discovered_check` (провал вскрывает шах себе → разрешено, затем ходы только из-под шаха).
  - `test_dep_fail_leads_to_selfmate` и `test_dep_fail_leads_to_stalemate`.
  - `test_dep_rook_clears_castling` (обе стороны, оба исхода).
  - `test_dep_resets_fifty_and_repetition`.
  - `test_dep_insufficient_material_after_fail`.
- Сервисы (с тестовой PG):
  - лимит 1 деп за ход и 10 за партию; деп в чужой ход; деп после хода невозможен;
  - `test_dep_probability` — 10 000 бросков через подменённый RNG/реальный CSPRNG, частота в пределах ±2% от шанса;
  - часы: флаг, инкремент, abort без первого хода, флаг против недостаточного материала;
  - экономика: нельзя уйти в минус, конкурентное открытие кейсов (параллельные запросы не дают отрицательный баланс), ledger сходится с балансом;
  - апгрейд: границы шанса, сгорание входов в обоих исходах, автоснятие экипировки, чужие предметы;
  - безопасность: без cookie → 401; чужой `Origin` → 403; забаненный → 403; не-игрок → 404 на партию; не-админ → 403 на `/admin/*`; cookie содержит только `sid`-токен.
- `test_frontend_static.py` — запрещённые API хранилищ, `document.cookie`, `innerHTML` с `${`, `Math.random` в файлах, где он не помечен комментарием `// cosmetic`.

### 11.2 Приёмка (ручная)
1. На чистом Linux: `cp .env.example .env && docker compose up -d --build` → `http://localhost:8080` открывается.
2. Два браузера (обычный + инкогнито), два аккаунта, оба встают в очередь 3+2 → партия создаётся, ходы видны обоим в реальном времени.
3. Деп: шанс отображается, анимация видна обоим, после успеха фигура заменена, после провала исчезла; 11-й деп невозможен; второй деп за ход невозможен.
4. Кейс открывается, баланс уменьшается, предмет в инвентаре; экипировка видна сопернику в новой партии.
5. Апгрейд работает, входы исчезают.
6. В devtools: в Application → Storage пусто, единственная cookie — `sid` (HttpOnly). Подмена любых данных в браузере не меняет баланс/роль/исходы.
7. `docker compose down && docker compose up -d` — данные сохранились.

---

## 12. Фазы

| Фаза | Task | Содержимое |
|---|---|---|
| 1 | `tasks/task-001-infra-auth.md` | compose, nginx, migrate, модели users/sessions/settings/ledger/admin_audit, auth, Origin, rate-limit, CLI, тесты, перенос в `legacy/` |
| 2 | `task-002` | `chess_engine` + все unit-тесты 11.1 по движку |
| 3 | `task-003` | games, invites, матчмейкинг, WS, worker (часы), Elo, награды |
| 4 | `task-004` | коллекции, скины, кейсы, дропы, инвентарь, экипировка (+ снапшот в партию), открытие кейсов, апгрейд, админ-API каталога, сид Genesis |
| 5 | `task-005` | маркет, дарение, история передач, лидерборд, админ-API пользователей/настроек/бросков/маркета |
| 6 | `task-006` | фронтенд по разделу 10 (включая админку каталога) |

После каждой фазы — полное ревью кода, прогон тестов, затем следующая фаза.
