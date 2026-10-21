# task-003 — Партии: создание, ходы, депы, часы, матчмейкинг, WebSocket, Elo, награды

Прочитай перед работой: `docs/TZ.md` разделы 3.3–3.8, 5, 6.4, 8 (invites, games, game_events, rolls), 9.3–9.6.
Движок `app/chess_engine` уже готов и проверен: используй его, **не дублируй** шахматную логику.

## Правила для исполнителя
Те же, что в task-001/002. Отдельно:
1. Время везде берётся только через `from app.core import clock` → `clock.now()`. Никаких `datetime.now()` в коде игр. Импорт именно модуля, не функции: тесты подменяют `clock.now`.
2. Случайность — только через `app.services.rolls.get_rng()`.
3. Любой `SELECT … FOR UPDATE` — с `.execution_options(populate_existing=True)`.
4. Публикация в Redis и изменения ZSET — **только после коммита**, через `after_commit` (п. 2.2).
5. Порядок блокировок (против дедлоков): сначала строка `games`, потом строки `users` по возрастанию id. Никогда наоборот.
6. Если в задании что-то не сходится или неясно — остановись и спроси.

---

## 1. Миграция `alembic/versions/0002_games.py` (руками, как 0001)

### `invites`
`code text pk`, `creator_id bigint fk users not null`, `time_control text not null`, `created_at timestamptz not null default now()`, `expires_at timestamptz not null`, `game_id uuid fk games null`.

### `games`
| Колонка | Тип | Примечание |
|---|---|---|
| id | uuid pk | генерируется в Python `uuid.uuid4()` |
| status | text not null | check `('active','finished','aborted')` |
| time_control | text not null | `"3+2"` |
| base_ms, inc_ms | int not null | |
| white_id, black_id | bigint fk users not null | |
| fen | text not null | |
| ply | int not null default 0 | |
| repetition | jsonb not null default `'{}'` | `{position_key: count}` |
| white_ms, black_ms | bigint not null | остаток на момент `turn_started_at` |
| turn_started_at | timestamptz not null | |
| clock_running | bool not null default false | |
| abort_deadline | timestamptz null | |
| dep_used_this_turn | bool not null default false | |
| white_deps, black_deps | smallint not null default 0 | |
| draw_offer_by | text null | check `('white','black')` |
| white_last_offer_ply, black_last_offer_ply | int null | |
| result | text null | check `('white','black','draw')` |
| end_reason | text null | check: `checkmate, stalemate, insufficient_material, fifty_move, threefold, resign, timeout, timeout_vs_insufficient, agreement, abort, abort_no_first_move` |
| white_loadout, black_loadout | jsonb not null default `'{}'` | в task-004 сюда пишется снапшот экипировки |
| white_elo_before, black_elo_before | int not null | |
| white_elo_after, black_elo_after | int null | |
| white_reward, black_reward | int null | |
| version | int not null default 0 | |
| created_at | timestamptz not null default now() | |
| finished_at | timestamptz null | |

Индексы: `(white_id, finished_at desc)`, `(black_id, finished_at desc)`, `(status)`.

### `active_players`
`user_id bigint pk fk users`, `game_id uuid fk games not null`. **PK гарантирует одну активную партию на игрока**: вставка второй строки для того же пользователя падает с IntegrityError.

### `game_events`
По TZ §8: `id bigserial pk`, `game_id uuid fk`, `seq int not null`, `ply int not null`, `actor text` (check `white|black|system`), `kind text` (check `move, dep, resign, draw_offer, draw_accept, draw_decline, abort, flag, game_over`), `payload jsonb not null`, `fen_after text not null`, `white_ms bigint`, `black_ms bigint`, `created_at`. Unique `(game_id, seq)`.

### `rolls`
По TZ §8: `id bigserial pk`, `user_id bigint fk not null`, `kind text` (check `dep, case_open, upgrade`), `ref text not null`, `chance numeric(10,8) null`, `roll_value double precision not null`, `input jsonb not null`, `outcome jsonb not null`, `created_at`. Индекс `(user_id, created_at desc)`.

Модели: `app/models/game.py` (`Game`, `GameEvent`, `ActivePlayer`, `Invite`), `app/models/roll.py` (`Roll`); добавить в `app/models/__init__.py`.

## 2. Инфраструктурные добавки

### 2.1 `app/core/clock.py`
```python
from datetime import UTC, datetime

def now() -> datetime:
    return datetime.now(UTC)

def to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)
```

