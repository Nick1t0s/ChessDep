# Цель
Новый `backend/tests/test_cases_admin.py`: админка кейсов v3 и пула ежедневной награды, выдача предметов.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1 «Кейс», 5 «Кейс», «Ежедневная награда», 6.1–6.3 админ), `backend/app/services/catalog_admin.py`, `backend/app/api/admin_catalog.py`, `backend/tests/conftest.py`, `backend/tests/test_catalog_admin.py` (стиль хелперов).

# Область
Создать только `backend/tests/test_cases_admin.py`.

# Тесты
1. `test_case_kinds_validation` — `POST /api/v1/admin/cases`: `kind: "set"` без `set_id` → 422; `kind: "custom"` с `set_id` → 422; `sale_starts_at >= sale_ends_at` → 422; `kind: "set", set_id: 1` → 400 `SET_IS_BASE`; `set_id: 999` → 404 `SET_NOT_FOUND`; корректный `kind: "collection", collection_id: 2` → 201, `status == "draft"`, `sold_count == 0`, `collection == {"code": "genesis", "name": "Genesis"}`.
2. `test_auto_drops_by_kind` — кейс `set` (набор 2): `drops/auto` `{}` → 14 дропов; кейс `collection` (коллекция 2) → 12; кейс `custom`: `{}` → 422; `{"set_ids": [2]}` → 14; `{"collection_ids": [2]}` → 12; `{"set_ids": [1]}` → 400 `SET_IS_BASE`.
3. `test_manual_drops_scope` — кейс `collection` (коллекция 2): `PUT drops` с доской 26 → 400 `DROP_ITEM_NOT_AVAILABLE`; со скином 14 → 200; кейс `custom`: с базовым скином 1 → 400 `DROP_ITEM_NOT_AVAILABLE`; с 26 и 14 → 200.
4. `test_publish_unpublish` — без дропов publish → 400 `CASE_NOT_READY`; с дропами → `on_sale`, `on_sale_now is True`, кейс в `GET /api/v1/shop`; повторный publish → 400 `CASE_NOT_READY`; `PUT drops` у опубликованного → 400 `CASE_LOCKED`; `DELETE` → 400 `CASE_LOCKED`; unpublish → `off_sale`, нет в `/shop`; повторный unpublish → 400 `CASE_NOT_ON_SALE`; publish снова → `on_sale`.
5. `test_publish_requires_released_sets` — черновик-набор с коллекцией (через `POST /admin/sets` и `/collections`, 12 фигур), кейс `custom` с его коллекцией в автовесах → publish → 400 `CASE_NOT_READY`; выпустить набор → publish → 200.
6. `test_retire_set_unpublishes` — выпущенный новый набор + опубликованный кейс по нему; retire набора → кейс `off_sale`; в аудите `set.retire` payload `{"unpublished_case_ids": [case_id]}`; publish → 400 `CASE_NOT_READY`; `GET /api/v1/cases/{id}` → 200 (`on_sale_now: false`).
7. `test_patch_limits` — `PATCH /admin/cases/1` `{"stock_limit": 5, "sale_ends_at": <через сутки ISO>}` → 200, поля сохранены; `{"stock_limit": null}` → снято; `{"sale_starts_at": <через 2 суток>, ...}` при `sale_ends_at` через сутки → 422. Купить кейс 1 дважды от `alice` (`POST /api/v1/cases/1/buy`), затем `PATCH {"stock_limit": 1}` → 422.
8. `test_daily_pool_admin` — `GET /admin/daily-reward-pool` → `[{"case": {... "id": 1 ...}, "weight": 1}]`; `PUT` `[{"case_id": 1, "weight": 3}]` → 200 и вес 3; черновой кейс в пуле → 400 `CASE_NOT_AVAILABLE`; повтор `case_id` → 422; `PUT []` → пул пуст.
9. `test_grant_item_and_case` — `POST /admin/users/{alice_id}/grant-item` `{"item_def_id": 14}` → `kind == "skin"`, `source == "admin_grant"`; `{"case_id": 1}` → `kind == "case"`, `case.id == 1`, `wear is None`; `{"item_def_id": 1}` (базовый) → 400 `ITEM_DEF_NOT_AVAILABLE`; оба поля → 422; черновой кейс → 400 `ITEM_DEF_NOT_AVAILABLE`.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_cases_admin.py` — всё проходит.

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
