# Цель
`test_upgrade.py`, `test_admin_users.py`, `test_auth.py` под v3.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1, 5 «Апгрейд»), `backend/tests/test_upgrade.py`, `backend/tests/test_admin_users.py`, `backend/tests/test_auth.py`, `backend/app/services/upgrade.py`, `backend/tests/conftest.py`.

# Область
`backend/tests/test_upgrade.py`, `backend/tests/test_admin_users.py`, `backend/tests/test_auth.py`.

# Что сделать
- `test_upgrade.py`: коды `genesis-*` прежние. Где тест выставлял `genesis-wk.value = 5000` для «мифической» цели — заменить на доску `genesis-board-albion` (mythic 5000, цель апгрейда) и убрать правку value. Блок «Цель из черновой коллекции»: создать черновой набор `POST /api/v1/admin/sets` и коллекцию `POST /api/v1/admin/sets/{id}/collections` (12 фигур), цель — скин `winter-wq` из ответа (`collections[0].items`). Добавить: цель — базовый скин (id 1) → недоступна (тот же reason/код, что для недоступной цели); вход — базовый предмет → 400 `ITEM_BOUND`; вход — кейс-предмет (`give_cases`) → 400 `ITEM_NOT_UPGRADABLE`; апгрейд в доску (`genesis-board-albion`) при достаточных входах — успешен (`rng.values` по образцу `test_upgrade_success`), новый предмет `def.kind == "board"`.
- `test_admin_users.py`, `test_auth.py`: исправить то, что сломалось из-за v3 (поле `daily_bonus_available_at` удалено из `/me`; у новых пользователей 13 базовых предметов). В `test_auth.py` добавить в тест регистрации проверку: после регистрации у пользователя 13 предметов `source == "base"` и 13 строк `loadouts`.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_upgrade.py tests/test_admin_users.py tests/test_auth.py` — всё проходит.

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