### 2.2 `app/db.py` — хуки после коммита
```python
AfterCommit = Callable[[], Awaitable[None]]

def after_commit(db: AsyncSession, fn: AfterCommit) -> None:
    db.info.setdefault("after_commit", []).append(fn)

async def run_after_commit(db: AsyncSession) -> None:
    for fn in db.info.pop("after_commit", []):
        try:
            await fn()
        except Exception:
            logger.exception("after_commit hook failed")

async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        async with session.begin():
            yield session
        await run_after_commit(session)
```
Если внутри запроса было исключение, `session.begin()` откатывает транзакцию, и хуки не выполняются. Это и нужно. Проверено: в FastAPI 0.115.6 код после `yield` выполняется **до** отправки ответа клиенту.

### 2.3 `app/services/rolls.py`
```python
class Rng(Protocol):
    def random(self) -> float: ...

_rng: Rng = secrets.SystemRandom()

def get_rng() -> Rng: return _rng
def set_rng(rng: Rng) -> None: ...          # только для тестов
def reset_rng() -> None: ...                # вернуть SystemRandom

async def record_roll(db, *, user_id: int, kind: str, ref: str, chance: float | None,
                      roll_value: float, input: dict, outcome: dict) -> int   # flush, вернуть id
```

### 2.4 `app/services/pubsub.py`
```python
def game_channel(game_id: uuid.UUID) -> str: return f"game:{game_id}"
async def publish_game(game_id: uuid.UUID, message: dict) -> None   # redis PUBLISH json.dumps
```
Формат сообщения: `{"version": int, "dep": DepEvent | None, "game_over": GameOver | None}` (схемы в п. 4).

### 2.5 `app/services/game_clock.py` (чистые функции, без БД)
```python
def parse_time_control(tc: str) -> tuple[int, int]      # "3+2" -> (180000, 2000); иначе ValueError
def turn_color(game) -> str                             # из game.fen: "white" | "black"
def remaining_ms(game, color: str, now: datetime) -> int
    # если game.clock_running и color == turn_color(game):
    #     ms_цвета - (now - turn_started_at) в мс, но не меньше 0
    # иначе ms_цвета
def deadline(game) -> datetime | None
    # status != "active" -> None
    # clock_running -> turn_started_at + ms_ходящего
    # иначе abort_deadline (может быть None)
def is_expired(game, now: datetime) -> bool             # deadline is not None and now >= deadline
```

### 2.6 `app/services/elo.py`
```python
def elo_update(ra: int, rb: int, score_a: float, k: int = 32) -> tuple[int, int]
    # ea = 1 / (1 + 10 ** ((rb - ra) / 400)); new_a = round(ra + k*(score_a - ea)); new_b = round(rb + k*((1-score_a) - (1-ea)))
```

## 3. `app/services/games.py` — вся логика партий

Внутренний хелпер:
```python
async def lock_game(db, game_id: uuid.UUID) -> Game        # FOR UPDATE + populate_existing; нет -> AppError(404, "GAME_NOT_FOUND", "Партия не найдена")
def color_of(game, user_id) -> str                         # "white"/"black"; не игрок -> AppError(404, "GAME_NOT_FOUND", ...)
def bump(game) -> int                                      # game.version += 1; вернуть новую версию
async def add_event(db, game, *, actor, kind, payload) -> None   # seq = game.version (вызывать после bump), ply, fen_after, white_ms, black_ms
def schedule_deadline(db, game) -> None
    # after_commit: если deadline(game) есть -> ZADD clock:deadlines {str(id): to_ms(deadline)}, иначе ZREM
def publish(db, game, *, dep=None, game_over=None) -> None
    # after_commit: publish_game(game.id, {"version": game.version, "dep": dep, "game_over": game_over})
```

