from sqlalchemy import select

from tests.conftest import SessionLocal, give_items
from app.models import AdminAudit, User

_WINTER_COLLECTION = {
    "code": "winter",
    "name": "Winter",
    "description": "Зимняя коллекция",
}

_WINTER_SKIN = {
    "code": "winter-queen-snow",
    "name": "Зимний ферзь",
    "kind": "piece_skin",
    "piece_type": "Q",
    "rarity": "epic",
    "value": 500,
    "asset": {"type": "stub", "color": "#ffffff"},
}


async def test_admin_required(client, alice) -> None:
    resp = await client.get("/api/v1/admin/collections")
    assert resp.status_code == 401
    resp = await alice.get("/api/v1/admin/collections")
    assert resp.status_code == 403


async def test_collection_lifecycle(admin, rng) -> None:
    rng.values = [0.0]
    resp = await admin.post("/api/v1/admin/collections", json=_WINTER_COLLECTION)
    assert resp.status_code == 201, resp.text
    collection_id = resp.json()["id"]

    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/items", json=_WINTER_SKIN
    )
    assert resp.status_code == 201, resp.text
    skin_id = resp.json()["id"]

    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/cases",
        json={"code": "winter-case", "name": "Winter: кейс", "price": 120, "sort": 0},
    )
    assert resp.status_code == 201, resp.text
    case_id = resp.json()["id"]

    # Релиз без дропов → COLLECTION_NOT_READY.
    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/release")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "COLLECTION_NOT_READY"

    resp = await admin.post(
        f"/api/v1/admin/cases/{case_id}/drops/auto", json={"kind": "piece_skin"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["drops"] == [{"item_def_id": skin_id, "weight": 64_000}]

    # Ретирать можно только выпущенные.
    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/retire")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "COLLECTION_NOT_RELEASED"

    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/release")
    assert resp.status_code == 200, resp.text

    # После релиза кейс виден публично первым (released_at свежее).
    resp = await admin.get("/api/v1/cases")
    assert resp.status_code == 200
    assert [c["code"] for c in resp.json()] == [
        "winter-case",
        "genesis-pieces",
        "genesis-boards",
    ]

    # Открытие кейса.
    resp = await admin.post(f"/api/v1/cases/{case_id}/open")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["balance"] == 880
    assert body["item"]["def"]["code"] == "winter-queen-snow"
    assert body["item"]["def"]["id"] == skin_id
    assert body["win_index"] == 45
    assert len(body["strip"]) == 60

    # Снятая коллекция скрывается из списков, её кейс недоступен.
    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/retire")
    assert resp.status_code == 200, resp.text
    resp = await admin.get("/api/v1/cases")
    assert [c["code"] for c in resp.json()] == ["genesis-pieces", "genesis-boards"]
    resp = await admin.get("/api/v1/collections")
    data = resp.json()
    assert [c["code"] for c in data] == ["winter", "genesis"]
    assert data[0]["status"] == "retired"
    resp = await admin.get("/api/v1/item-defs?upgrade_target=true")
    codes = [i["code"] for i in resp.json()]
    assert len(codes) == 22
    assert "winter-queen-snow" not in codes

    # Открытый предмет сохранился, им можно экипироваться.
    resp = await admin.get("/api/v1/inventory")
    inv = resp.json()
    assert [i["id"] for i in inv] == [body["item"]["id"]]
    resp = await admin.put(
        "/api/v1/loadout/Q", json={"inventory_item_id": body["item"]["id"]}
    )
    assert resp.status_code == 200, resp.text

    # Повторный релиз невозможен.
    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/release")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "COLLECTION_NOT_DRAFT"


async def test_item_def_validation(admin, db) -> None:
    resp = await admin.post("/api/v1/admin/collections", json=_WINTER_COLLECTION)
    assert resp.status_code == 201, resp.text
    collection_id = resp.json()["id"]

    # piece_skin с бордовым asset.
    bad_asset = dict(_WINTER_SKIN, asset={"type": "stub", "light": "#fff", "dark": "#000"})
    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/items", json=bad_asset
    )
    assert resp.status_code == 422

    # board_skin с piece_type.
    bad_board = {
        "code": "winter-board",
        "name": "Зимняя доска",
        "kind": "board_skin",
        "piece_type": "P",
        "rarity": "common",
        "value": 20,
        "asset": {"type": "stub", "light": "#fff", "dark": "#000"},
    }
    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/items", json=bad_board
    )
    assert resp.status_code == 422

    # piece_skin без piece_type.
    no_type = {k: v for k, v in _WINTER_SKIN.items() if k != "piece_type"}
    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/items", json=no_type
    )
    assert resp.status_code == 422

    # Некорректный rarity.
    bad_rarity = dict(_WINTER_SKIN, rarity="gold")
    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/items", json=bad_rarity
    )
    assert resp.status_code == 422

    # Повтор кода (genesis) → 409.
    dup = dict(_WINTER_SKIN, code="genesis-pawn-chalk")
    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/items", json=dup
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ITEM_CODE_TAKEN"

    # Скин можно удалить из черновика.
    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/items", json=_WINTER_SKIN
    )
    assert resp.status_code == 201, resp.text
    skin_id = resp.json()["id"]
    resp = await admin.delete(f"/api/v1/admin/item-defs/{skin_id}")
    assert resp.status_code == 204
    resp = await admin.get(f"/api/v1/admin/collections/{collection_id}")
    assert resp.status_code == 200
    assert [i["code"] for i in resp.json()["items"]] == []


