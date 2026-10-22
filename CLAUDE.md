# ChessDep — правила для Claude Code

Сначала прочитай `docs/ARCHITECTURE.md` — там всё устройство проекта, механизмы, решения и рецепты. Исходное ТЗ — `docs/TZ.md`, доп. контракт — `docs/contracts-spectate.md`.

## Инварианты (нарушать нельзя)
- Сервер — единственный источник истины. В браузере только cookie сессии; фронт ничего не вычисляет из игровой логики.
- Время — только `clock.now()`; случайность — только `rolls.get_rng()`; каждый бросок — в `rolls`.
- Любой `SELECT … FOR UPDATE` — с `.execution_options(populate_existing=True)`.
- Порядок блокировок: `market_listings` → `inventory_items` → `games` → `users` (внутри — по возрастанию id).
- Баланс — только через `economy.apply_delta` (пишет `ledger`).
- Redis (pub/sub, ZSET дедлайнов) — только через `after_commit`; в своей сессии — `run_after_commit` после коммита.
- Действия админа — в `admin_audit`. Роль admin — только CLI `make make-admin LOGIN=…`.
- Фронт: DOM только через `h()`/`textContent`; без `innerHTML`, `Math.random`, хранилищ браузера, инлайн-скриптов/стилей; цвета — `style.setProperty`.
- Миграции — руками, с `downgrade`; новые таблицы — в `_TRUNCATE_SQL` в `backend/tests/conftest.py`.

## Проверка изменений
- `make test` (или `bash scripts/test_isolated.sh` для параллельных копий).
- `bash scripts/check_frontend.sh` для фронта.
- После правок бэкенда на живом стеке: `docker compose up -d --build api worker`.

## Как здесь пишется код
Код пишут исполнители GLM через `~/.claude/skills/delegate/oc-dispatch.sh` по жёстким ТЗ (глобальные правила — `~/.claude/CLAUDE.md`). Контракт сначала кладётся в `docs/`, заглушки общих файлов (роутеры в `main.py` и т. п.) делаются заранее, чтобы задачи не пересекались. Копии ТЗ — в `tasks/delegated/<фича>/`.