Ошибки (все `AppError`):
| Код | HTTP | Когда |
|---|---|---|
| `GAME_NOT_FOUND` | 404 | нет партии или пользователь не её игрок |
| `GAME_NOT_ACTIVE` | 400 | status != active |
| `TIME_EXPIRED` | 400 | `is_expired(game, now)`: флаг/abort поставит worker |
| `NOT_YOUR_TURN` | 400 | |
| `ILLEGAL_MOVE` | 400 | `EngineError` из `apply_move` |
| `DEP_ALREADY_USED_THIS_TURN` | 400 | |
| `DEP_LIMIT_REACHED` | 400 | депов цвета ≥ `DEP_LIMIT_PER_GAME` |
| `DEP_INVALID_PIECE`, `DEP_INVALID_TARGET`, `WOULD_CHECK_OPPONENT` | 400 | `EngineError` из движка, код как есть |
| `VERSION_CONFLICT` | 409 | передан `expected_version` и он != `game.version` |
| `ALREADY_IN_GAME` | 409 | у пользователя уже есть активная партия |
| `INVALID_TIME_CONTROL` | 400 | tc не из настройки `time_controls` |
| `DRAW_OFFER_NOT_ALLOWED` | 400 | |
| `NO_DRAW_OFFER` | 400 | accept/decline без предложения от соперника |
| `ABORT_NOT_ALLOWED` | 400 | |

Каждое игровое действие (move/dep/resign/draw/abort) начинается одинаково:
1. `game = await lock_game(db, game_id)`; `color = color_of(game, user.id)`;
2. `expected_version` передан и не совпал → `VERSION_CONFLICT`;
3. `game.status != "active"` → `GAME_NOT_ACTIVE`;
4. `is_expired(game, now)` → `TIME_EXPIRED`.

### 3.1 `create_game(db, user_a_id, user_b_id, time_control, now) -> Game`
1. tc не в `await get_setting(db, "time_controls")` → `INVALID_TIME_CONTROL`.
2. Цвета: `get_rng().random() < 0.5` → `user_a` белые, иначе чёрные.
3. Загрузить обоих пользователей (без блокировки), снять `elo` в `*_elo_before`.
4. Создать `Game`: стартовый FEN (`chess.STARTING_FEN`), `ply=0`, `repetition={position_key(start): 1}`, `white_ms=black_ms=base_ms`, `turn_started_at=now`, `clock_running=False`, `abort_deadline = now + abort_first_move_s`, `version=0`.
5. Добавить `ActivePlayer` для обоих, `flush()`. `IntegrityError` → `ALREADY_IN_GAME`. Важно: делать это внутри `async with db.begin_nested():`, чтобы откатилась только вложенная транзакция.
6. `schedule_deadline`, `publish` не нужен (подписчиков ещё нет).

### 3.2 `do_move(db, user, game_id, uci, expected_version, now) -> Game`
1. Общие шаги; цвет хода (`turn_color`) != color → `NOT_YOUR_TURN`.
2. `res = apply_move(board, uci)` (`EngineError` → `ILLEGAL_MOVE`).
3. Часы:
   - если `clock_running`: `ms_ходящего = remaining_ms(game, color, now) + inc_ms`;
   - `turn_started_at = now`;
   - если новый `ply == 1` (белые сделали первый ход): `abort_deadline = now + abort_first_move_s`;
   - если новый `ply == 2` (чёрные сделали первый ход): `clock_running = True`, `abort_deadline = None`.
4. `fen = res.board.fen()`, `ply += 1`, `dep_used_this_turn = False`.
5. Если `draw_offer_by` == цвет соперника → `draw_offer_by = None` (ход = отказ от предложения).
6. Повторения: если `res.irreversible` → `repetition = {}`; затем `repetition[position_key] += 1` (новый dict, не мутировать старый на месте, иначе SQLAlchemy не увидит изменения JSONB).
7. `bump`, событие `move` `{uci, san}`.
8. `outcome = game_outcome(res.board, repetition[key])` → если есть, `finish_game(...)`.
9. `schedule_deadline`, `publish` (с `game_over`, если партия закончилась).

### 3.3 `do_dep(db, user, game_id, square, target, expected_version, now) -> tuple[Game, DepResolution, int]`
1. Общие шаги; не его ход → `NOT_YOUR_TURN`.
2. `dep_used_this_turn` → `DEP_ALREADY_USED_THIS_TURN`; депы цвета ≥ 10 → `DEP_LIMIT_REACHED`.
3. `validate_dep(board, square, target)` (`EngineError` → тот же код). **Сначала** валидация, **потом** бросок.
4. `roll = get_rng().random()`; `multiplier = float(await get_setting(db, "dep_multiplier"))`; `res = resolve_dep(board, square, target, roll, multiplier)`.
5. `roll_id = record_roll(kind="dep", ref=str(game.id), chance=res.chance, roll_value=roll, input={"square", "from", "to", "fen_before"}, outcome={"success", "fen_after"})`.
6. `fen = res.board.fen()`, `dep_used_this_turn = True`, депы цвета `+= 1`, `repetition = {position_key(res.board): 1}`. Часы не трогать.
7. `bump`, событие `dep` `{square, from, to, chance, success, roll_id}`.
8. `outcome = game_outcome(res.board, 1)` → `finish_game`.
9. `schedule_deadline`, `publish(dep=DepEvent, game_over=...)`.

