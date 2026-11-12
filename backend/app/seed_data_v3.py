"""Замороженный сид v3 (цветные заглушки) для миграции 0007. Не менять.
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
# 13 слотов экипировки: те же 12 фигур плюс доска.
LOADOUT_SLOTS: tuple[str, ...] = CANONICAL_SLOTS + ("board",)

BASE_SET_ID: int = 1
# 13 базовых скинов в порядке слотов LOADOUT_SLOTS.
BASE_DEF_IDS: tuple[int, ...] = tuple(range(1, 14))
BASE_COLORS: dict[str, str] = {"w": "#f4f6ff", "b": "#ff5470"}

GENESIS_RARITY: dict[str, str] = {
    "P": "common", "N": "uncommon", "B": "uncommon",
    "R": "rare", "Q": "epic", "K": "legendary",
}
GENESIS_COLORS: dict[str, str] = {"w": "#ffffff", "b": "#ffc93c"}
# Результат auto_weights для Genesis при весах редкостей по умолчанию; сумма 10 000 000.
GENESIS_WEIGHTS: dict[str, int] = {
    "common": 3996000, "uncommon": 319600, "rare": 160000, "epic": 32000,
    "legendary": 10000, "mythic": 6000,
}


def item_code(collection_code: str, side: str, piece_type: str) -> str:
    return f"{collection_code}-{side}{piece_type.lower()}"


def item_name(collection_name: str, side: str, piece_type: str) -> str:
    return f"{collection_name} | {PIECE_NAMES[side + piece_type]}"


def seed_rows() -> dict[str, list[dict]]:
    now = clock.now()
    item_sets = [
        {
            "id": 1,
            "code": "base",
            "name": "Базовый",
            "description": "Стартовые скины каждого игрока.",
            "status": "released",
            "is_base": True,
            "released_at": now,
        },
        {
            "id": 2,
            "code": "genesis",
            "name": "Genesis",
            "description": "Первый набор. Скины-заглушки.",
            "status": "released",
            "is_base": False,
            "released_at": now,
        },
    ]
    collections = [
        {"id": 1, "set_id": 1, "code": "base", "name": "Базовая", "description": ""},
        {"id": 2, "set_id": 2, "code": "genesis", "name": "Genesis", "description": ""},
    ]
    item_defs: list[dict] = []
    # Базовый набор: 12 фигур коллекции base в каноническом порядке (id 1–12).
    for i, slot in enumerate(CANONICAL_SLOTS):
        side, piece_type = slot[0], slot[1:]
        item_defs.append({
            "id": i + 1,
            "set_id": 1,
            "collection_id": 1,
            "code": item_code("base", side, piece_type),
            "name": item_name("Базовая", side, piece_type),
            "kind": "piece",
            "side": side,
            "piece_type": piece_type,
            "rarity": "common",
            "value": 1,
            "asset": {"type": "stub", "color": BASE_COLORS[side]},
            "is_upgrade_target": False,
        })
    # Базовая доска (id 13).
    item_defs.append({
        "id": 13,
        "set_id": 1,
        "collection_id": None,
        "code": "base-board",
        "name": "Базовая доска",
        "kind": "board",
        "side": None,
        "piece_type": None,
        "rarity": "common",
        "value": 1,
        "asset": {"type": "stub", "light": "#454f77", "dark": "#262e4d"},
        "is_upgrade_target": False,
    })
    # Genesis: 12 фигур коллекции genesis (id 14–25).
    item_id = 13
    for side in SIDES:
        for piece_type in PIECE_TYPES:
            item_id += 1
            rarity = GENESIS_RARITY[piece_type]
            item_defs.append({
                "id": item_id,
                "set_id": 2,
                "collection_id": 2,
                "code": item_code("genesis", side, piece_type),
                "name": item_name("Genesis", side, piece_type),
                "kind": "piece",
                "side": side,
                "piece_type": piece_type,
                "rarity": rarity,
                "value": RARITY_VALUES[rarity],
                "asset": {"type": "stub", "color": GENESIS_COLORS[side]},
                "is_upgrade_target": True,
            })
    # Доски Genesis (id 26, 27).
    item_defs.append({
        "id": 26,
        "set_id": 2,
        "collection_id": None,
        "code": "genesis-board-paper",
        "name": "Genesis | Бумага",
        "kind": "board",
        "side": None,
        "piece_type": None,
        "rarity": "uncommon",
        "value": 60,
        "asset": {"type": "stub", "light": "#ffffff", "dark": "#e5e5e5"},
        "is_upgrade_target": True,
    })
    item_defs.append({
        "id": 27,
        "set_id": 2,
        "collection_id": None,
        "code": "genesis-board-albion",
        "name": "Genesis | Альбион",
        "kind": "board",
        "side": None,
        "piece_type": None,
        "rarity": "mythic",
        "value": 5000,
        "asset": {"type": "stub", "light": "#ffffff", "dark": "#c9d1e0"},
        "is_upgrade_target": True,
    })
    cases = [
        {
            "id": 1,
            "code": "genesis",
            "name": "Genesis",
            "kind": "set",
            "set_id": 2,
            "collection_id": None,
            "price": 100,
            "status": "on_sale",
            "sort": 1,
            "stock_limit": None,
            "sold_count": 0,
            "sale_starts_at": None,
            "sale_ends_at": None,
        }
    ]
    # Дропы кейса — все скины Genesis (id 14–27).
    case_drops = [
        {"case_id": 1, "item_def_id": row["id"], "weight": GENESIS_WEIGHTS[row["rarity"]]}
        for row in item_defs
        if row["id"] >= 14
    ]
    daily_reward_pool = [{"case_id": 1, "weight": 1}]
    return {
        "item_sets": item_sets,
        "collections": collections,
        "item_defs": item_defs,
        "cases": cases,
        "case_drops": case_drops,
        "daily_reward_pool": daily_reward_pool,
    }
