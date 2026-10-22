from sqlalchemy import select

from app.models import AdminAudit, ItemDef, User

SLOTS = [s + p for s in "wb" for p in "PNBRQK"]

_GENESIS_CODES = [f"genesis-{slot[0]}{slot[1].lower()}" for slot in SLOTS]
_WINTER_CODES = [f"winter-{slot[0]}{slot[1].lower()}" for slot in SLOTS]


def pieces_body(rarity: str = "common", value: int = 20) -> list[dict]:
    return [
        {"side": s[0], "piece_type": s[1], "rarity": rarity, "value": value,
         "asset": {"type": "stub", "color": "#ffffff"}}
        for s in SLOTS
    ]


async def create_collection(admin, code: str = "winter", name: str = "Winter") -> dict:
    resp = await admin.post("/api/v1/admin/collections", json={
        "code": code, "name": name, "description": "", "pieces": pieces_body()})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_admin_required(client, alice) -> None:
    resp = await client.get("/api/v1/admin/collections")
    assert resp.status_code == 401
    resp = await alice.get("/api/v1/admin/collections")
    assert resp.status_code == 403


async def test_collection_create_shape(admin, client) -> None:
    body = await create_collection(admin)
    assert body["status"] == "draft"
    assert body["items_count"] == 12

    items = body["items"]
    assert len(items) == 12
    assert [i["code"] for i in items] == [
        "winter-wp", "winter-wn", "winter-wb", "winter-wr", "winter-wq", "winter-wk",
        "winter-bp", "winter-bn", "winter-bb", "winter-br", "winter-bq", "winter-bk",
    ]
    assert items[0]["name"] == "Winter | Белая пешка"
    assert items[11]["name"] == "Winter | Чёрный король"
    for item in items:
        code = item["code"]
        assert code == f"winter-{item['side']}{item['piece_type'].lower()}"

    resp = await admin.post("/api/v1/admin/collections", json={
        "code": "winter", "name": "Другая зима", "description": "", "pieces": pieces_body()})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "COLLECTION_CODE_TAKEN"

    resp = await client.get("/api/v1/collections/winter")
    assert resp.status_code == 404


async def test_collection_create_validation(admin) -> None:
    base = {"code": "winter", "name": "Winter", "description": ""}

    resp = await admin.post(
        "/api/v1/admin/collections", json={**base, "pieces": pieces_body()[:-1]}
    )
    assert resp.status_code == 422

    dup = pieces_body()
    dup[0]["piece_type"] = "K"
    resp = await admin.post("/api/v1/admin/collections", json={**base, "pieces": dup})
    assert resp.status_code == 422

    resp = await admin.post(
        "/api/v1/admin/collections", json={**base, "pieces": pieces_body(rarity="bogus")}
    )
    assert resp.status_code == 422

    bad_asset = pieces_body()
    bad_asset[0]["asset"] = {"type": "stub", "light": "#fff", "dark": "#000"}
    resp = await admin.post("/api/v1/admin/collections", json={**base, "pieces": bad_asset})
    assert resp.status_code == 422