### 3.4 Прочие действия
- `do_resign` → `finish_game(result=соперник, end_reason="resign")`, событие `resign`.
- `do_draw_offer`: запрещено (`DRAW_OFFER_NOT_ALLOWED`), если `draw_offer_by is not None` или `last_offer_ply цвета is not None and ply < last_offer_ply + 2`. Иначе `draw_offer_by = color`, `last_offer_ply цвета = ply`, событие `draw_offer`.
- `do_draw_accept`: `draw_offer_by` != цвет соперника → `NO_DRAW_OFFER`; иначе `finish_game("draw", "agreement")`, событие `draw_accept`.
- `do_draw_decline`: та же проверка; `draw_offer_by = None`, событие `draw_decline`.
- `do_abort`: `ply >= 2` → `ABORT_NOT_ALLOWED`; иначе `finish_game(None, "abort", aborted=True)`, событие `abort`.
- Каждое действие: `bump`, событие, `schedule_deadline`, `publish`.

### 3.5 `check_timeout(db, game, now) -> bool` (вызывает worker; партия уже заблокирована)
- не active или не `is_expired` → `False`;
- `clock_running is False` (истёк `abort_deadline`) → `finish_game(None, "abort_no_first_move", aborted=True)`, событие `abort` с actor `system`;
- иначе флаг: `ms_ходящего = 0`; `opp` = соперник ходящего; `can_win_on_time(board, opp)` → `finish_game(opp, "timeout")`, иначе `finish_game("draw", "timeout_vs_insufficient")`; событие `flag` с actor `system`;
- `bump`, `schedule_deadline`, `publish`; вернуть `True`.

### 3.6 `finish_game(db, game, result, end_reason, now, aborted=False) -> GameOver`
1. `status = "aborted" if aborted else "finished"`, `result`, `end_reason`, `finished_at = now`, `draw_offer_by = None`, `clock_running = False`.
2. Перед финишем зафиксировать часы: если часы шли, `ms_ходящего = remaining_ms(game, ходящий, now)`.
3. Удалить обе строки `ActivePlayer` этой партии.
4. Если `aborted` → Elo и награды не трогать, вернуть `GameOver(result=None, end_reason, elo_delta=None, rewards={"white": 0, "black": 0})`.
5. Иначе: `lock_user` обоих **по возрастанию id**; `elo_update(white.elo, black.elo, score_white)` (1 / 0.5 / 0); записать `*_elo_after`, обновить `users.elo`.
6. Награды: для каждого игрока, если `game.ply >= reward_min_plies` и число строк `ledger` этого пользователя с `reason in ('game_win','game_draw')` и `created_at >= полночь UTC сегодня` < `reward_games_per_day`:
   победитель → `apply_delta(+game_win_reward, "game_win", ref=str(game.id))`; при ничьей оба → `game_draw_reward`, `"game_draw"`. Записать `white_reward`/`black_reward` (0, если не положено).
7. Событие `game_over` `{result, end_reason}` (actor `system`).
8. Вернуть `GameOver`.

`finish_game` сам не делает `bump`/`publish`: это делает вызвавшее действие (один `bump` на действие, событие `game_over` добавляется с тем же `seq`+1 — для этого `add_event` для game_over вызывать после ещё одного `bump`). Итого при ходе, закончившем партию: версия +2, два события (`move`, `game_over`).

## 4. Схемы `app/schemas/games.py`
Все с `extra="forbid"`. Поля и вложенность — **ровно** как в TZ 9.4/9.5/9.6:
- `MoveIn {uci: constr(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$"), expected_version: int | None = None}`
- `DepIn {square: constr(pattern=r"^[a-h][1-8]$"), target: Literal["N","B","R","Q"], expected_version: int | None = None}`
- `ActionIn {expected_version: int | None = None}` (resign/draw/abort; тело может отсутствовать)
- `TimeControlIn {time_control: str}`
- `GameStateOut`, `DepOptionsOut`, `DepResultOut`, `DepEvent {by, square, from, to, success, chance, roll_value}`, `GameOver {result, end_reason, elo_delta: {white, black} | None, rewards: {white, black}}`. Поле `from` — через `Field(alias="from")` и `model_config = ConfigDict(populate_by_name=True)`; ответ сериализовать `by_alias=True`.

