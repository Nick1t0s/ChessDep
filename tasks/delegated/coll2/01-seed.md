# Цель
Новые сид-данные Genesis по контракту и заморозка старых для миграции 0003.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 3, 4), `backend/app/seed_data.py`, `backend/alembic/versions/0003_items.py`.

# Область
1. Создать `backend/app/seed_data_v1.py` — ТОЧНАЯ копия текущего `backend/app/seed_data.py`, но функция переименована `genesis_rows` → `genesis_rows_v1`, в docstring модуля: «Замороженные сид-данные v1 для миграции 0003. Не менять.»
2. В `backend/alembic/versions/0003_items.py` заменить только строку `from app.seed_data import genesis_rows` на `from app.seed_data_v1 import genesis_rows_v1 as genesis_rows`. Больше в этом файле ничего не менять.
3. Переписать `backend/app/seed_data.py`:
   - оставить `import app.core.clock as clock` и `RARITY_VALUES` без изменений;
   - удалить `PIECES`, `PIECE_VARIANTS`, `BOARD_VARIANTS`, `PIECE_CASE_WEIGHTS`, `BOARD_WEIGHTS`;
   - добавить:
```python
SIDES: tuple[str, ...] = ("w", "b")
PIECE_TYPES: tuple[str, ...] = ("P", "N", "B", "R", "Q", "K")

PIECE_NAMES: dict[str, str] = {
    "wP": "Белая пешка", "wN": "Белый конь", "wB": "Белый слон",
    "wR": "Белая ладья", "wQ": "Белый ферзь", "wK": "Белый король",
    "bP": "Чёрная пешка", "bN": "Чёрный конь", "bB": "Чёрный слон",
    "bR": "Чёрная ладья", "bQ": "Чёрный ферзь", "bK": "Чёрный король",
}

# Канонический порядок 12 скинов коллекции: белые P..K, затем чёрные P..K.
CANONICAL_SLOTS: tuple[str, ...] = tuple(s + p for s in SIDES for p in PIECE_TYPES)

GENESIS_RARITY: dict[str, str] = {
    "P": "common", "N": "uncommon", "B": "uncommon",
    "R": "rare", "Q": "epic", "K": "legendary",
}
GENESIS_COLORS: dict[str, str] = {"w": "#ffffff", "b": "#ffc93c"}
# Результат auto_weights для Genesis при весах редкостей по умолчанию.
GENESIS_WEIGHTS: dict[str, int] = {
    "common": 3996000, "uncommon": 399500, "rare": 160000, "epic": 32000, "legendary": 10000,
}


def item_code(collection_code: str, side: str, piece_type: str) -> str:
    return f"{collection_code}-{side}{piece_type.lower()}"


def item_name(collection_name: str, side: str, piece_type: str) -> str:
    return f"{collection_name} | {PIECE_NAMES[side + piece_type]}"
```
   - `genesis_rows()` возвращает `{"collections", "item_defs", "cases", "case_drops"}`:
     - collections: `[{"id": 1, "code": "genesis", "name": "Genesis", "description": "Первая коллекция. Скины-заглушки.", "status": "released", "released_at": now}]`, `now = clock.now()`;
     - item_defs: 12 штук, id 1..12 в порядке `CANONICAL_SLOTS`; каждый `{"id", "collection_id": 1, "code": item_code("genesis", side, pt), "name": item_name("Genesis", side, pt), "side": side, "piece_type": pt, "rarity": GENESIS_RARITY[pt], "value": RARITY_VALUES[rarity], "asset": {"type": "stub", "color": GENESIS_COLORS[side]}, "is_upgrade_target": True}` (ключа `kind` НЕТ);
     - cases: `[{"id": 1, "code": "genesis", "name": "Genesis", "price": 100, "status": "active", "sort": 1}]` (ключей `collection_id` и `is_active` НЕТ);
     - case_drops: по одному на каждый скин: `{"case_id": 1, "item_def_id": d["id"], "weight": GENESIS_WEIGHTS[d["rarity"]]}`.
   - docstring модуля обновить: используют `alembic/versions/0006_collections_v2.py` и `tests/conftest.py`.

# Готово, когда
`python3 -m py_compile backend/app/seed_data.py backend/app/seed_data_v1.py backend/alembic/versions/0003_items.py` без ошибок.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md`. Имена, поля, коды ошибок и тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`.
- Тесты бэкенда в этой волне НЕ запускаются и будут падать — это ожидаемо, их чинит следующая волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
