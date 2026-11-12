# Цель
Обновить `backend/tests/test_catalog.py` и `backend/tests/test_cases_open.py` под сид v2 и статусы кейса.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 4, 5 «Кейс», 6.1), оба файла тестов, `backend/tests/conftest.py`, `backend/app/services/cases.py`, `backend/app/api/items.py`.

# Область
`backend/tests/test_catalog.py`, `backend/tests/test_cases_open.py`.

# Что сделать
`test_catalog.py`:
- `test_seed_genesis`: `items_count == 12`; `GET /cases` → коды `["genesis"]` и у кейса `collections == [{"code": "genesis", "name": "Genesis"}]`; `GET /collections/genesis` → коды скинов в порядке `genesis-wp, genesis-wn, genesis-wb, genesis-wr, genesis-wq, genesis-wk, genesis-bp, …, genesis-bk`; asset белых `#ffffff`, чёрных `#ffc93c`; ни у одного элемента нет ключа `kind`.
- `test_seed_weights_match_auto_formula`: один кейс `genesis`, веса == `auto_weights(...)`, сумма `9_994_000`.
- `test_case_detail_chances`: `GET /cases/1`: 12 дропов, сумма шансов ≈ 1; у дропа `genesis-wk` `chance == pytest.approx(10000 / 9994000)`; `chance_text` у него — запиши то значение, которое реально вернёт `format_chance(10000 / 9994000)` из `app.chess_engine` (вычисли в тесте: `assert d["chance_text"] == format_chance(10000 / 9994000)`); у кейса `collections == [{"code":"genesis","name":"Genesis"}]`.
- `test_exterior_boundaries` не менять.

`test_cases_open.py`:
- `test_weighted_pick_boundaries`, `test_open_case_insufficient_funds`, `test_open_case_concurrent` — только заменить id/коды/цену по сиду (кейс id 1, цена 100), если они ссылаются на старые.
- `test_open_case_deterministic`: кейс id 1; пересчитать ожидаемого победителя: дропы отсортированы по `item_def_id` (1..12), `weighted_pick` берёт первый дроп с накопленной суммой > `r * 9994000`. Подставь в `rng.values` то же первое значение, что сейчас, и вычисли ожидаемый `item_def_id` по этой формуле руками в тесте (через `weighted_pick` из `app.services.cases` по дропам из БД — допустимо), остальное (лента 60, `win_index` в [45, 54], `defs` содержит все id ленты, баланс, запись `rolls`) — как сейчас.
- `test_open_unavailable_case`: вместо старой логики: через `admin` создать кейс `POST /api/v1/admin/cases` `{code:"c2", name:"C2", price:10}` (draft) → `GET /api/v1/cases/{id}` 404 `CASE_NOT_FOUND`, `POST /api/v1/cases/{id}/open` (от admin) 404 `CASE_NOT_FOUND`; закрыть кейс genesis `POST /api/v1/admin/cases/1/close` → `GET /api/v1/cases/1` 404, `POST /api/v1/cases/1/open` 400 `CASE_NOT_AVAILABLE`, а `GET /api/v1/cases` → `[]`.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_catalog.py tests/test_cases_open.py` — всё проходит.

# Новые сид-данные (одинаковы в каждом тесте, `tests/conftest.py` их вставляет)
Коллекция `genesis` (id 1, released). 12 скинов, id и код:
| id | code | side | piece_type | rarity | value |
|---|---|---|---|---|---|
| 1 | genesis-wp | w | P | common | 20 |
| 2 | genesis-wn | w | N | uncommon | 60 |
| 3 | genesis-wb | w | B | uncommon | 60 |
| 4 | genesis-wr | w | R | rare | 150 |
| 5 | genesis-wq | w | Q | epic | 500 |
| 6 | genesis-wk | w | K | legendary | 1500 |
| 7 | genesis-bp | b | P | common | 20 |
| 8 | genesis-bn | b | N | uncommon | 60 |
| 9 | genesis-bb | b | B | uncommon | 60 |
| 10 | genesis-br | b | R | rare | 150 |
| 11 | genesis-bq | b | Q | epic | 500 |
| 12 | genesis-bk | b | K | legendary | 1500 |
Имена: `"Genesis | Белая пешка"`, `"Genesis | Белый конь"`, … `"Genesis | Чёрный король"`. asset белых `{"type":"stub","color":"#ffffff"}`, чёрных `{"type":"stub","color":"#ffc93c"}`.
Один кейс: id 1, code `genesis`, name `Genesis`, price 100, status `active`, дропы — все 12 скинов, веса: common 3996000, uncommon 399500, rare 160000, epic 32000, legendary 10000 (сумма 9 994 000). Скинов досок и мифических скинов НЕТ.

# Замена старых кодов (сохраняет value)
| старый | новый |
|---|---|
| genesis-pawn-chalk | genesis-wp |
| genesis-knight-chalk, genesis-bishop-chalk, genesis-board-paper | genesis-bp |
| genesis-board-porcelain | genesis-wn |
| genesis-pawn-frost | genesis-wr |
| genesis-knight-frost | genesis-br |
| genesis-queen-snow | genesis-wq |
| genesis-pawn-snow, genesis-board-marble | genesis-bq |
| genesis-board-albion (mythic 5000) | genesis-wk, но в начале теста выставить ему value 5000: `async with SessionLocal() as s, s.begin(): await s.execute(update(ItemDef).where(ItemDef.code == "genesis-wk").values(value=5000))` |
Если тест проверял `kind`, `piece_type`, имя, редкость или слот старого скина — поменять ожидание на значение нового скина из таблицы выше. Старые кейсы `genesis-pieces` (id 1) и `genesis-boards` (id 2) заменены одним кейсом id 1.

# Правила
- Контракт: `docs/contracts-collections.md`. Код приложения (`backend/app/**`) НЕ менять — только тесты из «Область». Если тест падает из-за кода приложения, а не теста — не «чинить» тест под баг: оставить тест правильным по контракту и описать расхождение в SUMMARY.
- Не удалять тесты и не ослаблять проверки, кроме тех, что проверяют удалённое (доски, `kind`, удалённые эндпоинты).
- Проверка: `bash scripts/test_isolated.sh <твои файлы тестов>` (например `bash scripts/test_isolated.sh tests/test_market.py`; пути — относительно `backend/`). Это Docker, ~1–2 минуты. Должно пройти без `failed`/`error`. Другие файлы тестов сейчас могут падать — их чинят параллельно, не трогай.
- Если что-то не сходится — остановиться и описать в SUMMARY, не придумывать.
