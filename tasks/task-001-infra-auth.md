# task-001 — Инфраструктура, авторизация, экономика-ядро

Прочитай перед работой: `docs/TZ.md` (особенно разделы 5, 6, 7, 8, 9.1, 9.2) и `docs/AUDIT.md`.

## Правила для исполнителя (обязательно)
1. Делаешь **ровно** то, что описано ниже. Не добавляй библиотек, сервисов, эндпоинтов, полей, файлов, которых здесь нет.
2. Не меняешь архитектурные решения (стек, структуру папок, формат ошибок, схему cookie). Если что-то кажется неправильным или невозможным — **остановись и напиши вопрос** в конце ответа, не обходи.
3. Версии зависимостей — ровно те, что указаны. Если версия не ставится — сообщи, не подбирай сам.
4. Запрещено: `localStorage`, `sessionStorage`, `indexedDB`, `document.cookie`, `innerHTML` с данными, инлайн `<script>`/`<style>`/`onclick=` во фронте; модуль `random` в бэкенде; JWT; хранение чего-либо кроме токена в cookie.
5. Код — Python 3.12, type hints везде, async SQLAlchemy 2.0 стиль (`select()`, `Mapped[...]`).
6. В конце работы прогони команды из раздела «Проверка» и приложи их вывод.

---

## 0. Чистка репозитория
```bash
mkdir -p legacy
mv site legacy/site
mv templates legacy/templates
git rm -f main.py
rm -f FILES.md
```
Больше ничего в `legacy/` не трогать.

## 1. Корневые файлы

### `.gitignore`
```
.env
.idea/
__pycache__/
*.pyc
.pytest_cache/
certs/*.pem
```

### `.env.example`
```
POSTGRES_USER=chessdep
POSTGRES_PASSWORD=change-me
POSTGRES_DB=chessdep
DATABASE_URL=postgresql+asyncpg://chessdep:change-me@postgres:5432/chessdep
REDIS_URL=redis://redis:6379/0
COOKIE_SECURE=false
ALLOWED_ORIGINS=http://localhost:8080
SESSION_TTL_DAYS=30
HTTP_PORT=8080
```

### `docker-compose.yml`
```yaml
name: chessdep

x-backend: &backend
  build: ./backend
  env_file: .env
  restart: unless-stopped

services:
  postgres:
    image: postgres:16-alpine
    env_file: .env
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 3s
      timeout: 3s
      retries: 20
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    volumes: [redisdata:/data]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 3s
      timeout: 3s
      retries: 20
    restart: unless-stopped

  migrate:
    <<: *backend
    command: ["alembic", "upgrade", "head"]
    restart: "no"
    depends_on:
      postgres: {condition: service_healthy}

  api:
    <<: *backend
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000",
              "--proxy-headers", "--forwarded-allow-ips", "*"]
    depends_on:
      migrate: {condition: service_completed_successfully}
      redis: {condition: service_healthy}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status==200 else 1)"]
      interval: 5s
      timeout: 3s
      retries: 20

  worker:
    <<: *backend
    command: ["python", "-m", "app.worker"]
    depends_on:
      migrate: {condition: service_completed_successfully}
      redis: {condition: service_healthy}

  nginx:
    build: ./nginx
    ports: ["${HTTP_PORT:-8080}:80"]
    volumes: ["./frontend:/usr/share/nginx/html:ro"]
    depends_on:
      api: {condition: service_healthy}
    restart: unless-stopped

  postgres-test:
    profiles: [test]
    image: postgres:16-alpine
    environment: {POSTGRES_USER: test, POSTGRES_PASSWORD: test, POSTGRES_DB: test}
    tmpfs: [/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test -d test"]
      interval: 2s
      retries: 30

  redis-test:
    profiles: [test]
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      retries: 30

  api-test:
    profiles: [test]
    build: ./backend
    environment:
      DATABASE_URL: postgresql+asyncpg://test:test@postgres-test:5432/test
      REDIS_URL: redis://redis-test:6379/0
      COOKIE_SECURE: "false"
      ALLOWED_ORIGINS: http://test
      SESSION_TTL_DAYS: "30"
      TESTING: "1"
      FRONTEND_DIR: /frontend
    volumes:
      - ./backend:/app
      - ./frontend:/frontend:ro
    command: ["sh", "-c", "alembic upgrade head && pytest -q -p no:cacheprovider"]
    depends_on:
      postgres-test: {condition: service_healthy}
      redis-test: {condition: service_healthy}

volumes:
  pgdata:
  redisdata:
```

