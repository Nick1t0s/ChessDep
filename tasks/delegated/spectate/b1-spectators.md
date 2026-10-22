# Цель
Зрители: любой залогиненный видит любую партию (GET и WebSocket), список живых партий; WebSocket передаёт сообщения чата.

# Контекст
Прочитай сначала:
- `docs/contracts-spectate.md` — ЕДИНСТВЕННЫЙ контракт этой задачи; поля, пути, коды — дословно оттуда.
- Образцы стиля: `backend/app/api/games.py`, `backend/app/services/game_view.py`, `backend/app/api/me.py`, `backend/tests/test_games.py`, `backend/tests/conftest.py` (фикстуры `alice`, `bob`, `carol`, `rng`, `frozen`, `client`, хелперы `start_game`, `register`, `set_fen`).
- `backend/app/core/errors.py` — ошибки только через `AppError(status, code, message)`; сообщение по-русски.
- `backend/app/core/deps.py` — `current_user`.

Правила:
- время только `clock.now()` (`from app.core import clock`); любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`; публикация в Redis — только через `after_commit` из `app.db`;
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`);
- существующие тесты не удалять и не ослаблять (кроме явно названного ниже).

# Область
Менять: `backend/app/services/game_view.py`, `backend/app/api/games.py`, `backend/app/api/ws.py`, `backend/tests/test_games.py` (только тест `test_stranger_cannot_see_game`, см. п. 5). Создать: `backend/tests/test_spectators.py`.

# Контракт и что сделать
1. `game_view.build_state`: `you` = `"white"` если зритель — белые, `"black"` если чёрные, иначе `"spectator"`. `legal_moves` как раньше — только если партия активна и `you == turn` (у зрителя всегда `[]`).
2. `api/games.py`:
   - `GET /games/{game_id}` — пускать любого залогиненного: партии нет → 404 `GAME_NOT_FOUND`, проверку `color_of` для этого эндпоинта убрать;
   - `GET /games/{game_id}/dep-options` — по-прежнему только игроки (404 остальным);
   - все POST-действия не трогать;
   - добавить `GET /games/live` (контракт п. 3): `limit: Annotated[int, Query(ge=1, le=100)] = 50`, требует `current_user`, ответ — список dict по контракту, `created_at`/логины/Elo из `games` и `users` (Elo — `*_elo_before`). **Объявить этот маршрут в файле выше `@router.get("/games/{game_id}")`.**
3. `api/ws.py`:
   - в `_load_ws_context` и `_pubsub_loop` убрать требование быть игроком (оставить: сессия валидна, пользователь не забанен, партия существует);
   - в `_pubsub_loop`, сразу после `json.loads`, если в событии есть ключ `"chat"` → `await websocket.send_json({"type": "chat", "data": event["chat"]})` и `continue` (состояние не загружать).
4. Добавить в `ws.py` чистую функцию `def is_chat_event(event: dict) -> bool: return "chat" in event` и использовать её в п. 3.
5. В `tests/test_games.py::test_stranger_cannot_see_game` заменить первую проверку: теперь `GET /games/{id}` для carol → 200 и `you == "spectator"`; проверку, что `move` → 404, оставить.
6. `tests/test_spectators.py` (фикстуры `alice`, `bob`, `carol`, `rng`, хелпер `start_game`):
   - `test_spectator_sees_state` — carol: 200, `you == "spectator"`, `legal_moves == []`, 32 фигуры;
   - `test_spectator_cannot_act` — carol: `move`, `dep`, `resign`, `draw/offer`, `abort` → 404 `GAME_NOT_FOUND`; `GET dep-options` → 404;
   - `test_live_games_list` — после `start_game` и хода e2e4: `GET /games/live` у carol → один элемент с верными `white.login`, `black.login`, `time_control == "3+2"`, `ply == 1`, `deps_used == 0`; после сдачи — список пуст;
   - `test_live_route_not_uuid` — `GET /games/live` → 200 (а не 422);
   - `test_live_requires_auth` — без cookie → 401;
   - `test_is_chat_event` — `is_chat_event({"chat": {}})` → True, `is_chat_event({"version": 1})` → False.

# Готово, когда
`bash scripts/test_isolated.sh` завершается с кодом 0 и печатает `N passed` без `failed` (это полный прогон всех тестов бэкенда в Docker, ~2–3 минуты; можно запускать параллельно с другими).

# Нельзя
- Менять файлы вне «Область».
- Менять контракт (`docs/contracts-spectate.md`), добавлять эндпоинты, поля или зависимости, которых нет в контракте и задаче.
- Во фронтенде: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `style=` и `on*=` в HTML, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, а описать проблему в SUMMARY.
