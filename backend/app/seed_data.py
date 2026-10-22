"""Сид-данные коллекции Genesis: один источник для миграции и conftest.

Чистый модуль: без БД и I/O. Используют
- alembic/versions/0006_collections_v2.py (op.bulk_insert),
- tests/conftest.py (TRUNCATE + вставка перед каждым тестом).
"""
import app.core.clock as clock

RARITY_VALUES: dict[str, int] = {
    "common": 20,
    "uncommon": 60,
    "rare": 150,
    "epic": 500,
    "legendary": 1500,
    "mythic": 5000,
}

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


def genesis_rows() -> dict[str, list[dict]]:
    now = clock.now()
    collections = [
        {
            "id": 1,
            "code": "genesis",
            "name": "Genesis",
            "description": "Первая коллекция. Скины-заглушки.",
            "status": "released",
            "released_at": now,
        }
    ]
    item_defs: list[dict] = []
    item_id = 0
    for side in SIDES:
        for piece_type in PIECE_TYPES:
            item_id += 1
            rarity = GENESIS_RARITY[piece_type]
            item_defs.append({
                "id": item_id,
                "collection_id": 1,
                "code": item_code("genesis", side, piece_type),
                "name": item_name("Genesis", side, piece_type),
                "side": side,
                "piece_type": piece_type,
                "rarity": rarity,
                "value": RARITY_VALUES[rarity],
                "asset": {"type": "stub", "color": GENESIS_COLORS[side]},
                "is_upgrade_target": True,
            })
    cases = [
        {
            "id": 1,
            "code": "genesis",
            "name": "Genesis",
            "price": 100,
            "status": "active",
            "sort": 1,
        }
    ]
    case_drops: list[dict] = []
    for row in item_defs:
        case_drops.append(
            {"case_id": 1, "item_def_id": row["id"], "weight": GENESIS_WEIGHTS[row["rarity"]]}
        )
    return {
        "collections": collections,
        "item_defs": item_defs,
        "cases": cases,
        "case_drops": case_drops,
    }