`app/services/game_view.py`:
```python
def build_state(game, viewer_user_id, players: dict[str, User], now) -> GameStateOut
```
- `you` = цвет зрителя; `turn` = `turn_color`; `board` = `board_squares`; `legal_moves` = `legal_moves_uci`, только если партия активна и ход зрителя, иначе `[]`;
- `check_square` = клетка короля ходящего, если `board.is_check()`, иначе `None`;
- `last_action` = payload последнего события `move`/`dep` с полем `kind` (или `None`);
- `clocks = {white_ms: remaining_ms(white), black_ms: remaining_ms(black), running: turn_color if clock_running and active else None, server_time_ms: to_ms(now)}`;
- `deps = {limit: 10, white_used, black_used, used_this_turn}`;
- `players.{color} = {login, elo, loadout}` (`loadout` из `games.*_loadout`).

```python
def build_dep_options(game, viewer_color, multiplier) -> DepOptionsOut
```
`available=False` и причина по приоритету: `GAME_NOT_ACTIVE` → `NOT_YOUR_TURN` → `DEP_ALREADY_USED_THIS_TURN` → `DEP_LIMIT_REACHED`. `pieces` = `list_dep_options` (даже если `available=False`; UI покажет серым). `deps_left = 10 - used`.

## 5. Матчмейкинг `app/services/matchmaking.py`
Redis-ключи: `mm:queue:{tc}` (LIST user_id), `mm:user:{user_id}` (STRING tc, TTL 10 с — heartbeat).
- `enqueue(db, user, tc)`: tc вне настроек → `INVALID_TIME_CONTROL`; есть `ActivePlayer` → `ALREADY_IN_GAME`; если `mm:user:{id}` уже есть → только продлить TTL (не дублировать в очереди); иначе `SET mm:user:{id} tc EX 10` + `RPUSH mm:queue:{tc} id`.
- `dequeue(user)`: прочитать tc, `LREM mm:queue:{tc} 0 id`, `DEL mm:user:{id}`.
- `status(db, user)`: есть `ActivePlayer` → `{"status": "matched", "time_control": game.tc, "game_id": ...}`; есть `mm:user` → продлить TTL на 10 с, `{"status": "queued", "time_control": tc, "game_id": None}`; иначе `idle`.
- `tick(now)` (вызывает worker, отдельная `SessionLocal` на каждую пару): для каждого tc из настроек, пока в очереди ≥ 2 живых:
  1. `LPOP` по одному, пропуская id, у которых нет `mm:user:{id}` или он равен другому tc (сбежал/истёк heartbeat);
  2. для пары `(a, b)` открыть транзакцию, `create_game(db, a, b, tc, now)`; успех → коммит, `run_after_commit`, `DEL mm:user:{a}`, `DEL mm:user:{b}`;
  3. `ALREADY_IN_GAME` → откат; найти, кто из них уже в партии (по `ActivePlayer`), его `DEL mm:user`, второго вернуть `LPUSH` в начало очереди и продолжить.
- Worker запускается **в одном экземпляре** (так и в compose: без `replicas`), поэтому без Lua-скриптов.

## 6. Роутеры

### `app/api/games.py` (все требуют `current_user`; rate-limit `hit(f"rl:game:{user.id}", 10, 1)` на POST)
| Метод | Путь | Ответ |
|---|---|---|
| GET | `/api/v1/games/{game_id}` | `GameStateOut` (для finished тоже) |
| GET | `/api/v1/games/{game_id}/dep-options` | `DepOptionsOut` |
| POST | `/api/v1/games/{game_id}/move` | `GameStateOut` |
| POST | `/api/v1/games/{game_id}/dep` | `DepResultOut` (`state` внутри) |
| POST | `/api/v1/games/{game_id}/resign` | `GameStateOut` |
| POST | `/api/v1/games/{game_id}/draw/offer` | `GameStateOut` |
| POST | `/api/v1/games/{game_id}/draw/accept` | `GameStateOut` |
| POST | `/api/v1/games/{game_id}/draw/decline` | `GameStateOut` |
| POST | `/api/v1/games/{game_id}/abort` | `GameStateOut` |

`game_id: uuid.UUID` (кривой uuid → 422). GET без блокировки (обычный select).

