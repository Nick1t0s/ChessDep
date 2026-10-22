# Контракт: зрители, чат, история ходов, история партий, HTTPS

Единый источник истины для задач волны «spectate». Поля, имена и форматы — дословно.

## 1. Доступ
- Любой **залогиненный** пользователь может смотреть любую партию (активную или завершённую): состояние, WebSocket, события, чат.
- Действия (ход, деп, ничья, сдача, отмена, `dep-options`) — только игрокам. Для остальных — как сейчас, 404 `GAME_NOT_FOUND`.
- Аноним (без сессии) — 401, как везде.

## 2. Состояние партии для зрителя
`GET /api/v1/games/{id}` для не-игрока возвращает тот же `GameStateOut`, но:
- `you = "spectator"`;
- `legal_moves = []`.

WebSocket `/ws/games/{id}` пускает зрителей так же, как игроков.

## 3. Живые партии
`GET /api/v1/games/live?limit=1..100` (по умолчанию 50, только залогиненным) → массив, сортировка `created_at desc`, только `status = 'active'`:
```json
[{"id": "uuid", "time_control": "3+2", "ply": 14, "created_at": "iso",
  "white": {"login": "a", "elo": 1216}, "black": {"login": "b", "elo": 1190},
  "deps_used": 3}]
```
`deps_used = white_deps + black_deps`. **Маршрут `/games/live` объявляется в роутере раньше `/games/{game_id}`** (иначе `live` уйдёт в uuid-параметр и получит 422).

## 4. События партии (история ходов)
`GET /api/v1/games/{id}/events?after_seq=<int, по умолчанию 0>` (любой залогиненный; партии нет → 404 `GAME_NOT_FOUND`):
```json
{
  "game": {"id": "uuid", "status": "active|finished|aborted", "result": "white|black|draw|null",
           "end_reason": "str|null", "time_control": "3+2",
           "white": {"login": "a", "elo": 1200}, "black": {"login": "b", "elo": 1200},
           "white_loadout": {}, "black_loadout": {},
           "created_at": "iso", "finished_at": "iso|null",
           "initial_board": [{"square": "a1", "piece": "R", "color": "white"}]},
  "events": [
    {"seq": 1, "ply": 1, "kind": "move", "actor": "white",
     "payload": {"uci": "e2e4", "san": "e4"},
     "board": [{"square": "a1", "piece": "R", "color": "white"}],
     "check_square": null, "white_ms": 180000, "black_ms": 180000, "created_at": "iso"}
  ]
}
```
- `events` — все события партии с `seq > after_seq`, по возрастанию `seq`, всех видов (`move`, `dep`, `resign`, `draw_offer`, `draw_accept`, `draw_decline`, `abort`, `flag`, `game_over`).
- `board` и `check_square` вычисляются на сервере из `fen_after` события: `board_squares(chess.Board(fen_after))`; `check_square` — клетка короля стороны, которая ходит, если `board.is_check()`, иначе `null`.
- `initial_board` — `board_squares(chess.Board())`.
- `payload` для `dep`: `{"square", "from", "to", "chance", "success", "roll_id"}` (как в БД).
- Elo в `game.white/black` — `*_elo_before`.

## 5. Профиль игрока и его партии
- `GET /api/v1/users/{login}` (любой залогиненный; нет такого логина → 404 `USER_NOT_FOUND`) →
  `{"login", "elo", "created_at", "games": {"played", "wins", "draws", "losses"}}`.
  Считаются только партии со `status = 'finished'`.
- `GET /api/v1/users/{login}/games?before=<iso>&limit=1..100` → ровно та же форма, что `GET /api/v1/me/games` (`{items: [{id, opponent_login, color, result, end_reason, time_control, finished_at, elo_delta}], next_before}`), с точки зрения этого игрока.

## 6. Чат партии
Таблица `game_messages`: `id bigserial pk`, `game_id uuid fk games not null`, `user_id bigint fk users not null`, `body text not null check (char_length(body) between 1 and 300)`, `created_at timestamptz not null default now()`. Индекс `(game_id, id)`.

- `POST /api/v1/games/{id}/chat` тело `{"body": str}` (любой залогиненный, партия существует, в любом статусе):
  - `body` обрезается `strip()`; пусто после обрезки или длиннее 300 → 422 `VALIDATION_ERROR`;
  - rate-limit: `hit(f"rl:chat:{user.id}", 1, 1)` и `hit(f"rl:chatm:{user.id}", 20, 60)`;
  - ответ 201 `ChatMessageOut` = `{"id", "login", "role": "white|black|spectator", "body", "created_at"}`;
  - после коммита: `pubsub.publish_game(game_id, {"chat": ChatMessageOut})`.
- `GET /api/v1/games/{id}/chat?before_id=<int>&limit=1..100` (по умолчанию 50) → `{"items": [ChatMessageOut, ...], "next_cursor": int|null}`. Берутся последние `limit` сообщений с `id < before_id`, отдаются **по возрастанию id**; `next_cursor` = наименьший id страницы, если страница полная, иначе `null`.

## 7. WebSocket
Сообщение из Redis-канала `game:{id}` с ключом `"chat"` (без `"version"`) — клиенту уходит **только** `{"type": "chat", "data": <ChatMessageOut>}`, состояние не перечитывается и не отправляется. Остальные сообщения — как раньше (`dep` → `state` → `game_over`).

## 8. Фронтенд-модули

### `frontend/js/game-moves.js`
```js
export function createMoveList(container, { onSelect }) -> {
  setEvents(events),      // заменить весь список (массив событий из п. 4)
  appendEvents(events),   // дописать новые (seq больше последнего)
  lastSeq(),              // seq последнего события или 0
  select(seq | null),     // подсветить выбранное событие (null — снять подсветку)
}
// onSelect(event) — клик по ходу или депу; event — объект события из п. 4
```
Показывает ходы парами «1. e4 e5», депы — отдельной строкой «⚡ Конь → Ферзь ✓/✗», прочие события — серой строкой.

### `frontend/js/game-chat.js`
```js
export function createChat(container, { gameId, canWrite }) -> {
  load(),                 // GET /games/{gameId}/chat — последние 50
  onWsChat(message),      // добавить ChatMessageOut, пришедший по WebSocket (без дублей по id)
}
```

### Страницы
- `game.html` — режим зрителя, панель ходов (`game-moves.js`), чат (`game-chat.js`), просмотр любой позиции.
- `replay.html?id=<uuid>` — повтор завершённой (или любой) партии по событиям.
- `live.html` — список живых партий со ссылкой «Смотреть» → `/game.html?id=`.
- `user.html?login=<login>` — публичный профиль и партии со ссылками на `/replay.html?id=`.

## 9. HTTPS
- Сертификаты: `./certs/fullchain.pem` и `./certs/privkey.pem`, в контейнер монтируются в `/etc/nginx/certs` (только чтение).
- Сертификаты есть → nginx слушает 443 (HTTPS) и 80, а с 80 отдаёт 301 на `https://$host:${HTTPS_PORT}$request_uri`. Сертификатов нет → работает как сейчас, только http на 80.
- Порты compose: `${HTTP_PORT:-8080}:80` и `${HTTPS_PORT:-8443}:443`.
- Для HTTPS в `.env`: `COOKIE_SECURE=true`, а в `ALLOWED_ORIGINS` добавить `https://<хост>:<HTTPS_PORT>`.
- `scripts/gen-dev-cert.sh` — самоподписанный сертификат для `localhost` через контейнер `alpine/openssl`.
