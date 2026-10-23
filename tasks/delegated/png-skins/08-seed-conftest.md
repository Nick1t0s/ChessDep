# Цель
Сид (`backend/app/seed_data.py`) использует PNG-asset вместо цветных заглушек; `backend/tests/conftest.py` перед каждым тестом заливает картинки сида в `skin_images`.

# Контекст
Прочитай: `docs/contracts-skins.md` (§3, §5), `backend/app/seed_skins.py` (готовые `seed_image_id(name)`, `seed_image_rows()`), `backend/app/seed_data.py`, `backend/tests/conftest.py` (`_TRUNCATE_SQL`, `_seed_genesis`). Картинки уже лежат в `backend/app/seed_images/`.

# Область
Только `backend/app/seed_data.py` и `backend/tests/conftest.py`.

# Правки seed_data.py
1. Добавить импорт `from app.seed_skins import seed_image_id` (после `import app.core.clock as clock`).
2. Удалить константы `BASE_COLORS` и `GENESIS_COLORS`.
3. Asset всех 27 скинов → `{"type": "png", "image": seed_image_id(<code скина>)}`:
   - фигуры базового набора: `"asset": {"type": "png", "image": seed_image_id(item_code("base", side, piece_type))},`
   - базовая доска: `"asset": {"type": "png", "image": seed_image_id("base-board")},`
   - фигуры Genesis: `"asset": {"type": "png", "image": seed_image_id(item_code("genesis", side, piece_type))},`
   - доски Genesis: `seed_image_id("genesis-board-paper")` и `seed_image_id("genesis-board-albion")`.
4. Docstring модуля заменить на:
```python
"""Сид-данные v4: наборы, базовый набор + Genesis с PNG-скинами (docs/contracts-skins.md).

Без БД; id картинок берутся из app/seed_skins.py (файлы app/seed_images/).
Использует tests/conftest.py (TRUNCATE + вставка перед каждым тестом).
Миграция 0007 использует замороженный seed_data_v3.py, 0008 переводит его на PNG.
"""
```

# Правки conftest.py
1. В `_TRUNCATE_SQL` после `"item_sets, daily_reward_pool "` дописать `skin_images`: строка станет `"item_sets, daily_reward_pool, skin_images "`.
2. В импорт из `app.models` добавить `SkinImage` (в алфавитном порядке списка); добавить `from app.seed_skins import seed_image_rows` рядом с `from app.seed_data import seed_rows`.
3. Первой строкой в теле `_seed_genesis` (до `rows = seed_rows()`): `    await db.execute(insert(SkinImage).values(seed_image_rows()))`.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_shop.py tests/test_cases_open.py tests/test_games.py` — зелёные (нужен Docker). Другие тесты (test_catalog*, test_inventory, test_upgrade, test_cases_admin) в этой волне падают из-за старых ожиданий asset — их чинит следующая волна, НЕ трогай их.

# Нельзя
Трогать другие файлы, менять id/коды/редкости сида. Если что-то не сходится — остановиться и описать в SUMMARY.