### `Makefile`
```make
up:        ; docker compose up -d --build
down:      ; docker compose down
logs:      ; docker compose logs -f --tail=100
test:      ; docker compose --profile test run --rm --build api-test; docker compose --profile test rm -sf postgres-test redis-test
make-admin:; docker compose exec api python -m app.cli make-admin $(LOGIN)
.PHONY: up down logs test make-admin
```

### `README.md`
Коротко: требования (Linux, Docker, Compose v2), `cp .env.example .env`, `make up`, открыть `http://localhost:8080`, `make test`, `make make-admin LOGIN=nik`. Для доступа с другой машины — добавить её origin (например `http://192.168.1.10:8080`) в `ALLOWED_ORIGINS` через запятую.

## 2. Backend

### `backend/Dockerfile`
```dockerfile
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt
COPY . .
RUN useradd -r -u 10001 app && chown -R app /app
USER app
```

### `backend/requirements.txt`
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.0
pydantic==2.10.4
pydantic-settings==2.7.0
email-validator==2.2.0
argon2-cffi==23.1.0
redis==5.2.1
chess==1.11.1
```

### `backend/requirements-dev.txt`
```
pytest==8.3.4
pytest-asyncio==0.25.0
httpx==0.28.1
```

### `backend/pyproject.toml`
Только конфиг pytest:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
```

### `backend/app/config.py`
`class Settings(BaseSettings)` с полями: `database_url: str`, `redis_url: str`, `cookie_secure: bool = True`, `allowed_origins: list[str]` (из строки через запятую, используй `field_validator(mode="before")`), `session_ttl_days: int = 30`, `testing: bool = False`, `frontend_dir: str = "/frontend"`. Свойство `cookie_name` → `"__Host-sid"` если `cookie_secure`, иначе `"sid"`. Синглтон `settings = Settings()`.

### `backend/app/db.py`
- `engine = create_async_engine(settings.database_url, poolclass=NullPool if settings.testing else None, pool_pre_ping=True)` (если `None` — не передавай аргумент).
- `SessionLocal = async_sessionmaker(engine, expire_on_commit=False)`.
- FastAPI-зависимость `async def get_db() -> AsyncIterator[AsyncSession]`: открывает сессию, `async with session.begin():` вокруг `yield` (одна транзакция на запрос, коммит при успехе, rollback при исключении).

### `backend/app/redis.py`
`redis_client = redis.asyncio.from_url(settings.redis_url, decode_responses=True)`.

### Модели `backend/app/models/`
`base.py`: `class Base(DeclarativeBase)`, общий `MetaData` с naming convention (`ix_%(column_0_label)s`, `uq_%(table_name)s_%(column_0_name)s`, `ck_%(table_name)s_%(constraint_name)s`, `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`, `pk_%(table_name)s`).

Таблицы (точно по TZ §8, только эти пять в этой задаче):
- `user.py` → `users`: id, login (CITEXT), email (CITEXT), password_hash, role (check `'user','admin'`), is_banned, balance (check `>= 0`, default 0), elo (default 1200), last_daily_bonus_at, created_at (`server_default=func.now()`).
- `session.py` → `sessions`: id, user_id (FK `ondelete=CASCADE`), token_hash (`LargeBinary`, unique), created_at, expires_at, last_seen_at, revoked_at, ip (`INET`), user_agent (Text, обрезать до 512).
- `setting.py` → `settings`: key (pk), value (JSONB), updated_at, updated_by (FK users, nullable).
- `ledger.py` → `ledger`: id, user_id (FK), delta, balance_after, reason (check по списку TZ §8), ref (nullable), actor_id (FK nullable), created_at. Индекс `(user_id, created_at desc)`.
- `admin_audit.py` → `admin_audit`: id, admin_id (FK **nullable** — null для CLI), action, target, payload (JSONB), created_at.

CITEXT: `from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB`.

### Миграция `backend/alembic/versions/0001_initial.py`
- Пишется **руками** (не autogenerate): `op.execute("CREATE EXTENSION IF NOT EXISTS citext")`, затем `op.create_table` для пяти таблиц один-в-один с моделями.
- Сид `settings` — все ключи и значения из TZ §5 через `op.bulk_insert`.
- `downgrade` удаляет таблицы в обратном порядке.
- `alembic/env.py` — async-вариант (шаблон `alembic init -t async`), `target_metadata = Base.metadata`, URL берётся из `app.config.settings.database_url`. Все модели импортируются в `app/models/__init__.py`.

