from sqlalchemy import select

from app.models import Case, CaseDrop, ItemDef
from app.schemas.items import exterior
from app.services.cases import auto_weights
from app.services.settings import DEFAULTS


async def test_seed_genesis(client) -> None:
    resp = await client.get("/api/v1/collections")
    assert resp.status_code == 200
    data = resp.json()
    genesis = next(c for c in data if c["code"] == "genesis")
    assert genesis["items_count"] == 22
    assert genesis["status"] == "released"

    resp = await client.get("/api/v1/cases")
    assert resp.status_code == 200
    assert [c["code"] for c in resp.json()] == ["genesis-pieces", "genesis-boards"]

    resp = await client.get("/api/v1/collections/genesis")
    assert resp.status_code == 200
    detail = resp.json()
    asset_piece = {"type": "stub", "color": "#ffffff"}
    asset_board = {"type": "stub", "light": "#ffffff", "dark": "#e5e5e5"}
    for item in detail["items"]:
        assert item["asset"] == (asset_piece if item["kind"] == "piece_skin" else asset_board)


async def test_seed_weights_match_auto_formula(db) -> None:
    defs = {d.id: d for d in (await db.scalars(select(ItemDef))).all()}
    case_ids = {c.code: c.id for c in (await db.scalars(select(Case))).all()}
    drops = (await db.scalars(select(CaseDrop))).all()
    by_case: dict[int, list[CaseDrop]] = {}
    for drop in drops:
        by_case.setdefault(drop.case_id, []).append(drop)

    for code, total in (("genesis-pieces", 8_375_994), ("genesis-boards", 9_660_000)):
        case_drops = by_case[case_ids[code]]
        weights = {d.item_def_id: d.weight for d in case_drops}
        item_defs = [defs[item_def_id] for item_def_id in weights]
        assert weights == auto_weights(item_defs, dict(DEFAULTS["rarity_weights"]))
        assert sum(weights.values()) == total


async def test_case_detail_chances(client) -> None:
    resp = await client.get("/api/v1/cases/2")
    assert resp.status_code == 200
    detail = resp.json()
    assert len(detail["drops"]) == 4
    assert abs(sum(d["chance"] for d in detail["drops"]) - 1.0) < 1e-9
    mythic = next(d for d in detail["drops"] if d["def"]["rarity"] == "mythic")
    assert mythic["chance_text"] == "0.06%"


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
