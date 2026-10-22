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


async def test_seed_genesis(client) -> None:
    resp = await client.get("/api/v1/collections")
    assert resp.status_code == 200
    data = resp.json()
    genesis = next(c for c in data if c["code"] == "genesis")
    assert genesis["items_count"] == 12
    assert genesis["status"] == "released"

    resp = await client.get("/api/v1/cases")
    assert resp.status_code == 200
    cases = resp.json()
    assert [c["code"] for c in cases] == ["genesis"]
    assert cases[0]["collections"] == [{"code": "genesis", "name": "Genesis"}]

    resp = await client.get("/api/v1/collections/genesis")
    assert resp.status_code == 200
    detail = resp.json()
    assert [item["code"] for item in detail["items"]] == CANONICAL_CODES
    asset_white = {"type": "stub", "color": "#ffffff"}
    asset_black = {"type": "stub", "color": "#ffc93c"}
    for item in detail["items"]:
        assert "kind" not in item
        assert item["asset"] == (asset_white if item["side"] == "w" else asset_black)


async def test_seed_weights_match_auto_formula(db) -> None:
    defs = {d.id: d for d in (await db.scalars(select(ItemDef))).all()}
    cases = {c.code: c.id for c in (await db.scalars(select(Case))).all()}
    assert list(cases) == ["genesis"]
    drops = (
        await db.scalars(select(CaseDrop).where(CaseDrop.case_id == cases["genesis"]))
    ).all()
    assert len(drops) == 12

    weights = {d.item_def_id: d.weight for d in drops}
    item_defs = [defs[item_def_id] for item_def_id in weights]
    assert weights == auto_weights(item_defs, dict(DEFAULTS["rarity_weights"]))
    assert sum(weights.values()) == 9_994_000


async def test_case_detail_chances(client) -> None:
    resp = await client.get("/api/v1/cases/1")
    assert resp.status_code == 200
    detail = resp.json()
    assert len(detail["drops"]) == 12
    assert abs(sum(d["chance"] for d in detail["drops"]) - 1.0) < 1e-9
    assert detail["collections"] == [{"code": "genesis", "name": "Genesis"}]
    legendary = next(d for d in detail["drops"] if d["def"]["code"] == "genesis-wk")
    assert legendary["chance"] == pytest.approx(10000 / 9994000)
    assert legendary["chance_text"] == format_chance(10000 / 9994000)


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
