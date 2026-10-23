from sqlalchemy import select

from app.models import AdminAudit

SLOTS = [s + p for s in "wb" for p in "PNBRQK"]

_WINTER_CODES = [f"winter-{slot[0]}{slot[1].lower()}" for slot in SLOTS]
_GENESIS_CODES = [f"genesis-{slot[0]}{slot[1].lower()}" for slot in SLOTS]
_GENESIS_CODES += ["genesis-board-paper", "genesis-board-albion"]

_BOARD_ASSET = {"type": "stub", "light": "#f0f0f0", "dark": "#30304a"}


def pieces_body(rarity: str = "common", value: int = 20) -> list[dict]:
    return [
        {"side": s[0], "piece_type": s[1], "rarity": rarity, "value": value,
         "asset": {"type": "stub", "color": "#ffffff"}}
        for s in SLOTS
    ]


def board_body(code: str, name: str = "Winter Board") -> dict:
    return {
        "code": code, "name": name, "rarity": "uncommon", "value": 60,
        "asset": dict(_BOARD_ASSET),
    }


async def create_set(admin, code: str = "winter") -> dict:
    resp = await admin.post("/api/v1/admin/sets", json={
        "code": code, "name": "Winter", "description": ""})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def add_collection(admin, set_id: int, code: str = "winter") -> dict:
    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/collections", json={
        "code": code, "name": "Winter", "description": "", "pieces": pieces_body()})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def add_board(admin, set_id: int, code: str = "winter-board") -> dict:
    resp = await admin.post(
        f"/api/v1/admin/sets/{set_id}/boards", json=board_body(code))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_admin_required(client, alice) -> None:
    resp = await alice.get("/api/v1/admin/sets")
    assert resp.status_code == 403
    resp = await alice.post("/api/v1/admin/sets", json={
        "code": "winter", "name": "Winter", "description": ""})
    assert resp.status_code == 403


async def test_set_create_and_list(admin, client) -> None:
    body = await create_set(admin)
    assert body["status"] == "draft"
    assert body["is_base"] is False
    assert body["collections_count"] == 0
    assert body["boards_count"] == 0

    resp = await admin.post("/api/v1/admin/sets", json={
        "code": "winter", "name": "Другая зима", "description": ""})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SET_CODE_TAKEN"

    resp = await admin.get("/api/v1/admin/sets")
    assert resp.status_code == 200
    by_code = {s["code"]: s for s in resp.json()}
    assert set(by_code) == {"base", "genesis", "winter"}
    base = by_code["base"]
    assert base["is_base"] is True
    assert base["status"] == "released"
    assert by_code["genesis"]["is_base"] is False
    assert by_code["winter"]["is_base"] is False

    # Черновик не виден публично.
    resp = await client.get("/api/v1/sets/winter")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SET_NOT_FOUND"
    resp = await client.get("/api/v1/sets")
    assert resp.status_code == 200
    assert [s["code"] for s in resp.json()] == ["genesis"]


async def test_collection_in_set(admin, client) -> None:
    item_set = await create_set(admin)
    set_id = item_set["id"]
    detail = await add_collection(admin, set_id)

    collections = detail["collections"]
    assert len(collections) == 1
    items = collections[0]["items"]
    assert [i["code"] for i in items] == _WINTER_CODES
    assert items[0]["name"] == "Winter | Белая пешка"
    assert items[11]["name"] == "Winter | Чёрный король"
    for item in items:
        assert item["kind"] == "piece"
        assert item["set"] == {"code": "winter", "name": "Winter"}

    # 11 фигур → 422.
    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/collections", json={
        "code": "short", "name": "Winter", "description": "",
        "pieces": pieces_body()[:-1]})
    assert resp.status_code == 422

    # Повторный код коллекции → 409.
    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/collections", json={
        "code": "winter", "name": "Другая зима", "description": "",
        "pieces": pieces_body()})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "COLLECTION_CODE_TAKEN"


async def test_board_in_set(admin) -> None:
    item_set = await create_set(admin)
    set_id = item_set["id"]
    detail = await add_collection(admin, set_id)
    board = await add_board(admin, set_id, code="winter-board")
    assert board["kind"] == "board"
    assert board["side"] is None
    assert board["collection"] is None
    assert board["asset"] == _BOARD_ASSET
    assert board["set"] == {"code": "winter", "name": "Winter"}

    resp = await admin.get(f"/api/v1/admin/sets/{set_id}")
    assert resp.status_code == 200
    boards = resp.json()["boards"]
    assert len(boards) == 1
    assert boards[0]["code"] == "winter-board"
    piece_id = resp.json()["collections"][0]["items"][0]["id"]

    # asset с color вместо light/dark → 422.
    resp = await admin.post(
        f"/api/v1/admin/sets/{set_id}/boards",
        json={**board_body("winter-board-2"), "asset": {"type": "stub", "color": "#ffffff"}},
    )
    assert resp.status_code == 422

    resp = await admin.delete(f"/api/v1/admin/item-defs/{board['id']}")
    assert resp.status_code == 204

    # Скин фигуры удалить нельзя.
    resp = await admin.delete(f"/api/v1/admin/item-defs/{piece_id}")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_DEF_LOCKED"


