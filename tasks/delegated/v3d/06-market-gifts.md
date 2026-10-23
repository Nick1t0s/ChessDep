# Цель
`test_market.py` и `test_gifts.py` под v3: лоты кейсов, фильтр вида, базовые предметы.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 5 «Маркет и подарки», 6.1 маркет, 6.3 `/market`), `backend/tests/test_market.py`, `backend/tests/test_gifts.py`, `backend/app/services/market.py`, `backend/app/api/market.py`, `backend/tests/conftest.py`.

# Область
`backend/tests/test_market.py`, `backend/tests/test_gifts.py`.

# Что сделать
- Коды скинов `genesis-*` не изменились — существующие тесты должны в основном работать. Исправить то, что сломалось из-за 13 базовых предметов у каждого пользователя (подсчёты инвентаря, «первый предмет» и т. п.) и формы `ListingItemOut` (`kind`, `def`, `case`).
- Новые тесты в `test_market.py`:
  - `test_list_and_buy_case` — `[c] = await give_cases("alice", [1])`; выставить за 150; лот: `item.kind == "case"`, `item.case.id == 1`, `item.def is None`; bob покупает; предмет у bob (`GET /inventory?kind=case`); `GET /api/v1/market/cases/1` → `case.id == 1`, `stats.last_sale_price == 150`, `sales` из 1 элемента.
  - `test_kind_filter` — лоты: скин `genesis-wp`, доска `genesis-board-paper`, кейс 1; `?kind=piece` → только скин; `?kind=board` → только доска; `?kind=case` → только кейс; `?case_id=1` → кейс; `?set=genesis` → скин и доска.
  - `test_base_item_not_listable` — базовый предмет → 400 `ITEM_BOUND`.
- Новые тесты в `test_gifts.py`:
  - `test_gift_case` — подарить кейс-предмет bob → 200; у bob в инвентаре; в списке подарков `item.kind == "case"`.
  - `test_gift_base_item` — базовый → 400 `ITEM_BOUND`.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_market.py tests/test_gifts.py` — всё проходит.

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
