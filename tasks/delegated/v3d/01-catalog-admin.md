# Цель
Переписать `backend/tests/test_catalog_admin.py` под админку наборов v3 (наборы, коллекции, доски, скины).

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 5 «Набор», «Коллекция / доска», 6.1–6.3 админ), текущий `backend/tests/test_catalog_admin.py` (хелперы `pieces_body`, стиль), `backend/app/api/admin_catalog.py`, `backend/app/services/catalog_admin.py`, `backend/tests/conftest.py`.

# Область
Только `backend/tests/test_catalog_admin.py`.

# Тесты
Хелперы: `pieces_body()` (как сейчас), `async create_set(admin, code="winter") -> dict` (`POST /api/v1/admin/sets`, 201), `async add_collection(admin, set_id, code="winter") -> dict` (`POST /api/v1/admin/sets/{id}/collections`, 201, возвращает деталь набора), `async add_board(admin, set_id, code="winter-board") -> dict`.
1. `test_admin_required` — без админа 403 на `GET /admin/sets`, `POST /admin/sets`.
2. `test_set_create_and_list` — создать; `status == "draft"`, `is_base is False`, счётчики 0; повторный код → 409 `SET_CODE_TAKEN`; `GET /admin/sets` содержит `base` (`is_base: true`), `genesis` и новый; черновик не виден публично: `GET /api/v1/sets/winter` → 404 `SET_NOT_FOUND`, нет в `GET /api/v1/sets`.
3. `test_collection_in_set` — коллекция в черновике: деталь набора содержит 1 коллекцию с 12 скинами `winter-wp` … `winter-bk` по порядку, у скинов `kind == "piece"`, `set == {"code": "winter", "name": <имя>}`; 11 фигур → 422; повторный код коллекции → 409.
4. `test_board_in_set` — доска: 201, `kind == "board"`, `side is None`, `collection is None`, `asset` = переданный; asset с `color` вместо `light/dark` → 422; деталь набора: `boards` из 1 элемента; `DELETE /admin/item-defs/{board_id}` → 204; удаление скина фигуры → 400 `ITEM_DEF_LOCKED`.
5. `test_release_and_retire` — пустой набор: release → 400 `SET_EMPTY`; с коллекцией и доской: release → `released`; повторный → 400 `SET_NOT_DRAFT`; после выпуска добавить коллекцию/доску → 400 `SET_NOT_DRAFT`; публично `GET /api/v1/sets/winter` → 200 (1 коллекция, 1 доска), `GET /api/v1/sets` содержит его с `collections_count == 1`, `boards_count == 1`; retire → `retired`; повторный retire → 400 `SET_NOT_RELEASED`.
6. `test_base_set_protected` — `POST /admin/sets/1/retire` → 400 `SET_IS_BASE`; `DELETE /admin/sets/1` → 400 `SET_IS_BASE`; `GET /api/v1/sets` не содержит `base`.
7. `test_item_def_patch` — в черновике `PATCH /admin/item-defs/{piece_id}` `{"rarity": "mythic", "value": 999, "name": "X", "asset": {"type": "stub", "color": "#123456"}}` → 200; фигуре asset доски → 422; доске asset фигуры → 422; после выпуска `{"rarity": "rare"}` → 400 `ITEM_DEF_LOCKED`, `{"value": 77}` → 200; `{"side": "b"}` → 422.
8. `test_delete_draft_set` — набор с коллекцией, кейс `POST /admin/cases` `{code: "w-case", name: "W", price: 10, kind: "set", set_id: <id>}`; `DELETE /admin/sets/{id}` → 204; кейс удалён (`GET /admin/cases` не содержит `w-case`); удаление выпущенного набора `genesis` (id 2) → 400 `SET_NOT_DRAFT`.
9. `test_delete_collection` — в черновике `DELETE /admin/collections/{id}` → 204, деталь набора без коллекций; у выпущенного — 400 `SET_NOT_DRAFT`.
10. `test_admin_item_defs_list` — `GET /admin/item-defs`: 14 скинов genesis, нет `base-*`; после создания черновика с коллекцией — 26.
11. `test_audit` — после создания набора, коллекции, доски, выпуска в `admin_audit` есть действия `set.create`, `collection.create`, `board.create`, `set.release`.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_catalog_admin.py` — всё проходит.

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
