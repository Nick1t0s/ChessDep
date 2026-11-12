# Цель
Чат партии: таблица, миграция, отправка и история сообщений, доставка по WebSocket через Redis.

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
Создать: `backend/alembic/versions/0005_chat.py`, `backend/app/models/chat.py`, `backend/app/schemas/chat.py`, `backend/app/services/chat.py`, `backend/tests/test_chat.py`. Заполнить: `backend/app/api/chat.py` (роутер уже есть и подключён в `main.py` — `main.py` не трогать). Менять: `backend/app/models/__init__.py` (добавить `GameMessage`), `backend/tests/conftest.py` (ТОЛЬКО добавить `game_messages` в список `_TRUNCATE_SQL`).

# Контракт и что сделать
Реализовать контракт п. 6 дословно.

- Миграция `0005_chat.py`: `revision = "0005"`, `down_revision = "0004"`, руками (`op.create_table`, check-ограничение длины `ck_game_messages_body_length`, индекс `ix_game_messages_game_id_id` на `(game_id, id)`); `downgrade` удаляет индекс и таблицу. Образец — `backend/alembic/versions/0004_market.py`.
- Модель `GameMessage` в `models/chat.py` (образец — `models/market.py`).
- `schemas/chat.py`: `ChatIn {body: str}` с валидатором: `strip()`, пусто или длиннее 300 → ошибка валидации (422); `ChatMessageOut {id, login, role, body, created_at}`; `ChatPageOut {items, next_cursor}`.
- `services/chat.py`:
  ```python
  def role_of(game: Game, user_id: int) -> str          # "white" | "black" | "spectator"
  async def post_message(db, user: User, game_id: uuid.UUID, body: str) -> ChatMessageOut
  async def list_messages(db, game_id: uuid.UUID, before_id: int | None, limit: int) -> ChatPageOut
  ```
  `post_message`: партии нет → 404 `GAME_NOT_FOUND`; вставка, `flush`; `after_commit(db, ...)` → `pubsub.publish_game(game_id, {"chat": msg.model_dump(mode="json")})`.
- `api/chat.py`: `POST /games/{game_id}/chat` (201; сначала `hit(f"rl:chat:{user.id}", 1, 1)` и `hit(f"rl:chatm:{user.id}", 20, 60)` из `app.core.ratelimit`), `GET /games/{game_id}/chat?before_id=&limit=50`. Оба — `current_user`.

`tests/test_chat.py`:
- `test_post_roles` — alice (белые) пишет → `role == "white"`; carol (не игрок) → `"spectator"`; тело обрезается (`"  gg  "` → `"gg"`);
- `test_post_validation` — `"   "` → 422; 301 символ → 422; 300 символов → 201;
- `test_rate_limit` — два сообщения подряд от одного пользователя → второй ответ 429 `RATE_LIMITED`;
- `test_list_pagination` — 5 сообщений (между ними очищать ключи rate-limit: `await redis_client.delete(f"rl:chat:{uid}")` или фикстурой `frozen` не обойтись — используй прямой `delete` ключа), `limit=2` → два последних по возрастанию id и `next_cursor`; следующая страница `before_id=next_cursor` → два предыдущих;
- `test_publish_after_commit` — подписаться на `game:{id}` (`redis_client.pubsub()`), отправить сообщение → получить JSON с ключом `"chat"` и тем же `body`;
- `test_chat_auth_and_404` — без cookie 401; несуществующая партия → 404.

# Готово, когда
`bash scripts/test_isolated.sh` завершается с кодом 0 и печатает `N passed` без `failed` (это полный прогон всех тестов бэкенда в Docker, ~2–3 минуты; можно запускать параллельно с другими).

# Нельзя
- Менять файлы вне «Область».
- Менять контракт (`docs/contracts-spectate.md`), добавлять эндпоинты, поля или зависимости, которых нет в контракте и задаче.
- Во фронтенде: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `style=` и `on*=` в HTML, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, а описать проблему в SUMMARY.