### `backend/app/core/errors.py`
```python
class AppError(Exception):
    def __init__(self, status: int, code: str, message: str): ...
```
Хендлеры, которые регистрируются в `main.py`:
- `AppError` → `JSONResponse(status, {"error": {"code", "message"}})`;
- `RequestValidationError` → 422 `VALIDATION_ERROR`, message `"Некорректные данные"`;
- `StarletteHTTPException` 404/405 → `NOT_FOUND` / `METHOD_NOT_ALLOWED`;
- любое иное исключение → 500 `INTERNAL`, message `"Внутренняя ошибка"`, стек только в лог.

Коды этой задачи: `UNAUTHENTICATED` 401, `INVALID_CREDENTIALS` 401, `USER_BANNED` 403, `BAD_ORIGIN` 403, `FORBIDDEN` 403, `LOGIN_TAKEN` 409, `EMAIL_TAKEN` 409, `RATE_LIMITED` 429, `BONUS_COOLDOWN` 400, `INSUFFICIENT_FUNDS` 400, `WRONG_PASSWORD` 400.

### `backend/app/core/security.py`
```python
_ph = argon2.PasswordHasher()
DUMMY_HASH = _ph.hash("dummy-password-for-timing")

def hash_password(p: str) -> str
def verify_password(hash_: str, p: str) -> bool   # ловит VerifyMismatchError/InvalidHashError → False
def new_session_token() -> str                    # secrets.token_urlsafe(32)
def hash_token(token: str) -> bytes               # hashlib.sha256(token.encode()).digest()
```

### `backend/app/core/sessions.py`
- `async def create_session(db, user_id, ip, user_agent) -> str` — создаёт строку, `expires_at = now + session_ttl_days`, возвращает **сырой** токен (в БД — только хеш).
- `async def resolve_session(db, token) -> tuple[Session, User] | None` — ищет по `hash_token`, проверяет `revoked_at is None` и `expires_at > now()`; обновляет `last_seen_at`, если прошло > 60 с.
- `async def revoke_session(db, session_id)`, `async def revoke_all(db, user_id, except_session_id: int | None = None)`.
- `def set_session_cookie(response, token)`: `response.set_cookie(settings.cookie_name, token, max_age=ttl_seconds, httponly=True, secure=settings.cookie_secure, samesite="strict", path="/")`.
- `def clear_session_cookie(response)`.

### `backend/app/core/deps.py`
- `async def current_user(request, db) -> User`: берёт cookie `settings.cookie_name`; нет → 401 `UNAUTHENTICATED`; `resolve_session` → None → 401; `user.is_banned` → 403 `USER_BANNED`. Кладёт `request.state.session_id`.
- `async def require_admin(user = Depends(current_user)) -> User`: `role != 'admin'` → 403 `FORBIDDEN`.
- `def client_ip(request) -> str`: `request.client.host` (uvicorn уже применил proxy headers).

### `backend/app/core/origin.py`
Чистый ASGI-middleware (не `BaseHTTPMiddleware`): для HTTP-запросов с методом не из `{GET, HEAD, OPTIONS}` заголовок `origin` обязан быть в `settings.allowed_origins`, иначе ответ 403 `{"error":{"code":"BAD_ORIGIN","message":"Запрос с недопустимого источника"}}`. Отсутствие заголовка = недопустимо. Для `websocket`-scope та же проверка для всех (в этой задаче WS-эндпоинтов нет, но проверка должна быть).

### `backend/app/core/ratelimit.py`
```python
async def hit(key: str, limit: int, window_s: int) -> None:
    # pipeline: INCR key; EXPIRE key window_s NX
    # если значение > limit → raise AppError(429, "RATE_LIMITED", "Слишком много запросов, подождите")
async def count(key: str) -> int
async def incr(key: str, window_s: int) -> int
```
Ключи в этой задаче: `rl:register:{ip}` 5/3600; `rl:login:{ip}` 10/60; `rl:loginfail:{login.lower()}` — 5 неудач / 900 с.

