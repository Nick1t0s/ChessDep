import pytest
from pydantic import ValidationError
from sqlalchemy import select, update

from app.db import SessionLocal
from app.models import InventoryItem, ItemDef, User
from app.schemas.items import SkinAsset, resolve_image
from app.seed_skins import seed_image_id
from app.services.items import loadout_snapshot


async def _def_id(code: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(ItemDef.id).where(ItemDef.code == code))


async def _user_id(login: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(User.id).where(User.login == login))


async def test_resolve_image() -> None:
    asset = {"type": "png", "image": "a" * 64}
    assert resolve_image(asset, "FN") == "a" * 64

    asset = {"type": "png", "image": "a" * 64, "exteriors": {"FN": "b" * 64}}
    assert resolve_image(asset, "FN") == "b" * 64
    assert resolve_image(asset, "MW") == "a" * 64


async def test_skin_asset_serialization() -> None:
    assert SkinAsset(type="png", image="a" * 64).model_dump() == {"type": "png", "image": "a" * 64}

    dumped = SkinAsset(type="png", image="a" * 64, exteriors={"BS": "b" * 64}).model_dump()
    assert "exteriors" in dumped
    assert dumped["exteriors"] == {"BS": "b" * 64}

    with pytest.raises(ValidationError):
        SkinAsset(type="png", image="a" * 64, exteriors={"XX": "a" * 64})


async def test_patch_exteriors(admin) -> None:
    resp = await admin.get("/api/v1/admin/item-defs")
    assert resp.status_code == 200, resp.text
    def_id = next(i["id"] for i in resp.json() if i["code"] == "genesis-wq")
    url = f"/api/v1/admin/item-defs/{def_id}"

    resp = await admin.patch(url, json={
        "asset": {
            "type": "png",
            "image": seed_image_id("genesis-wq"),
            "exteriors": {"BS": seed_image_id("base-wq")},
        },
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["asset"] == {
        "type": "png",
        "image": seed_image_id("genesis-wq"),
        "exteriors": {"BS": seed_image_id("base-wq")},
    }

    # Картинка доски для фигуры → 422.
    resp = await admin.patch(url, json={
        "asset": {
            "type": "png",
            "image": seed_image_id("genesis-wq"),
            "exteriors": {"BS": seed_image_id("base-board")},
        },
    })
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # Несуществующая картинка качества → 404.
    resp = await admin.patch(url, json={
        "asset": {
            "type": "png",
            "image": seed_image_id("genesis-wq"),
            "exteriors": {"BS": "f" * 64},
        },
    })
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "SKIN_IMAGE_NOT_FOUND"


async def test_item_image_by_exterior(admin, alice, db) -> None:
    def_id = await _def_id("genesis-wq")
    resp = await admin.patch(f"/api/v1/admin/item-defs/{def_id}", json={
        "asset": {
            "type": "png",
            "image": seed_image_id("genesis-wq"),
            "exteriors": {"BS": seed_image_id("base-wq")},
        },
    })
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
    resp = await admin.patch(f"/api/v1/admin/item-defs/{def_id}", json={
        "asset": {
            "type": "png",
            "image": seed_image_id("genesis-wq"),
            "exteriors": {"BS": seed_image_id("base-wq")},
        },
    })
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
