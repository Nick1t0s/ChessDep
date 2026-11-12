# Цель
История ходов (события партии с позициями), публичный профиль игрока и его партии.

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
Заполнить: `backend/app/api/game_history.py` (там уже есть `router = APIRouter(prefix="/api/v1", tags=["game_history"])`, он подключён в `main.py` — `main.py` не трогать). Создать: `backend/app/services/history.py`, `backend/app/schemas/history.py`, `backend/tests/test_history.py`.

# Контракт и что сделать
Реализовать контракт п. 4 и п. 5 дословно.

`services/history.py`:
```python
async def game_events(db, game: Game, after_seq: int) -> dict        # ответ п. 4
async def user_profile(db, login: str) -> dict                       # ответ п. 5; нет логина → AppError(404, "USER_NOT_FOUND", "Игрок не найден")
async def user_games(db, user: User, before: datetime | None, limit: int) -> dict   # форма как /me/games
```
- позиции: `from app.chess_engine import board_squares` и `chess.Board(event.fen_after)`; `check_square` — `chess.square_name(board.king(board.turn))`, если `board.is_check()`, иначе `None`;
- `user_games` — та же логика, что в `api/me.py::read_games_history` (скопировать запрос и формирование элементов в сервис; `me.py` НЕ менять);
- статистика `user_profile`: `played` = число партий игрока со `status='finished'`; `wins` = где `result` равен цвету игрока; `draws` = `result='draw'`; `losses` = остальные finished.

`api/game_history.py` (все эндпоинты — `Depends(current_user)`):
- `GET /games/{game_id}/events?after_seq=0` (`game_id: uuid.UUID`, `after_seq: int = Query(0, ge=0)`); партии нет → 404 `GAME_NOT_FOUND`;
- `GET /users/{login}`;
- `GET /users/{login}/games?before=&limit=50` (`limit` 1..100).

Схемы ответов в `schemas/history.py` (Pydantic, `model_config = ConfigDict(extra="forbid")`), поля — ровно по контракту.

`tests/test_history.py`:
- `test_events_fools_mate` — после f3, e5, g4, Qh4: `events` содержит 4 события `move` и 1 `game_over` по возрастанию `seq`; у последнего `move` `payload.san == "Qh4#"`, в `board` на h4 чёрный ферзь, `check_square == "e1"`; `game.result == "black"`; `len(game.initial_board) == 32`;
- `test_events_after_seq` — `after_seq=2` возвращает только события с `seq > 2`;
- `test_events_dep_payload` — `rng.values=[0.0]`, деп b1→Q, затем `events`: событие `dep` с `payload.success is True`, в `board` на b1 белый ферзь;
- `test_events_spectator_and_auth` — carol (не игрок) получает 200; без cookie — 401; несуществующий uuid — 404;
- `test_user_profile_stats` — после «детского мата» `GET /users/alice` → `games == {"played": 1, "wins": 0, "draws": 0, "losses": 1}`; bob — `wins == 1`; `GET /users/nobody` → 404 `USER_NOT_FOUND`;
- `test_user_games_shape` — `GET /users/bob/games` у carol: один элемент, `opponent_login == "alice"`, `color` и `result` с точки зрения bob, `elo_delta == 16`.

# Готово, когда
`bash scripts/test_isolated.sh` завершается с кодом 0 и печатает `N passed` без `failed` (это полный прогон всех тестов бэкенда в Docker, ~2–3 минуты; можно запускать параллельно с другими).

# Нельзя
- Менять файлы вне «Область».
- Менять контракт (`docs/contracts-spectate.md`), добавлять эндпоинты, поля или зависимости, которых нет в контракте и задаче.
- Во фронтенде: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `style=` и `on*=` в HTML, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, а описать проблему в SUMMARY.