### `app/api/matchmaking.py`
`POST /api/v1/matchmaking/queue` (202, `{"status":"queued"}`), `DELETE /api/v1/matchmaking/queue` (204), `GET /api/v1/matchmaking/status`.

### `app/api/invites.py`
- `POST /api/v1/invites` `{time_control}` → `{code, expires_at}`. Проверки: tc валиден, у создателя нет `ActivePlayer`. `code` — 10 символов из алфавита `abcdefghjkmnpqrstuvwxyz23456789` через `secrets.choice`. `expires_at = now + 10 мин`.
- `POST /api/v1/invites/{code}/accept` → `{game_id}`. `SELECT invite FOR UPDATE populate_existing`; нет → 404 `INVITE_NOT_FOUND`; `game_id` уже есть или `expires_at <= now` → 400 `INVITE_EXPIRED`; свой → 400 `INVITE_OWN`. `create_game(db, invite.creator_id, user.id, invite.time_control, now)`, `invite.game_id = game.id`.
- `DELETE /api/v1/invites/{code}` → 204; только создатель (иначе 404 `INVITE_NOT_FOUND`), только пока `game_id is None`.

### `app/api/me.py` — добавить
- `GET /api/v1/me/active-game` → `{"game_id": uuid | None}`.
- `GET /api/v1/me/games?before=<iso datetime>&limit=1..100` → `{"items": [...], "next_before": iso | None}`. Элемент: `{id, opponent_login, color, result, end_reason, time_control, finished_at, elo_delta}`. Только finished/aborted, сортировка `finished_at desc`, фильтр `finished_at < before`. (Курсор по времени вместо id: у партий uuid. Это осознанное отличие от TZ 9.1.)

### `app/api/ws.py` — `@router.websocket("/ws/games/{game_id}")`
1. Origin уже проверен middleware.
2. Токен из `websocket.cookies.get(settings.cookie_name)`; в отдельной `SessionLocal()` резолвить сессию и партию. Нет сессии, бан, нет партии или пользователь не игрок → `await websocket.close(code=4403)` **без** accept.
3. `accept()`; подписаться `pubsub.subscribe(game_channel(id))` **до** отправки первого состояния (чтобы не потерять событие); отправить `{"type": "state", "data": state}`.
4. Две корутины в `asyncio.wait(..., return_when=FIRST_COMPLETED)`:
   - чтение клиента: `receive_json()`; `{"type": "ping"}` → `{"type": "pong"}`; прочее игнорировать; `WebSocketDisconnect` → выход;
   - чтение pubsub: на каждое сообщение — новая `SessionLocal()`, загрузить партию и игроков, затем отправить по порядку `ws_messages(message, state)`.
5. В `finally`: отменить оставшуюся задачу, `unsubscribe`, `aclose` pubsub.

Чистая функция (тестируется отдельно):
```python
def ws_messages(message: dict, state: dict) -> list[dict]:
    out = []
    if message.get("dep"): out.append({"type": "dep", "data": message["dep"]})
    out.append({"type": "state", "data": state})
    if message.get("game_over"): out.append({"type": "game_over", "data": message["game_over"]})
    return out
```

## 7. Worker `app/worker.py`
Заменить заглушку. Цикл до SIGTERM/SIGINT:
- при старте `rebuild_deadlines()`: для всех `games.status='active'` пересчитать `deadline` и `ZADD` (восстановление после потери Redis);
- каждые 200 мс `tick_clocks(clock.now())`: `ZRANGEBYSCORE clock:deadlines -inf <now_ms> LIMIT 0 50`; для каждого id — своя транзакция: `lock_game`; не active → `ZREM`; иначе `check_timeout`; если не истёк — `schedule_deadline` (пересчитать). Коммит, `run_after_commit`;
- каждые 500 мс `matchmaking.tick(clock.now())`;
- исключение в одной итерации логируется и не роняет цикл.

`tick_clocks` и `rebuild_deadlines` — функции уровня модуля, их вызывают тесты.

## 8. Тесты