async def test_item_def_locked_after_release(admin) -> None:
    # PATCH разрешённых полей + видимость в публичной ручке.
    resp = await admin.patch(
        "/api/v1/admin/item-defs/1",
        json={"name": "Пешка | Мел", "value": 25},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["value"] == 25

    resp = await admin.patch(
        "/api/v1/admin/item-defs/1",
        json={"asset": {"type": "stub", "color": "#cccccc"}},
    )
    assert resp.status_code == 200, resp.text
    resp = await admin.get("/api/v1/collections/genesis")
    detail = resp.json()
    pawn = next(i for i in detail["items"] if i["code"] == "genesis-pawn-chalk")
    assert pawn["asset"] == {"type": "stub", "color": "#cccccc"}
    assert pawn["value"] == 25

    # PATCH заблокированных полей → ITEM_DEF_LOCKED.
    resp = await admin.patch(
        "/api/v1/admin/item-defs/2", json={"rarity": "mythic"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_DEF_LOCKED"

    resp = await admin.patch("/api/v1/admin/item-defs/2", json={"kind": "board_skin"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_DEF_LOCKED"

    # DELETE скина из выпущенной коллекции → ITEM_DEF_LOCKED.
    resp = await admin.delete("/api/v1/admin/item-defs/2")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_DEF_LOCKED"

    # PATCH asset/kind несовместимого вида → 422.
    resp = await admin.patch(
        "/api/v1/admin/item-defs/1",
        json={"asset": {"type": "stub", "light": "#fff", "dark": "#000"}},
    )
    assert resp.status_code == 422

    # PATCH asset у board_skin (совпадает по виду) — ок.
    resp = await admin.patch(
        "/api/v1/admin/item-defs/19",
        json={"asset": {"type": "stub", "light": "#ffffff", "dark": "#e5e5e5"}},
    )
    assert resp.status_code == 200


async def test_drops_validation(admin) -> None:
    resp = await admin.post("/api/v1/admin/collections", json=_WINTER_COLLECTION)
    assert resp.status_code == 201, resp.text
    collection_id = resp.json()["id"]
    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/items", json=_WINTER_SKIN
    )
    assert resp.status_code == 201, resp.text
    skin_id = resp.json()["id"]
    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/cases",
        json={"code": "winter-case", "name": "Winter: кейс", "price": 100, "sort": 0},
    )
    assert resp.status_code == 201, resp.text
    case_id = resp.json()["id"]

    # Дроп со скином другой коллекции.
    resp = await admin.put(
        f"/api/v1/admin/cases/{case_id}/drops", json=[{"item_def_id": 1, "weight": 10}]
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DROP_ITEM_NOT_IN_COLLECTION"

    # Повтор item_def_id → 422.
    resp = await admin.put(
        f"/api/v1/admin/cases/{case_id}/drops",
        json=[
            {"item_def_id": skin_id, "weight": 10},
            {"item_def_id": skin_id, "weight": 20},
        ],
    )
    assert resp.status_code == 422

    # weight: 0 → 422.
    resp = await admin.put(
        f"/api/v1/admin/cases/{case_id}/drops", json=[{"item_def_id": skin_id, "weight": 0}]
    )
    assert resp.status_code == 422

    # Дропы кейса выпущенной коллекции менять нельзя.
    resp = await admin.put(
        "/api/v1/admin/cases/1/drops", json=[{"item_def_id": 1, "weight": 10}]
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_LOCKED"

    resp = await admin.post("/api/v1/admin/cases/1/drops/auto")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_LOCKED"

    # Ручная установка дропов в черновике работает.
    resp = await admin.put(
        f"/api/v1/admin/cases/{case_id}/drops", json=[{"item_def_id": skin_id, "weight": 5}]
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["drops"] == [{"item_def_id": skin_id, "weight": 5}]


async def test_grant_item_and_audit(admin, alice, db) -> None:
    alice_id = (await db.scalars(select(User).where(User.login == "alice"))).one().id
    admin_id = (await db.scalars(select(User).where(User.login == "admin"))).one().id

    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/grant-item", json={"item_def_id": 1}
    )
    assert resp.status_code == 200, resp.text
    granted = resp.json()
    assert granted["source"] == "admin_grant"
    assert granted["def"]["code"] == "genesis-pawn-chalk"

    resp = await admin.post("/api/v1/admin/collections", json=_WINTER_COLLECTION)
    assert resp.status_code == 201, resp.text
    collection_id = resp.json()["id"]
    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/items", json=_WINTER_SKIN
    )
    assert resp.status_code == 201, resp.text
    draft_skin_id = resp.json()["id"]

    # Выдача скина из черновой коллекции → ITEM_DEF_NOT_AVAILABLE, без аудита.
    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/grant-item", json={"item_def_id": draft_skin_id}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_DEF_NOT_AVAILABLE"

    # Несуществующий пользователь → 404, без аудита.
    resp = await admin.post("/api/v1/admin/users/999999/grant-item", json={"item_def_id": 1})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "USER_NOT_FOUND"

    audits = (await db.scalars(select(AdminAudit).order_by(AdminAudit.id))).all()
    assert [a.action for a in audits] == [
        "user.grant_item",
        "collection.create",
        "item_def.create",
    ]
    assert all(a.admin_id == admin_id for a in audits)