### `backend/app/services/settings.py`
- `DEFAULTS: dict[str, Any]` — все ключи TZ §5.
- `async def get_setting(db, key: str) -> Any`: кэш в памяти процесса (dict `key → (value, monotonic_ts)`), TTL 5 с; при промахе читает таблицу; если строки нет — `DEFAULTS[key]`. Неизвестный ключ → `KeyError`.
- `def clear_cache()` — для тестов.

### `backend/app/services/economy.py`
```python
async def apply_delta(db: AsyncSession, user_id: int, delta: int, reason: str,
                      ref: str | None = None, actor_id: int | None = None) -> int:
    # SELECT users ... WHERE id=:id FOR UPDATE
    # new = balance + delta; new < 0 → AppError(400, "INSUFFICIENT_FUNDS", "Недостаточно ◈")
    # UPDATE balance; INSERT ledger(delta, balance_after=new, reason, ref, actor_id)
    # НЕ коммитит. Возвращает new.
```
Единственное место в коде, где меняется `users.balance`.

### `backend/app/schemas/auth.py`
Все модели `model_config = ConfigDict(extra="forbid")`.
- `RegisterIn`: `login` (`constr(pattern=r"^[A-Za-z0-9_-]{3,16}$")`), `email: EmailStr`, `password: constr(min_length=8, max_length=128)`.
- `LoginIn`: `login: constr(min_length=1, max_length=64)`, `password: constr(min_length=1, max_length=128)`.
- `PasswordIn`: `old_password`, `new_password` (8–128).
- `MeOut`: `id, login, role, balance, elo, daily_bonus_available_at: datetime | None` (None = доступен сейчас).
- `LedgerItemOut`: `id, delta, balance_after, reason, ref, created_at`; `Page[T]`: `items, next_cursor`.
- `DailyBonusOut`: `balance, next_available_at`.

### Роутеры `backend/app/api/`
`health.py` — `GET /api/v1/health`: `SELECT 1` + `redis PING` → `{"status":"ok"}`, иначе 503.

`auth.py`:
- `POST /api/v1/auth/register` → 201 `MeOut`. Порядок: `hit(rl:register)`; проверка занятости login/email (409); создать User (`balance=0`, `password_hash`); `flush`; `apply_delta(+starting_balance, "signup_bonus")`; `create_session`; поставить cookie. `IntegrityError` при гонке → 409 с правильным кодом.
- `POST /api/v1/auth/login` → 200 `MeOut`. Порядок: `hit(rl:login)`; если `count(rl:loginfail:<login>) >= 5` → 429; найти пользователя; если нет — `verify_password(DUMMY_HASH, password)` (выравнивание времени) и 401 `INVALID_CREDENTIALS`; неверный пароль → `incr(loginfail)` и 401 с тем же кодом и текстом `"Неверный логин или пароль"`; забанен → 403 `USER_BANNED`; иначе `create_session`, cookie.
- `POST /api/v1/auth/logout` (требует сессию) → 204, `revoke_session`, `clear_session_cookie`.

`me.py` (всё требует `current_user`):
- `GET /api/v1/me` → `MeOut`.
- `POST /api/v1/me/password` → 204; неверный старый → 400 `WRONG_PASSWORD`; `revoke_all(except текущей)`.
- `POST /api/v1/me/daily-bonus` → `DailyBonusOut`: `SELECT … FOR UPDATE` пользователя; если `last_daily_bonus_at + cooldown > now` → 400 `BONUS_COOLDOWN`; иначе `apply_delta(+daily_bonus, "daily_bonus")`, обновить `last_daily_bonus_at`.
- `GET /api/v1/me/ledger?cursor=&limit=` (limit 1..100, default 50, по `id desc`, `cursor` = id, выдаются записи с `id < cursor`).

`internal.py` — `GET /api/v1/internal/require-admin`: нет сессии → 401, не админ → 403, иначе 204. Без тела.

### `backend/app/main.py`
Создаёт `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`, добавляет `OriginMiddleware`, хендлеры ошибок, роутеры. На `shutdown` закрывает redis и `engine.dispose()`.

### `backend/app/cli.py`
`python -m app.cli make-admin <login>` / `revoke-admin <login>` (argparse, `asyncio.run`). Не найден → код выхода 1 и сообщение. Пишет `admin_audit(admin_id=None, action="cli_make_admin"|"cli_revoke_admin", target=login)`.

### `backend/app/worker.py`
Заглушка для task-003: асинхронный цикл, раз в 30 с логирует `worker alive`, корректно завершается по SIGTERM/SIGINT (`loop.add_signal_handler`).

