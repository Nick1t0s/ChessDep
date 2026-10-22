"""Сид-данные коллекции Genesis: один источник для миграции и conftest.

Чистый модуль: без БД и I/O. Используют
- alembic/versions/0003_items.py (op.bulk_insert),
- tests/conftest.py (TRUNCATE + вставка перед каждым тестом).
"""
import app.core.clock as clock

# (буква, slug, имя)
PIECES: list[tuple[str, str, str]] = [
    ("P", "pawn", "Пешка"),
    ("N", "knight", "Конь"),
    ("B", "bishop", "Слон"),
    ("R", "rook", "Ладья"),
    ("Q", "queen", "Ферзь"),
    ("K", "king", "Король"),
]

# Варианты скинов фигур: (суффикс, название, редкость)
PIECE_VARIANTS: list[tuple[str, str, str]] = [
    ("chalk", "Мел", "common"),
    ("frost", "Иней", "rare"),
    ("snow", "Снег", "epic"),
]

# Варианты досок: (суффикс, название, редкость)
BOARD_VARIANTS: list[tuple[str, str, str]] = [
    ("paper", "Бумага", "common"),
    ("porcelain", "Фарфор", "uncommon"),
    ("marble", "Мрамор", "epic"),
    ("albion", "Альбион", "mythic"),
]

RARITY_VALUES: dict[str, int] = {
    "common": 20,
    "uncommon": 60,
    "rare": 150,
    "epic": 500,
    "legendary": 1500,
    "mythic": 5000,
}

# Веса дропов кейса «Genesis: фигуры» (результат auto_weights: common 7992*1000//6,
# rare 320*1000//6, epic 64*1000//6; сумма 8 375 994).
PIECE_CASE_WEIGHTS: dict[str, int] = {"chalk": 1332000, "frost": 53333, "snow": 10666}

# Веса дропов кейса «Genesis: доски» (rarity: у каждой по одной доске; сумма 9 660 000).
BOARD_WEIGHTS: dict[str, int] = {
    "paper": 7992000,
    "porcelain": 1598000,
    "marble": 64000,
    "albion": 6000,
}


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
    for letter, slug, piece_name in PIECES:
        for suffix, variant_name, rarity in PIECE_VARIANTS:
            item_id += 1
            item_defs.append({
                "id": item_id,
                "collection_id": 1,
                "code": f"genesis-{slug}-{suffix}",
                "name": f"{piece_name} | {variant_name}",
                "kind": "piece_skin",
                "piece_type": letter,
                "rarity": rarity,
                "value": RARITY_VALUES[rarity],
                "asset": {"type": "stub", "color": "#ffffff"},
                "is_upgrade_target": True,
            })
    for suffix, variant_name, rarity in BOARD_VARIANTS:
        item_id += 1
        item_defs.append({
            "id": item_id,
            "collection_id": 1,
            "code": f"genesis-board-{suffix}",
            "name": f"Доска | {variant_name}",
            "kind": "board_skin",
            "piece_type": None,
            "rarity": rarity,
            "value": RARITY_VALUES[rarity],
            "asset": {"type": "stub", "light": "#ffffff", "dark": "#e5e5e5"},
            "is_upgrade_target": True,
        })
    cases = [
        {
            "id": 1,
            "collection_id": 1,
            "code": "genesis-pieces",
            "name": "Genesis: фигуры",
            "price": 100,
            "is_active": True,
            "sort": 1,
        },
        {
            "id": 2,
            "collection_id": 1,
            "code": "genesis-boards",
            "name": "Genesis: доски",
            "price": 250,
            "is_active": True,
            "sort": 2,
        },
    ]
    case_drops: list[dict] = []
    for row in item_defs:
        suffix = row["code"].rsplit("-", 1)[1]
        if row["kind"] == "piece_skin":
            case_drops.append(
                {"case_id": 1, "item_def_id": row["id"], "weight": PIECE_CASE_WEIGHTS[suffix]}
            )
        else:
            case_drops.append(
                {"case_id": 2, "item_def_id": row["id"], "weight": BOARD_WEIGHTS[suffix]}
            )
    return {
        "collections": collections,
        "item_defs": item_defs,
        "cases": cases,
        "case_drops": case_drops,
    }