### `tests/conftest.py` — добавить
- В autouse-очистку: `TRUNCATE ... games, game_events, active_players, invites, rolls ...` (добавить к списку), `rolls.reset_rng()`.
- `class FixedRng`: принимает список чисел, `random()` отдаёт их по кругу.
- Фикстура `rng` → `FixedRng` с `set_rng`; тест задаёт значения: `rng.values = [0.0]`.
- Фикстура `frozen` → объект с `.now` (по умолчанию `2026-10-21 12:00 UTC`) и `.advance(seconds)`; monkeypatch `app.core.clock.now`.
- Фикстуры `alice`, `bob` — отдельные `AsyncClient`, каждый зарегистрирован (свои cookie, Origin `http://test`).
- Хелпер `async def start_game(alice, bob, rng, tc="3+2") -> str`: `rng.values=[0.0]`; alice создаёт инвайт, bob принимает → alice белые. Вернуть `game_id`.
- Хелпер `async def set_fen(game_id, fen, **fields)`: напрямую в БД выставить `fen`, `repetition={position_key: 1}` и прочие поля (`ply`, `white_deps` и т.д.).

### `tests/test_game_clock.py` (чистые)
- `test_parse_time_control` — `"3+2"` → `(180000, 2000)`, `"10+0"` → `(600000, 0)`; `"3"`, `"a+b"`, `""` → `ValueError`.
- `test_remaining_ms` — часы не идут → остаток как есть; идут, ход белых, прошло 1.5 с → `white_ms - 1500`, `black_ms` без изменений; не уходит ниже 0.
- `test_deadline` — finished → `None`; не идут → `abort_deadline`; идут → `turn_started_at + ms_ходящего`.
- `test_elo_update` — `(1200, 1200, 1)` → `(1216, 1184)`; `(1200, 1200, 0.5)` → `(1200, 1200)`; `(1400, 1200, 1)` → `(1408, 1192)`; `(1400, 1200, 0)` → `(1376, 1224)`.
- `test_ws_messages` — без dep и game_over → `[state]`; с dep → `[dep, state]`; с обоими → `[dep, state, game_over]`.

### `tests/test_games.py` (HTTP)
Создание и доступ:
- `test_invite_creates_game` — alice белые, оба видят `GameStateOut`: `you` разный, `legal_moves` у alice 20, у bob `[]`; `/me/active-game` у обоих = game_id.
- `test_stranger_cannot_see_game` — третий пользователь: GET → 404 `GAME_NOT_FOUND`; move → 404.
- `test_invite_errors` — принять свой → `INVITE_OWN`; несуществующий → `INVITE_NOT_FOUND`; после `frozen.advance(601)` → `INVITE_EXPIRED`; повторное принятие принятого → `INVITE_EXPIRED`; неверный tc → `INVALID_TIME_CONTROL`.
- `test_one_active_game_per_user` — в партии: `POST /invites` → 409; `POST /matchmaking/queue` → 409; третий создаёт инвайт, alice принимает → 409 `ALREADY_IN_GAME`.

Ходы:
- `test_move_flow` — e2e4 от alice → 200, версия 1; повтор от alice → `NOT_YOUR_TURN`; `e7e5` от bob → 200; `e1e8` → `ILLEGAL_MOVE`.
- `test_move_version_conflict` — `expected_version: 5` → 409.
- `test_concurrent_moves` — `asyncio.gather` из 5 одинаковых `e2e4` от alice → ровно один 200, остальные 400 `NOT_YOUR_TURN`; ровно одно событие `move` в БД.
- `test_fools_mate_finishes_game` — f3, e5, g4, Qh4 → `status finished`, `result black`, `checkmate`; `active_players` пуста; Elo 1184/1216; наград нет (ply 4 < 10).
- `test_threefold` — `g1f3 g8f6 f3g1 f6g8` дважды → после 8-го полухода `draw`/`threefold`.

Депы:
- `test_dep_success_and_fail` — `rng.values=[0.0]`: деп b1→Q → `success`, на b1 ферзь, `deps.white_used == 1`, в `rolls` строка `kind=dep`, `roll_value=0.0`, `chance≈1/3`. Новая партия, `rng.values=[0.99]`: провал, b1 пуста.
- `test_dep_once_per_turn_and_limit` — второй деп в тот же ход → `DEP_ALREADY_USED_THIS_TURN`; после хода белых и хода чёрных снова можно; `set_fen(..., white_deps=10)` → `DEP_LIMIT_REACHED`; деп в ход соперника → `NOT_YOUR_TURN`.
- `test_dep_engine_errors` — `set_fen("4k3/8/4P3/8/8/8/8/4K3 w - - 0 1")` → деп e6→Q → `WOULD_CHECK_OPPONENT`, в `rolls` записей нет (бросок не делался); деп e1 → `DEP_INVALID_PIECE`.
- `test_dep_selfmate_finishes_game` — `set_fen("k7/8/8/8/8/8/6PP/r2N3K w - - 0 1", ply=20)`, `rng.values=[0.99]`, деп d1→R → партия finished, `black`, `checkmate`; Elo обновлён; bob получил `game_win_reward` (ledger `game_win`), alice — ничего.
- `test_dep_options_endpoint` — старт: у alice `available=true`, 14 фигур, `deps_left=10`; у bob `available=false`, `NOT_YOUR_TURN`; после депа alice — `DEP_ALREADY_USED_THIS_TURN`.
- `test_dep_resets_repetition` — после депа `games.repetition` содержит ровно один ключ со значением 1.

