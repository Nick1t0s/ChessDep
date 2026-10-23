# Цель
`test_inventory.py` под v3: базовые предметы, 13 слотов, запрет боя без полной экипировки, доска в снапшоте.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1 «Базовый набор», «Экипировка», 5 «Экипировка», «Снапшот»), `backend/tests/test_inventory.py`, `backend/app/api/items.py`, `backend/app/services/items.py`, `backend/app/services/matchmaking.py`, `backend/app/api/invites.py`, `backend/tests/conftest.py`, `backend/tests/test_matchmaking.py` (как тестируется очередь и `tick`).

# Область
Только `backend/tests/test_inventory.py`.

# Тесты (существующие адаптировать; добавить новые)
- `test_base_items_on_register` — у alice `GET /inventory` → 13 предметов, все `bound: true`, `source == "base"`, `wear == 0.0`; `GET /loadout` → все 13 слотов заняты, `complete is True`, `board.def.code == "base-board"`.
- `test_inventory_and_equip` — выдать `genesis-wq`, `genesis-board-paper`; надеть в `wQ` и `board`; `genesis-wq` в `bQ` → 400 `ITEM_SLOT_MISMATCH`; доску в `wP` → 400; кейс (`give_cases`) в любой слот → 400 `ITEM_SLOT_MISMATCH`; `PUT /loadout/x` → 422; фильтры `?kind=board` (только доски), `?kind=case`, `?slot=board`, `?side=w`.
- `test_loadout_incomplete_blocks_play` — alice снимает `wK` (`PUT /loadout/wK {"inventory_item_id": null}`) → `complete is False`; `POST /matchmaking/queue` → 400 `LOADOUT_INCOMPLETE`; `POST /invites` → 400 `LOADOUT_INCOMPLETE`; bob создаёт инвайт, alice принимает → 400 `LOADOUT_INCOMPLETE`; alice создаёт инвайт ДО снятия, затем снимает слот, bob принимает → 400 `LOADOUT_INCOMPLETE` (проверка создателя в `create_game`); вернуть базовый скин в слот → игра стартует.
- `test_matchmaking_drops_incomplete` — alice и bob в очереди (по образцу `test_matchmaking.py`), затем alice снимает слот, `tick` → партия не создана, alice выкинута из очереди (`GET /matchmaking/status` у alice — не в очереди), bob остался в очереди. (Если по коду воркера статус называется иначе — смотри `services/matchmaking.py::status`.)
- `test_loadout_snapshot_in_game` — alice надевает `genesis-wq` (`wQ`), `genesis-bq` (`bQ`), `genesis-board-paper` (`board`); bob ничего не меняет; партия; в `state["players"][color]["loadout"]`: у alice ключ `"Q"` — скин её стороны, `"board"` — `genesis-board-paper`; остальные ключи — базовые (`base-*`), у bob `"board"` — `base-board`; всего 7 ключей у каждого.
- `test_bound_items_rules` — базовый предмет alice: `POST /market/listings` → 400 `ITEM_BOUND`; `POST /gifts` → 400 `ITEM_BOUND`; `POST /upgrade/preview` с ним во входах → 400 `ITEM_BOUND`; кейс-предмет во входах апгрейда → 400 `ITEM_NOT_UPGRADABLE`. (Пути и тела запросов маркета, подарков и апгрейда — смотри соответствующие api-файлы.)
- Остальные существующие тесты (`test_equip_foreign_or_burned`, `test_inventory_hides_burned`, `test_loadout_concurrent_put`, `test_inventory_query_count`) — адаптировать под 13 слотов и наличие 13 базовых предметов.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_inventory.py` — всё проходит.

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
