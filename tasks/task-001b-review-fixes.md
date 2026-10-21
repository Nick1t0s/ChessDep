# task-001b — исправления по ревью task-001

Правила те же, что в task-001: делаешь ровно это, ничего сверх, при сомнении — вопрос.
Существующие тесты не удалять и не ослаблять.

---

## 1. КРИТИЧНО: устаревшие данные после `SELECT … FOR UPDATE` (двойной бонус, рассинхрон баланса)

**Воспроизведение:** 10 параллельных `POST /me/daily-bonus` от одного пользователя → все 10 отвечают 200, в `ledger` 10 записей `daily_bonus` (+2000), а `users.balance` = 1200. Баланс и журнал разошлись, бонус выдан 10 раз.

**Причина:** `current_user` загружает `User` в ту же ORM-сессию **до** блокировки. Затем `select(User)…with_for_update()` действительно ждёт блокировку, но SQLAlchemy возвращает объект из identity map и **не перезаписывает** уже загруженные атрибуты. Поэтому `balance` и `last_daily_bonus_at` остаются старыми, как до блокировки. `test_apply_delta_concurrent` этого не ловит: там у каждой задачи свежая сессия без предзагруженного пользователя.

**Исправление:**
1. В `app/services/economy.py` добавить:
   ```python
   async def lock_user(db: AsyncSession, user_id: int) -> User:
       user = await db.scalar(
           select(User)
           .where(User.id == user_id)
           .with_for_update()
           .execution_options(populate_existing=True)
       )
       if user is None:
           raise KeyError(user_id)
       return user
   ```
2. `apply_delta` получает пользователя только через `lock_user`.
3. `daily_bonus` в `app/api/me.py` получает `locked` только через `lock_user`, а не своим `select`.
4. Правило на будущее (добавь его комментарием над `lock_user`): «любой `FOR UPDATE` по сущности, которая могла быть загружена раньше в этой сессии, — только с `populate_existing=True`».

**Тесты (добавить в `tests/test_economy.py`):**
- `test_daily_bonus_concurrent`: регистрация, затем `asyncio.gather` из 10 `POST /api/v1/me/daily-bonus` одним клиентом. Ожидание: ровно один 200, девять 400 `BONUS_COOLDOWN`, ровно одна строка ledger `daily_bonus`, баланс `starting_balance + daily_bonus`, `sum(ledger.delta) == balance`.
- `test_apply_delta_with_preloaded_user`: две параллельные задачи, у каждой своя `SessionLocal()`. В транзакции каждая сначала делает `await session.get(User, user_id)`, потом `await asyncio.sleep(0.05)`, потом `apply_delta(session, user_id, -600, "admin_adjust")` при балансе 1000. Ожидание: ровно один успех, один `INSUFFICIENT_FUNDS`, баланс 400, `sum(ledger.delta) == balance`.

## 2. Тест статики фронта не проверяет JS

`tests/test_frontend_static.py` использует `root.glob("*.js")`, а это только корень `frontend/`. Файлы в `frontend/js/` не проверяются вообще.

**Исправление:** обходить `root.rglob("*")`, брать файлы с суффиксами `.js` и `.html`. Добавить проверку, что среди просмотренных есть `js/api.js` (`assert any(p.as_posix().endswith("js/api.js") for p in scanned)`), чтобы тест не мог молча проверить пустой набор. В сообщениях об ошибках выводить путь относительно `root`, а не `path.name`.

## 3. `daily_bonus_available_at` никогда не становится `null`

`me_out` возвращает `last_daily_bonus_at + cooldown`, даже когда это время уже прошло. По ТЗ `null` = «доступен сейчас», и фронт (`index.js`) блокирует кнопку при не-null значении. В итоге после первого бонуса кнопка заблокирована навсегда.

**Исправление:** в `daily_bonus_available_at(...)` возвращать `None`, если `last_daily_bonus_at is None` или вычисленное время `<= datetime.now(UTC)`.

**Тест** `test_me_daily_bonus_available_at`: сразу после регистрации `null`; после бонуса — дата в будущем; после сдвига `last_daily_bonus_at` на 25 ч назад — снова `null`.

## 4. Logout не удаляет cookie `__Host-sid` в браузере

`clear_session_cookie` вызывает `delete_cookie` без `secure`, `httponly` и `samesite`. Сейчас ответ выглядит так: `sid=""; Max-Age=0; Path=/; SameSite=lax`. Браузер отвергает `Set-Cookie` для префикса `__Host-` без `Secure`, поэтому в продакшен-режиме cookie останется в браузере. Сессия при этом на сервере отозвана, но cookie остаётся мусором.

**Исправление:** `response.delete_cookie(settings.cookie_name, path="/", secure=settings.cookie_secure, httponly=True, samesite="strict")`.

**Тест** `test_logout_cookie_secure_mode` (в `test_security.py`): monkeypatch `cookie_secure=True`, регистрация, logout с cookie `__Host-sid=<token>` в заголовке. Заголовок `set-cookie` ответа содержит `__Host-sid=`, `Max-Age=0`, `Secure`, `HttpOnly`, `SameSite=strict`.

## 5. Обработчик HTTP-ошибок превращает всё в 500

`http_exception_handler` отдаёт 500 `INTERNAL` на любой статус, кроме 404/405. В итоге `/health` при упавшем Redis вместо 503 отвечает 500.

**Исправление:** для прочих статусов возвращать **тот же** `exc.status_code` с кодом `HTTP_ERROR` и сообщением `"Ошибка запроса"`. Ветки 404/405 оставить как есть.

**Тест** `test_health_503_when_redis_down`: monkeypatch `app.api.health.redis_client.ping` на корутину, которая бросает `ConnectionError`. Ожидание: 503, `error.code == "HTTP_ERROR"`.

## 6. Недостающие CSS-классы

HTML использует классы `wrap`, `page-title`, `auth-card`, `auth-title`, `auth-form-stack`, `auth-note`, `u-row`, которых нет в `css/base.css`. Добавить их в `base.css`:
- `.wrap`: `max-width:420px; margin:48px auto; padding:0 16px`;
- `.page-title` / `.auth-title`: `font-size:22px; font-weight:800; margin-bottom:16px`;
- `.auth-card`: `display:flex; flex-direction:column; gap:14px`;
- `.auth-form-stack`: `display:flex; flex-direction:column; gap:14px`;
- `.auth-note`: `font-size:13px; color:var(--muted)`, ссылки внутри — `color:var(--gold)`;
- `.u-row`: `display:flex; justify-content:space-between; gap:8px; font-size:14px`, `span` — `color:var(--muted)`, `b` — `font-family:var(--mono)`.

---

## Проверка (приложить вывод)
```bash
make test        # все тесты зелёные, включая 6 новых
```
В конце ответа — список изменённых файлов и вопросы, если были.