async def test_collection_lifecycle(admin, db) -> None:
    collection = await create_collection(admin)
    collection_id = collection["id"]

    resp = await admin.post(
        "/api/v1/admin/cases", json={"code": "winter-case", "name": "Winter", "price": 50}
    )
    assert resp.status_code == 201, resp.text
    case = resp.json()
    assert case["status"] == "draft"
    assert case["drops"] == []
    assert case["collections"] == []
    case_id = case["id"]

    resp = await admin.post(
        f"/api/v1/admin/cases/{case_id}/drops/auto",
        json={"collection_ids": [collection_id]},
    )
    assert resp.status_code == 200, resp.text
    drops = resp.json()["drops"]
    assert len(drops) == 12
    assert resp.json()["collections"] == [{"code": "winter", "name": "Winter"}]

    # Активация с черновой коллекцией невозможна.
    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/activate")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_NOT_READY"

    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/release")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "released"

    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/release")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "COLLECTION_NOT_DRAFT"

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/activate")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/activate")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_NOT_READY"

    resp = await admin.get("/api/v1/cases")
    assert resp.status_code == 200
    by_code = {c["code"]: c for c in resp.json()}
    assert by_code["winter-case"]["collections"] == [{"code": "winter", "name": "Winter"}]

    resp = await admin.put(
        f"/api/v1/admin/cases/{case_id}/drops", json=[{"item_def_id": 1, "weight": 5}]
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_LOCKED"

    resp = await admin.delete(f"/api/v1/admin/cases/{case_id}")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_LOCKED"

    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/retire")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "retired"

    resp = await admin.get("/api/v1/admin/cases")
    admin_cases = {c["id"]: c for c in resp.json()}
    assert admin_cases[case_id]["status"] == "closed"

    audits = (await db.scalars(select(AdminAudit).order_by(AdminAudit.id))).all()
    retire_audit = [a for a in audits if a.action == "collection.retire"][-1]
    assert retire_audit.payload == {"closed_case_ids": [case_id]}

    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/retire")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "COLLECTION_NOT_RELEASED"

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/activate")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_NOT_READY"


async def test_mixed_case(admin) -> None:
    winter = await create_collection(admin)
    summer = await create_collection(admin, code="summer", name="Summer")
    winter_id, summer_id = winter["id"], summer["id"]
    assert winter_id < summer_id
    first_winter_skin_id = winter["items"][0]["id"]

    for coll_id in (winter_id, summer_id):
        resp = await admin.post(f"/api/v1/admin/collections/{coll_id}/release")
        assert resp.status_code == 200, resp.text

    resp = await admin.post(
        "/api/v1/admin/cases", json={"code": "mixed-case", "name": "Mixed", "price": 50}
    )
    assert resp.status_code == 201, resp.text
    case_id = resp.json()["id"]

    resp = await admin.post(
        f"/api/v1/admin/cases/{case_id}/drops/auto",
        json={"collection_ids": [winter_id, summer_id]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["drops"]) == 24
    assert body["collections"] == [
        {"code": "winter", "name": "Winter"},
        {"code": "summer", "name": "Summer"},
    ]

    resp = await admin.post(
        f"/api/v1/admin/cases/{case_id}/drops/auto", json={"collection_ids": [1, 1]}
    )
    assert resp.status_code == 422

    resp = await admin.post(
        f"/api/v1/admin/cases/{case_id}/drops/auto", json={"collection_ids": [999]}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "COLLECTION_NOT_FOUND"

    resp = await admin.put(
        f"/api/v1/admin/cases/{case_id}/drops",
        json=[
            {"item_def_id": 1, "weight": 5},
            {"item_def_id": first_winter_skin_id, "weight": 5},
        ],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["drops"] == [
        {"item_def_id": 1, "weight": 5},
        {"item_def_id": first_winter_skin_id, "weight": 5},
    ]
    assert body["collections"] == [
        {"code": "genesis", "name": "Genesis"},
        {"code": "winter", "name": "Winter"},
    ]

    resp = await admin.put(
        f"/api/v1/admin/cases/{case_id}/drops", json=[{"item_def_id": 99999, "weight": 1}]
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DROP_ITEM_NOT_AVAILABLE"

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/activate")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/close")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "closed"

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/close")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CASE_NOT_ACTIVE"

    resp = await admin.post(f"/api/v1/admin/cases/{case_id}/activate")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"


async def test_retired_collection_not_droppable(admin) -> None:
    collection = await create_collection(admin)
    collection_id = collection["id"]
    skin_id = collection["items"][0]["id"]

    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/release")
    assert resp.status_code == 200, resp.text
    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/retire")
    assert resp.status_code == 200, resp.text

    resp = await admin.post(
        "/api/v1/admin/cases", json={"code": "retired-case", "name": "X", "price": 50}
    )
    assert resp.status_code == 201, resp.text
    case_id = resp.json()["id"]

    resp = await admin.post(
        f"/api/v1/admin/cases/{case_id}/drops/auto",
        json={"collection_ids": [collection_id]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DROP_ITEM_NOT_AVAILABLE"

    resp = await admin.put(
        f"/api/v1/admin/cases/{case_id}/drops",
        json=[{"item_def_id": skin_id, "weight": 5}],
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DROP_ITEM_NOT_AVAILABLE"


async def test_item_def_patch(admin, db) -> None:
    collection = await create_collection(admin)
    collection_id = collection["id"]
    skin_id = collection["items"][0]["id"]

    resp = await admin.patch(
        f"/api/v1/admin/item-defs/{skin_id}",
        json={
            "rarity": "mythic",
            "value": 999,
            "name": "X",
            "asset": {"type": "stub", "color": "#123456"},
            "is_upgrade_target": False,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rarity"] == "mythic"
    assert body["value"] == 999
    assert body["name"] == "X"
    assert body["asset"] == {"type": "stub", "color": "#123456"}
    item_def = await db.get(ItemDef, skin_id)
    assert item_def.is_upgrade_target is False

    resp = await admin.patch(f"/api/v1/admin/item-defs/{skin_id}", json={"side": "b"})
    assert resp.status_code == 422

    resp = await admin.patch(f"/api/v1/admin/item-defs/{skin_id}", json={"piece_type": "Q"})
    assert resp.status_code == 422

    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/release")
    assert resp.status_code == 200, resp.text

    resp = await admin.patch(f"/api/v1/admin/item-defs/{skin_id}", json={"rarity": "rare"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_DEF_LOCKED"

    resp = await admin.patch(
        f"/api/v1/admin/item-defs/{skin_id}", json={"value": 77, "name": "Y"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["value"] == 77

    # Удалённые эндпоинты.
    resp = await admin.post(
        f"/api/v1/admin/collections/{collection_id}/items", json=pieces_body()[0]
    )
    assert resp.status_code in (404, 405)

    resp = await admin.delete(f"/api/v1/admin/item-defs/{skin_id}")
    assert resp.status_code == 405


async def test_delete_draft_collection(admin) -> None:
    collection = await create_collection(admin)
    collection_id = collection["id"]

    resp = await admin.post(
        "/api/v1/admin/cases", json={"code": "winter-case", "name": "Winter", "price": 50}
    )
    assert resp.status_code == 201, resp.text
    case_id = resp.json()["id"]

    resp = await admin.post(
        f"/api/v1/admin/cases/{case_id}/drops/auto",
        json={"collection_ids": [collection_id]},
    )
    assert resp.status_code == 200, resp.text

    resp = await admin.delete(f"/api/v1/admin/collections/{collection_id}")
    assert resp.status_code == 204

    resp = await admin.get("/api/v1/admin/cases")
    case = {c["id"]: c for c in resp.json()}[case_id]
    assert case["drops"] == []
    assert case["collections"] == []

    resp = await admin.delete("/api/v1/admin/collections/1")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "COLLECTION_NOT_DRAFT"


async def test_admin_lists(admin) -> None:
    collection = await create_collection(admin)
    collection_id = collection["id"]

    resp = await admin.get("/api/v1/admin/item-defs")
    codes = [i["code"] for i in resp.json()]
    assert codes == _GENESIS_CODES + _WINTER_CODES

    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/release")
    assert resp.status_code == 200, resp.text
    resp = await admin.post(f"/api/v1/admin/collections/{collection_id}/retire")
    assert resp.status_code == 200, resp.text

    resp = await admin.get("/api/v1/admin/item-defs")
    assert [i["code"] for i in resp.json()] == _GENESIS_CODES

    resp = await admin.get("/api/v1/admin/cases")
    data = resp.json()
    assert data[0]["code"] == "genesis"
    assert data[0]["status"] == "active"
    assert len(data[0]["drops"]) == 12


async def test_grant_item_and_audit(admin, alice, db) -> None:
    alice_id = (await db.scalars(select(User).where(User.login == "alice"))).one().id
    admin_id = (await db.scalars(select(User).where(User.login == "admin"))).one().id

    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/grant-item", json={"item_def_id": 1}
    )
    assert resp.status_code == 200, resp.text
    granted = resp.json()
    assert granted["source"] == "admin_grant"
    assert granted["def"]["code"] == "genesis-wp"

    collection = await create_collection(admin)
    draft_skin = collection["items"][5]  # winter-wq: Winter | Белый ферзь

    # Выдача скина из черновой коллекции → ITEM_DEF_NOT_AVAILABLE, без аудита.
    resp = await admin.post(
        f"/api/v1/admin/users/{alice_id}/grant-item",
        json={"item_def_id": draft_skin["id"]},
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
    ]
    assert all(a.admin_id == admin_id for a in audits)