## 3. nginx

### `nginx/Dockerfile`
```dockerfile
FROM nginx:1.27-alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/chessdep.conf
```

### `nginx/nginx.conf`
```nginx
server {
    listen 80;
    server_tokens off;
    client_max_body_size 64k;
    root /usr/share/nginx/html;

    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "same-origin" always;

    location /api/v1/internal/ { return 404; }

    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws/ {
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_read_timeout 3600s;
    }

    location = /admin.html {
        auth_request /_auth/admin;
        error_page 401 403 = @to_login;
        try_files $uri =404;
    }
    location = /_auth/admin {
        internal;
        proxy_pass http://api:8000/api/v1/internal/require-admin;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header Cookie $http_cookie;
    }
    location @to_login { return 302 /login.html?next=/admin.html; }

    location / { try_files $uri $uri/ =404; }
}
```
Ни в одном `location` не добавлять собственные `add_header` (иначе потеряются заголовки безопасности).

## 4. Frontend (минимальный, только для проверки auth; полноценный — task-006)

Файлы: `frontend/index.html`, `login.html`, `register.html`, `admin.html`, `css/base.css`, `js/api.js`, `js/login.js`, `js/register.js`, `js/index.js`.

- `css/base.css` — перенести из `legacy/site/css/style.css` только `:root`-токены, `body`, кнопки (`.btn`, `.btn-gold`, `.btn-ghost`), поля формы, карточку `.card`. Шрифт `system-ui`. Никаких `@import` и внешних шрифтов.
- Каждая страница: `<meta charset>`, `<meta viewport>`, `<link rel="stylesheet" href="css/base.css">`, `<script type="module" src="js/<page>.js"></script>`. Без инлайн-скриптов, стилей и `on*`-атрибутов.
- `admin.html` — заглушка «Админка — будет в фазе 5».

### `frontend/js/api.js` (написать ровно так)
```js
export class ApiError extends Error {
  constructor(status, code, message) { super(message); this.status = status; this.code = code; }
}

export async function api(method, path, body) {
  const opts = { method, credentials: 'same-origin', headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch('/api/v1' + path, opts);
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* пустое тело */ }
  if (!res.ok) {
    const err = (data && data.error) || { code: 'NETWORK', message: 'Ошибка сети' };
    if (res.status === 401 && err.code === 'UNAUTHENTICATED') redirectToLogin();
    throw new ApiError(res.status, err.code, err.message);
  }
  return data;
}

export function redirectToLogin() {
  const next = location.pathname + location.search;
  location.href = '/login.html?next=' + encodeURIComponent(next);
}

export function safeNext(defaultPath = '/index.html') {
  const n = new URLSearchParams(location.search).get('next');
  return n && n.startsWith('/') && !n.startsWith('//') && !n.includes('\\') ? n : defaultPath;
}

export function text(el, value) { el.textContent = value == null ? '' : String(value); }
```

- `login.js` / `register.js`: форма → `api('POST','/auth/login'|'/auth/register', {...})` → `location.href = safeNext()`; ошибка → `text(errorEl, e.message)`. Клиентская валидация допустима только как подсказка (сервер всё равно проверяет).
- `index.js`: `api('GET','/me')` → показать логин, баланс, роль; кнопка «Ежедневный бонус» → `POST /me/daily-bonus`, обновить баланс из ответа; кнопка «Выйти» → `POST /auth/logout` → `/login.html`. Если `role === 'admin'` — показать ссылку на `/admin.html`.

## 5. Тесты `backend/tests/`

### `conftest.py`
- Перед каждым тестом (autouse-фикстура): `TRUNCATE users, sessions, ledger, admin_audit RESTART IDENTITY CASCADE`, удалить и заново вставить `settings` из `DEFAULTS`, `settings_service.clear_cache()`, `redis_client.flushdb()`.
- Фикстура `client`: `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"Origin": "http://test"})`.
- Хелпер `async def register(client, login="alice", email=None, password="password123") -> Response`.
- Фикстура `db` — отдельная `SessionLocal()` для прямых проверок в БД.

