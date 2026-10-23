# Цель
Новый `backend/tests/test_daily_reward.py`; удалить тесты старого бонуса из `test_economy.py`.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1 «Ежедневная награда», 5 «Ежедневная награда», 6.1), `backend/app/services/daily_reward.py`, `backend/app/api/me.py`, `backend/tests/test_economy.py` (особенно `test_daily_bonus_concurrent` — образец параллельного теста), `backend/tests/conftest.py`, `backend/app/models/game.py`.

# Область
Создать `backend/tests/test_daily_reward.py`; в `backend/tests/test_economy.py` удалить `test_daily_bonus_concurrent`, `test_me_daily_bonus_available_at`, `test_daily_bonus_cooldown` (остальное не трогать).

# Тесты
Хелпер `async add_wins(user_login, n, *, ply=20, finished_at=None, as_black=False)` — вставить `n` строк `Game` напрямую в БД (отдельная сессия): `status="finished"`, `result` = цвет игрока, `ply`, `finished_at` (по умолчанию `clock.now()`), соперник — другой зарегистрированный пользователь (`bob`), обязательные поля `Game` заполни по модели (`fen` начальной позиции, `time_control "3+2"`, `base_ms`, `inc_ms`, и т. п. — смотри `services/games.py::create_game`).
1. `test_status_initial` — `GET /api/v1/me/daily-reward` → `{"wins_today": 0, "wins_required": 3, "claimed_today": false, "available": false}`.
2. `test_not_ready` — 2 победы → `POST` → 400 `DAILY_REWARD_NOT_READY`, сообщение содержит `3`.
3. `test_counting_rules` — 2 победы белыми + 1 чёрными (`as_black=True`) → `wins_today == 3`; победа с `ply=5` не считается; победа вчера (`finished_at = now - 1 day`) не считается; поражение и ничья не считаются.
4. `test_claim` — 3 победы; `rng.values = [0.0]`; `POST` → 200: `case.id == 1`, `item.kind == "case"`, `item.source == "daily_reward"`; в `rolls` запись `kind == "daily_reward"` с `outcome["item_id"] == item.id`; статус → `claimed_today: true`, `available: false`; повторный `POST` → 400 `DAILY_REWARD_CLAIMED`; кейс в `GET /inventory?kind=case`.
5. `test_weighted_pool` — создать (через `admin`) второй кейс `custom` с дропами и опубликовать; `PUT /admin/daily-reward-pool` `[{case_id: 1, weight: 1}, {case_id: new, weight: 3}]`; 3 победы; `rng.values = [0.3]` → кейс 2-й по `case_id` (накопление: 1 из 4 = 0.25 < 0.3) — проверь `case.id == new`.
6. `test_empty_pool` — `PUT /admin/daily-reward-pool []`; 3 победы → 400 `DAILY_REWARD_EMPTY`.
7. `test_next_day` — фикстура `frozen`; 3 победы; claim; `advance(86400)` → `claimed_today: false`, `wins_today: 0`.
8. `test_claim_concurrent` — 3 победы; 5 параллельных `POST` → ровно один 200 (образец — `test_daily_bonus_concurrent`).
9. `test_me_has_no_bonus_field` — `GET /api/v1/me` без ключа `daily_bonus_available_at`; `POST /api/v1/me/daily-bonus` → 404 или 405.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_daily_reward.py tests/test_economy.py` — всё проходит.

# Сид v3 (вставляется `tests/conftest.py` перед каждым тестом; см. `backend/app/seed_data.py`)
- Набор id 1 `base` («Базовый», released, `is_base`), коллекция id 1 `base`; скины id 1–12 `base-wp` … `base-bk` (common, value 1, не цель апгрейда), id 13 `base-board` (доска).
- Набор id 2 `genesis` (released), коллекция id 2 `genesis`; скины id 14–25: `genesis-wp`(14, common 20), `genesis-wn`(15, uncommon 60), `genesis-wb`(16, uncommon 60), `genesis-wr`(17, rare 150), `genesis-wq`(18, epic 500), `genesis-wk`(19, legendary 1500), `genesis-bp`(20, common 20), `genesis-bn`(21), `genesis-bb`(22), `genesis-br`(23, rare 150), `genesis-bq`(24, epic 500), `genesis-bk`(25, legendary 1500); доски id 26 `genesis-board-paper` (uncommon 60), id 27 `genesis-board-albion` (mythic 5000).
- Кейс id 1 `genesis` (`kind: set`, набор 2, цена 100, `on_sale`, без лимитов), дропы — скины 14–27, веса common 3996000, uncommon 319600, rare 160000, epic 32000, legendary 10000, mythic 6000 (сумма 10 000 000).
- Пул ежедневной награды: `[{case_id: 1, weight: 1}]`. Настройка `daily_reward_wins = 3`, `reward_min_plies = 10`, `starting_balance = 1000`.
- Каждый зарегистрированный пользователь (фикстуры `alice`, `bob`, `carol`, `admin`) сразу имеет 13 базовых предметов (`source: "base"`, `bound: true`), все надеты.
- Хелперы conftest: `give_items(login, codes)` → id скинов; `give_cases(login, case_ids)` → id предметов-кейсов; `start_game(alice, bob, rng)`; фикстуры `rng` (`rng.values = [...]`), `frozen` (часы), `db`, `client`, `anonymous`.

# Правила
- Контракт: `docs/contracts-collections.md` (v3). Код приложения (`backend/app/**`) НЕ менять — только тесты из «Область». Если тест падает из-за кода приложения, а не теста — оставить тест правильным по контракту, пометить `@pytest.mark.xfail(reason="<что не так>", strict=True)` и подробно описать расхождение в SUMMARY.
- Не удалять тесты, кроме проверяющих удалённое (старый бонус, `/admin/collections` как корень, `/cases` список, `POST /cases/{id}/open`).
- Проверка: `bash scripts/test_isolated.sh <твои файлы тестов>` (пути относительно `backend/`, например `tests/test_shop.py`). Docker, 1–2 мин. Должно пройти без `failed`/`error` (xfail допустим только по правилу выше). Другие файлы сейчас могут падать — не трогай.
- Если что-то не сходится — остановиться и описать в SUMMARY, не придумывать.
