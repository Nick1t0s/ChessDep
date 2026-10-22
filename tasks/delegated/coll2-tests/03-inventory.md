# Цель
Обновить `backend/tests/test_inventory.py` под 12 слотов и снапшот по стороне.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 5 «Экипировка», «Снапшот», 6.1 `LoadoutOut`, 6.3 `/inventory`), `backend/tests/test_inventory.py`, `backend/tests/conftest.py` (`give_items`, `start_game`), `backend/app/api/items.py`.

# Область
Только `backend/tests/test_inventory.py`.

# Что сделать
- Заменить коды по таблице. Слоты: `P` → `wP`/`bP` по стороне скина и т. д.; слота `board` больше нет; ответ `/loadout` содержит ровно 12 ключей `wP…bK`.
- `test_inventory_and_equip`: дополнительно проверить: `genesis-wp` в слот `bP` → 400 `ITEM_SLOT_MISMATCH`; `PUT /loadout/board` → 422; фильтр `GET /inventory?side=w` возвращает только `side == "w"`, `?slot=bQ` — только `genesis-bq`.
- `test_loadout_snapshot_in_game`: alice надевает `genesis-wq` в `wQ` и `genesis-bq` в `bQ`; bob — `genesis-wr` в `wR`. Старт партии через существующий хелпер; определить, кто белые. Ожидание: в `game.white_loadout` (или `players.white.loadout` в состоянии партии — как проверял старый тест) ключи — БЕЗ префикса (`"Q"`, `"R"`), берутся только слоты стороны, которой играет игрок: если alice белые — `white_loadout == {"Q": {...genesis-wq...}}`, у bob чёрными — `black_loadout == {}` (у него только белый слот); если наоборот — alice чёрными `{"Q": {...genesis-bq...}}`, bob белыми `{"R": {...genesis-wr...}}`. Проверить обе ветки через `if`, по фактическому цвету.
- Остальные тесты — только замена кодов и слотов.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_inventory.py` — всё проходит.

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
