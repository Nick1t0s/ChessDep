import pytest
from pydantic import ValidationError
from sqlalchemy import select, update

from app.db import SessionLocal
from app.models import InventoryItem, ItemDef, User
from app.schemas.items import EXTERIORS, SkinAsset, resolve_image
from app.seed_skins import seed_asset, seed_image_id
from app.services.items import loadout_snapshot


async def _def_id(code: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(ItemDef.id).where(ItemDef.code == code))


async def _user_id(login: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(User.id).where(User.login == login))


async def test_resolve_image() -> None:
    asset = {"type": "png", "image": "a" * 64, "exteriors": {e: "b" * 64 for e in EXTERIORS} | {"BS": "c" * 64}}
    assert resolve_image(asset, "BS") == "c" * 64
    assert resolve_image(asset, "FN") == "b" * 64


async def test_skin_asset_requires_all_exteriors() -> None:
    with pytest.raises(ValidationError):
        SkinAsset(type="png", image="a" * 64)

    four = {e: "b" * 64 for e in EXTERIORS if e != "MW"}
    with pytest.raises(ValidationError):
        SkinAsset(type="png", image="a" * 64, exteriors=four)

    with pytest.raises(ValidationError):
        SkinAsset(type="png", image="a" * 64, exteriors={e: "b" * 64 for e in EXTERIORS} | {"XX": "a" * 64})

    dumped = SkinAsset(type="png", image="a" * 64, exteriors={e: "b" * 64 for e in EXTERIORS}).model_dump()
    assert len(dumped["exteriors"]) == 5


async def test_patch_exteriors(admin) -> None:
    resp = await admin.get("/api/v1/admin/item-defs")
    assert resp.status_code == 200, resp.text
    def_id = next(i["id"] for i in resp.json() if i["code"] == "genesis-wq")
    url = f"/api/v1/admin/item-defs/{def_id}"

    asset = seed_asset("genesis-wq")
    asset["exteriors"]["BS"] = seed_image_id("base-wq")
    resp = await admin.patch(url, json={"asset": asset})
    assert resp.status_code == 200, resp.text
    assert resp.json()["asset"]["exteriors"]["BS"] == seed_image_id("base-wq")
    assert resp.json()["asset"] == asset

    # Нет качества MW → 422.
    no_mw = seed_asset("genesis-wq")
    del no_mw["exteriors"]["MW"]
    resp = await admin.patch(url, json={"asset": no_mw})
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # Картинка доски для фигуры → 422.
    board_bs = seed_asset("genesis-wq")
    board_bs["exteriors"]["BS"] = seed_image_id("base-board")
    resp = await admin.patch(url, json={"asset": board_bs})
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # Несуществующая картинка качества → 404.
    missing_bs = seed_asset("genesis-wq")
    missing_bs["exteriors"]["BS"] = "f" * 64
    resp = await admin.patch(url, json={"asset": missing_bs})
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "SKIN_IMAGE_NOT_FOUND"


async def test_item_image_by_exterior(admin, alice, db) -> None:
    def_id = await _def_id("genesis-wq")
    asset = seed_asset("genesis-wq")
    asset["exteriors"]["BS"] = seed_image_id("base-wq")
    resp = await admin.patch(f"/api/v1/admin/item-defs/{def_id}", json={"asset": asset})
    assert resp.status_code == 200, resp.text

    alice_id = await _user_id("alice")
    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/grant-item", json={"item_def_id": def_id}
    )
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["id"]

    await db.execute(update(InventoryItem).where(InventoryItem.id == item_id).values(wear=0.5))
    await db.commit()

    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/grant-item", json={"case_id": 1}
    )
    assert resp.status_code == 200, resp.text
    case_item_id = resp.json()["id"]

    inv = (await alice.get("/api/v1/inventory")).json()
    entry = next(i for i in inv if i["id"] == item_id)
    assert entry["image"] == seed_image_id("base-wq")
    assert entry["exterior"] == "BS"

    base_entry = next(i for i in inv if i["def"] and i["def"]["code"] == "base-wq")
    assert base_entry["image"] == seed_image_id("base-wq")

    case_entry = next(i for i in inv if i["id"] == case_item_id)
    assert case_entry["image"] is None


async def test_snapshot_uses_item_image(admin, alice, db) -> None:
    def_id = await _def_id("genesis-wq")
    asset = seed_asset("genesis-wq")
    asset["exteriors"]["BS"] = seed_image_id("base-wq")
    resp = await admin.patch(f"/api/v1/admin/item-defs/{def_id}", json={"asset": asset})
    assert resp.status_code == 200, resp.text

    alice_id = await _user_id("alice")
    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/grant-item", json={"item_def_id": def_id}
    )
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["id"]

    await db.execute(update(InventoryItem).where(InventoryItem.id == item_id).values(wear=0.5))
    await db.commit()

    resp = await alice.put("/api/v1/loadout/wQ", json={"inventory_item_id": item_id})
    assert resp.status_code == 200, resp.text

    async with SessionLocal() as session:
        snapshot = await loadout_snapshot(session, alice_id, "w")
    assert snapshot["Q"]["asset"] == {"type": "png", "image": seed_image_id("base-wq")}


async def test_create_board_requires_exteriors(admin) -> None:
    resp = await admin.post("/api/v1/admin/sets", json={"code": "winter", "name": "Winter", "description": ""})
    assert resp.status_code == 201, resp.text
    set_id = resp.json()["id"]

    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/boards", json={
        "code": "winter-board-noext", "name": "Winter Board", "rarity": "uncommon", "value": 60,
        "asset": {"type": "png", "image": seed_image_id("base-board")},
    })
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_seed_assets_full(db) -> None:
    defs = (await db.scalars(select(ItemDef))).all()
    assert defs
    for item_def in defs:
        assert set(item_def.asset["exteriors"]) == set(EXTERIORS), item_def.code
