# Цель
Магазин, покупка и открытие кейсов, публичный каталог: обновить `test_catalog.py`, `test_cases_open.py`, создать `test_shop.py`.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1, 5 «Кейс», 6.1, 6.3 публично), `backend/tests/test_catalog.py`, `backend/tests/test_cases_open.py`, `backend/app/services/cases.py`, `backend/app/api/items.py`, `backend/tests/conftest.py`.

# Область
`backend/tests/test_catalog.py`, `backend/tests/test_cases_open.py`, создать `backend/tests/test_shop.py`.

# Тесты
`test_catalog.py`: `test_seed_sets` — `GET /api/v1/sets` → только `genesis` (`collections_count 1`, `boards_count 2`); `GET /api/v1/sets/genesis` → 1 коллекция из 12 скинов в каноническом порядке + 2 доски; `GET /api/v1/sets/base` — 200 (базовый набор не в списке, но детально доступен); `GET /api/v1/collections/genesis` → `set == {"code":"genesis","name":"Genesis"}`, 12 скинов. `test_seed_weights_match_auto_formula` — дропы кейса 1 == `auto_weights` по скинам 14–27, сумма 10 000 000. `test_case_detail_chances` — `GET /api/v1/cases/1` (без логина): 14 дропов, у `genesis-board-albion` `chance == pytest.approx(6000/10_000_000)`, `chance_text == format_chance(...)`, `on_sale_now is True`, `kind == "set"`, `set.code == "genesis"`. `test_exterior_boundaries` — без изменений. Удалить проверки старого `/cases` и `/collections` (список).
`test_cases_open.py` (открытие предмета-кейса):
- `test_weighted_pick_boundaries` — без изменений.
- `test_open_case_item_deterministic` — `[item] = await give_cases("alice", [1])`; `rng.values = [<как в старом тесте>, …]`; `POST /api/v1/inventory/{item}/open` → 200; победитель = `weighted_pick` по дропам из БД (как в старом тесте); `len(strip) == 60`, `win_index ∈ [45, 54]`, все id ленты есть в `defs`; кейс-предмет в БД `status == "burned"`; новый скин `source == "case"`; баланс alice не изменился (1000); запись `rolls` `kind == "case_open"` с `input["inventory_item_id"] == item`.
- `test_open_errors` — чужой кейс → 400 `ITEM_NOT_OWNED`; скин (не кейс) → 400 `ITEM_NOT_CASE`; повторное открытие → 400 `ITEM_NOT_OWNED`; кейс, снятый с продажи (`POST /api/v1/admin/cases/1/unpublish` от `admin`), всё равно открывается.
- `test_open_concurrent` — два параллельных open одного предмета: ровно один 200.
`test_shop.py`:
- `test_shop_list` — `GET /api/v1/shop` (аноним) → `[кейс 1]`, `stock_limit is None`, `stock_left is None`.
- `test_buy_case` — alice покупает кейс 1: `item.kind == "case"`, `item.case.id == 1`, `wear is None`, `source == "shop"`, `balance == 900`; ledger `case_purchase` −100; `GET /inventory?kind=case` содержит предмет; кейс не открылся (скинов, кроме 13 базовых, нет).
- `test_buy_insufficient_funds` — баланс 50 (через `db`), покупка → 400 `INSUFFICIENT_FUNDS` (проверь код в `app/services/economy.py`); `sold_count` не изменился.
- `test_stock_limit` — `PATCH /admin/cases/1 {"stock_limit": 2}`; alice и bob покупают → 200, 200; третья покупка → 400 `CASE_NOT_AVAILABLE`; `GET /admin/cases` у кейса 1 `status == "off_sale"`, `sold_count == 2`; нет в `/shop`.
- `test_stock_limit_concurrent` — `stock_limit: 3`, у alice баланс 10000; 6 параллельных покупок → ровно 3 по 200.
- `test_sale_window` — `PATCH /admin/cases/1 {"sale_starts_at": <now+1h>}` → нет в `/shop`, покупка → 400 `CASE_NOT_AVAILABLE`; фикстура `frozen` `advance(7200)` → в `/shop`, покупка 200; `{"sale_ends_at": <now(frozen)+1h>}`, `advance(7200)` → снова нет; `GET /api/v1/cases/1` → `on_sale_now: false`.
- `test_draft_case_hidden` — черновик (`POST /admin/cases`) → `GET /api/v1/cases/{id}` 404 `CASE_NOT_FOUND`, buy → 404.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_catalog.py tests/test_cases_open.py tests/test_shop.py` — всё проходит.

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