### Обязательные тесты (имена ровно такие)
`test_auth.py`
- `test_register_sets_httponly_cookie_and_signup_bonus` — 201, `Set-Cookie` содержит `sid=`, `HttpOnly`, `SameSite=strict`, `Path=/`; в cookie нет `.`-разделённых сегментов JWT; баланс = `starting_balance`; одна запись ledger `signup_bonus`.
- `test_session_token_stored_hashed` — в `sessions.token_hash` лежит `sha256(token)`, сырого токена в БД нет.
- `test_register_duplicate_login_and_email` — 409 `LOGIN_TAKEN`, 409 `EMAIL_TAKEN` (логин регистронезависимо: `Alice` vs `alice`).
- `test_register_validation` — плохой логин, короткий пароль, лишнее поле `role: "admin"` → 422 (и роль не меняется).
- `test_login_ok_and_wrong_password` — одинаковые код и сообщение для несуществующего логина и неверного пароля.
- `test_login_fail_lockout` — 5 неверных паролей → 6-я попытка (даже с верным паролем) → 429.
- `test_logout_revokes_session` — после logout старый токен (вручную подставленный в cookie) → 401.
- `test_password_change_revokes_other_sessions`.
- `test_banned_user_rejected` — выставить `is_banned` в БД → `/me` 403 `USER_BANNED`; login → 403.
- `test_expired_session_rejected` — сдвинуть `expires_at` в прошлое → 401.

`test_security.py`
- `test_post_without_origin_forbidden` — клиент без заголовка Origin → 403 `BAD_ORIGIN`.
- `test_post_with_foreign_origin_forbidden` — `Origin: http://evil.example` → 403.
- `test_get_without_origin_allowed` — `GET /api/v1/health` без Origin → 200.
- `test_me_requires_auth` — 401 `UNAUTHENTICATED`.
- `test_require_admin_endpoint` — без сессии 401, user 403, admin (роль выставлена в БД) 204.
- `test_cookie_name_secure_mode` — при `cookie_secure=True` (monkeypatch settings) имя cookie `__Host-sid` и есть флаг `Secure`.
- `test_error_format` — 404 на несуществующий путь возвращает `{"error":{"code":"NOT_FOUND",...}}`.

`test_economy.py`
- `test_apply_delta_never_negative` — списание больше баланса → `INSUFFICIENT_FUNDS`, баланс и ledger не изменились.
- `test_apply_delta_concurrent` — баланс 1000, 10 параллельных задач (`asyncio.gather`, у каждой своя `SessionLocal()` и транзакция) списывают по 200 → ровно 5 успехов, баланс 0, `sum(ledger.delta) == balance`.
- `test_daily_bonus_cooldown` — первый раз +200, второй → 400 `BONUS_COOLDOWN`; после сдвига `last_daily_bonus_at` на 25 ч назад — снова успех.
- `test_ledger_pagination` — курсор и limit работают.

`test_cli.py`
- `test_make_admin` — вызвать функцию CLI напрямую (не subprocess): роль стала admin, запись в `admin_audit`.

`test_frontend_static.py`
Обходит все `*.js` и `*.html` в `settings.frontend_dir` и падает, если найдено:
- `localStorage`, `sessionStorage`, `indexedDB`, `document.cookie`;
- регэксп `innerHTML\s*=` (в этой фазе innerHTML не используется вообще);
- `Math.random`;
- в HTML: `<script>` без атрибута `src`, тег `<style>`, атрибуты `on\w+=`, атрибут `style=`;
- ссылки на внешние ресурсы: `https?://` внутри `src=` или `href=`.

## 6. Проверка (приложить вывод)
```bash
cp .env.example .env
make up
docker compose ps                                 # все сервисы healthy/running, migrate exited 0
curl -s localhost:8080/api/v1/health              # {"status":"ok"}
curl -si -X POST localhost:8080/api/v1/auth/register -H 'Content-Type: application/json' \
  -d '{"login":"nik","email":"nik@example.com","password":"password123"}'   # 403 BAD_ORIGIN
curl -si -X POST localhost:8080/api/v1/auth/register -H 'Origin: http://localhost:8080' \
  -H 'Content-Type: application/json' -d '{"login":"nik","email":"nik@example.com","password":"password123"}'  # 201 + Set-Cookie sid
curl -si localhost:8080/admin.html                # 302 → /login.html?next=/admin.html
curl -si localhost:8080/api/v1/internal/require-admin   # 404 (снаружи закрыто)
make make-admin LOGIN=nik
make test                                         # все тесты зелёные
```
В конце ответа: список созданных/изменённых файлов и вопросы, если были неясности.