Прочие действия:
- `test_resign` — bob сдаётся → `white`, `resign`.
- `test_draw_flow` — alice предлагает → `draw_offer_by=white`; повторно → `DRAW_OFFER_NOT_ALLOWED`; bob отклоняет → `None`; alice предлагает снова сразу → `DRAW_OFFER_NOT_ALLOWED` (ply не вырос на 2); alice e4, bob e5; alice предлагает → ок; bob принимает → `draw`, `agreement`.
- `test_draw_offer_cleared_by_opponent_move` — alice e4, alice предлагает, bob e5 → `draw_offer_by is None`; bob accept → `NO_DRAW_OFFER`.
- `test_abort` — на ply 0 bob abort → `aborted`, `abort`, Elo без изменений, `*_elo_after is None`; в другой партии после двух ходов → `ABORT_NOT_ALLOWED`.
- `test_rewards_daily_cap` — настройка `reward_games_per_day=1`; две партии подряд, каждая через `set_fen(..., ply=20)` + resign → награда только за первую.
- `test_me_games_history` — после двух завершённых партий `/me/games` отдаёт обе, свежая первой, `elo_delta` корректен; пагинация `limit=1` + `next_before`.
- `test_publish_after_commit` — подписаться на `game_channel(id)` своим `redis_client.pubsub()`; alice e4; получить сообщение (таймаут 2 с); `message.version` == `GET /games/{id}`.version; при ходе, завершившем партию, в сообщении есть `game_over`.

### `tests/test_clock_worker.py`
- `test_clock_starts_after_black_first_move` — после e4 `clock_running=False`; после e5 `True`, `abort_deadline is None`; `frozen.advance(10)`, alice ходит → `white_ms == 180000 - 10000 + 2000`.
- `test_flag_by_worker` — после двух ходов `frozen.advance(181)`, `tick_clocks(clock.now())` → партия finished, ход был белых → `black`, `timeout`; `white_ms == 0`.
- `test_flag_vs_insufficient` — `set_fen("4k3/8/8/8/8/8/r7/N3K3 b - - 0 1", ply=20, clock_running=True)` (ход чёрных, у чёрных ладья, у белых только конь), `frozen.advance(181)`, tick → `draw`, `timeout_vs_insufficient`.
- `test_move_after_expiry_rejected` — после истечения, но до tick: ход → 400 `TIME_EXPIRED`.
- `test_abort_no_first_move` — сразу после создания `frozen.advance(31)`, tick → `aborted`, `abort_no_first_move`; Elo не изменился.
- `test_rebuild_deadlines` — создать партию, `redis_client.delete("clock:deadlines")`, `rebuild_deadlines()` → в ZSET есть id партии со score = `to_ms(abort_deadline)`.

### `tests/test_matchmaking.py`
- `test_queue_and_match` — alice и bob в очередь 3+2 → оба `queued`; `matchmaking.tick(now)` → оба `matched` с одним `game_id`; очередь пуста; `mm:user:*` удалены.
- `test_dequeue` — встать и выйти → `idle`, очередь пуста.
- `test_queue_errors` — tc `"1+0"` → `INVALID_TIME_CONTROL`; повторный enqueue не дублирует (`LLEN == 1`).
- `test_stale_heartbeat_skipped` — alice в очереди, `DEL mm:user:{alice}` (имитация истёкшего TTL), bob в очереди, tick → партии нет, bob остаётся `queued`.
- `test_already_in_game_pushed_back` — alice и bob в очереди; до tick alice попадает в партию с третьим через инвайт; tick → для bob партии нет, bob всё ещё `queued` и первый в очереди.

## 9. Проверка (приложить вывод)
```bash
make test        # все зелёные: 61 старых + новые
make up && docker compose ps     # worker running, в логах нет исключений
docker compose logs worker --tail=20
```
В конце: список файлов, отступления (или «отступлений нет»), вопросы.
