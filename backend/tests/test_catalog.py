import pytest
from sqlalchemy import select

from app.chess_engine import format_chance
from app.models import Case, CaseDrop, ItemDef
from app.schemas.items import exterior
from app.services.cases import auto_weights
from app.services.settings import DEFAULTS

CANONICAL_CODES = [
    "genesis-wp",
    "genesis-wn",
    "genesis-wb",
    "genesis-wr",
    "genesis-wq",
    "genesis-wk",
    "genesis-bp",
    "genesis-bn",
    "genesis-bb",
    "genesis-br",
    "genesis-bq",
    "genesis-bk",
]

BOARD_CODES = ["genesis-board-paper", "genesis-board-albion"]
DROP_IDS = list(range(14, 28))


async def test_seed_sets(client) -> None:
    resp = await client.get("/api/v1/sets")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    genesis = data[0]
    assert genesis["code"] == "genesis"
    assert genesis["name"] == "Genesis"
    assert genesis["status"] == "released"
    assert genesis["collections_count"] == 1
    assert genesis["boards_count"] == 2

    resp = await client.get("/api/v1/sets/genesis")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["code"] == "genesis"
    assert detail["name"] == "Genesis"
    assert detail["status"] == "released"
    assert len(detail["collections"]) == 1
    collection = detail["collections"][0]
    assert collection["code"] == "genesis"
    assert collection["name"] == "Genesis"
    assert [item["code"] for item in collection["items"]] == CANONICAL_CODES
    asset_white = {"type": "stub", "color": "#ffffff"}
    asset_black = {"type": "stub", "color": "#ffc93c"}
    for item in collection["items"]:
        assert item["kind"] == "piece"
        assert item["set"] == {"code": "genesis", "name": "Genesis"}
        assert item["collection"] == {"code": "genesis", "name": "Genesis"}
        assert item["asset"] == (asset_white if item["side"] == "w" else asset_black)
    boards = detail["boards"]
    assert [board["code"] for board in boards] == BOARD_CODES
    for board in boards:
        assert board["kind"] == "board"
        assert board["side"] is None
        assert board["piece_type"] is None
        assert board["collection"] is None
        assert board["set"] == {"code": "genesis", "name": "Genesis"}
    assert boards[1]["rarity"] == "mythic"
    assert boards[1]["value"] == 5000

    resp = await client.get("/api/v1/sets/base")
    assert resp.status_code == 200
    base = resp.json()
    assert base["code"] == "base"
    assert base["name"] == "Базовый"
    assert base["status"] == "released"
    assert len(base["collections"]) == 1
    assert [item["code"] for item in base["collections"][0]["items"]] == [
        f"base-{slot[0]}{slot[1].lower()}" for slot in
        ("wP", "wN", "wB", "wR", "wQ", "wK", "bP", "bN", "bB", "bR", "bQ", "bK")
    ]
    assert [board["code"] for board in base["boards"]] == ["base-board"]

    resp = await client.get("/api/v1/collections/genesis")
    assert resp.status_code == 200
    collection_detail = resp.json()
    assert collection_detail["set"] == {"code": "genesis", "name": "Genesis"}
    assert [item["code"] for item in collection_detail["items"]] == CANONICAL_CODES


async def test_seed_weights_match_auto_formula(db) -> None:
    defs = {d.id: d for d in (await db.scalars(select(ItemDef))).all()}
    cases = {c.code: c.id for c in (await db.scalars(select(Case))).all()}
    assert list(cases) == ["genesis"]
    drops = (
        await db.scalars(select(CaseDrop).where(CaseDrop.case_id == cases["genesis"]))
    ).all()
    assert len(drops) == 14

    weights = {d.item_def_id: d.weight for d in drops}
    item_defs = [defs[item_def_id] for item_def_id in weights]
    assert set(weights) == set(DROP_IDS)
    assert weights == auto_weights(item_defs, dict(DEFAULTS["rarity_weights"]))
    assert sum(weights.values()) == 10_000_000


async def test_case_detail_chances(client) -> None:
    resp = await client.get("/api/v1/cases/1")
    assert resp.status_code == 200
    detail = resp.json()
    assert len(detail["drops"]) == 14
    assert abs(sum(d["chance"] for d in detail["drops"]) - 1.0) < 1e-9
    assert detail["kind"] == "set"
    assert detail["set"] == {"code": "genesis", "name": "Genesis"}
    assert detail["on_sale_now"] is True
    albion_chance = 6000 / 10_000_000
    albion = next(d for d in detail["drops"] if d["def"]["code"] == "genesis-board-albion")
    assert albion["chance"] == pytest.approx(albion_chance)
    assert albion["chance_text"] == format_chance(albion_chance)
    assert albion["def"]["kind"] == "board"
    legendary_chance = 10_000 / 10_000_000
    legendary = next(d for d in detail["drops"] if d["def"]["code"] == "genesis-wk")
    assert legendary["chance"] == pytest.approx(legendary_chance)
    assert legendary["chance_text"] == format_chance(legendary_chance)


def test_exterior_boundaries() -> None:
    expectations = [
        (0.0, "FN"),
        (0.0699, "FN"),
        (0.07, "MW"),
        (0.15, "FT"),
        (0.38, "WW"),
        (0.45, "BS"),
        (0.9999, "BS"),
    ]
    for wear, expected in expectations:
        assert exterior(wear) == expected