async def test_release_and_retire(admin, client) -> None:
    item_set = await create_set(admin)
    set_id = item_set["id"]

    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/release")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SET_EMPTY"

    await add_collection(admin, set_id)
    await add_board(admin, set_id)

    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/release")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "released"

    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/release")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SET_NOT_DRAFT"

    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/collections", json={
        "code": "extra", "name": "Extra", "description": "", "pieces": pieces_body()})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SET_NOT_DRAFT"

    resp = await admin.post(
        f"/api/v1/admin/sets/{set_id}/boards", json=board_body("extra-board"))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SET_NOT_DRAFT"

    resp = await client.get("/api/v1/sets/winter")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["collections"]) == 1
    assert len(body["collections"][0]["items"]) == 12
    assert len(body["boards"]) == 1
    assert body["boards"][0]["code"] == "winter-board"

    resp = await client.get("/api/v1/sets")
    assert resp.status_code == 200
    winter = {s["code"]: s for s in resp.json()}["winter"]
    assert winter["collections_count"] == 1
    assert winter["boards_count"] == 1

    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/retire")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "retired"

    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/retire")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SET_NOT_RELEASED"


async def test_base_set_protected(admin, client) -> None:
    resp = await admin.post("/api/v1/admin/sets/1/retire")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SET_IS_BASE"

    resp = await admin.delete("/api/v1/admin/sets/1")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SET_IS_BASE"

    resp = await client.get("/api/v1/sets")
    assert resp.status_code == 200
    assert "base" not in [s["code"] for s in resp.json()]


async def test_item_def_patch(admin) -> None:
    item_set = await create_set(admin)
    set_id = item_set["id"]
    detail = await add_collection(admin, set_id)
    piece = detail["collections"][0]["items"][0]  # winter-wp
    piece_id = piece["id"]
    board = await add_board(admin, set_id)

    resp = await admin.patch(f"/api/v1/admin/item-defs/{piece_id}", json={
        "rarity": "mythic", "value": 999, "name": "X",
        "asset": {"type": "stub", "color": "#123456"},
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rarity"] == "mythic"
    assert body["value"] == 999
    assert body["name"] == "X"
    assert body["asset"] == {"type": "stub", "color": "#123456"}

    # Фигуре asset доски → 422.
    resp = await admin.patch(
        f"/api/v1/admin/item-defs/{piece_id}",
        json={"asset": {"type": "stub", "light": "#ffffff", "dark": "#e5e5e5"}},
    )
    assert resp.status_code == 422

    # Доске asset фигуры → 422.
    resp = await admin.patch(
        f"/api/v1/admin/item-defs/{board['id']}",
        json={"asset": {"type": "stub", "color": "#123456"}},
    )
    assert resp.status_code == 422

    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/release")
    assert resp.status_code == 200, resp.text

    resp = await admin.patch(
        f"/api/v1/admin/item-defs/{piece_id}", json={"rarity": "rare"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ITEM_DEF_LOCKED"

    resp = await admin.patch(
        f"/api/v1/admin/item-defs/{piece_id}", json={"value": 77})
    assert resp.status_code == 200, resp.text
    assert resp.json()["value"] == 77

    resp = await admin.patch(
        f"/api/v1/admin/item-defs/{piece_id}", json={"side": "b"})
    assert resp.status_code == 422


async def test_delete_draft_set(admin) -> None:
    item_set = await create_set(admin)
    set_id = item_set["id"]
    await add_collection(admin, set_id)

    resp = await admin.post("/api/v1/admin/cases", json={
        "code": "w-case", "name": "W", "price": 10, "kind": "set", "set_id": set_id})
    assert resp.status_code == 201, resp.text

    resp = await admin.delete(f"/api/v1/admin/sets/{set_id}")
    assert resp.status_code == 204

    resp = await admin.get("/api/v1/admin/cases")
    assert resp.status_code == 200
    assert "w-case" not in [c["code"] for c in resp.json()]

    # Выпущенный genesis нельзя удалить.
    resp = await admin.delete("/api/v1/admin/sets/2")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SET_NOT_DRAFT"


async def test_delete_collection(admin) -> None:
    item_set = await create_set(admin)
    set_id = item_set["id"]
    detail = await add_collection(admin, set_id)
    collection_id = detail["collections"][0]["id"]

    resp = await admin.delete(f"/api/v1/admin/collections/{collection_id}")
    assert resp.status_code == 204

    resp = await admin.get(f"/api/v1/admin/sets/{set_id}")
    assert resp.status_code == 200
    assert resp.json()["collections"] == []
    assert resp.json()["collections_count"] == 0

    # У выпущенного набора коллекцию удалить нельзя.
    detail = await add_collection(admin, set_id, code="summer")
    collection_id = detail["collections"][0]["id"]
    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/release")
    assert resp.status_code == 200, resp.text
    resp = await admin.delete(f"/api/v1/admin/collections/{collection_id}")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SET_NOT_DRAFT"


async def test_admin_item_defs_list(admin) -> None:
    resp = await admin.get("/api/v1/admin/item-defs")
    assert resp.status_code == 200
    codes = [i["code"] for i in resp.json()]
    assert codes == _GENESIS_CODES
    assert not any(c.startswith("base-") for c in codes)

    item_set = await create_set(admin)
    await add_collection(admin, item_set["id"])

    resp = await admin.get("/api/v1/admin/item-defs")
    codes = [i["code"] for i in resp.json()]
    assert len(codes) == 26
    assert codes[:14] == _GENESIS_CODES
    assert codes[14:] == _WINTER_CODES


async def test_audit(admin, db) -> None:
    item_set = await create_set(admin)
    set_id = item_set["id"]
    await add_collection(admin, set_id)
    await add_board(admin, set_id)
    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/release")
    assert resp.status_code == 200, resp.text

    audits = (await db.scalars(select(AdminAudit).order_by(AdminAudit.id))).all()
    assert [a.action for a in audits] == [
        "set.create",
        "collection.create",
        "board.create",
        "set.release",
    ]
