import io

from PIL import Image
from sqlalchemy import select

from app.models import AdminAudit
from app.schemas.items import EXTERIORS
from app.seed_skins import seed_asset, seed_image_id
from tests.conftest import anonymous


def _png(size, mode="RGBA", color=(0, 0, 0, 0)) -> bytes:
    img = Image.new(mode, size, color)
    if mode == "RGBA" and size == (128, 128):
        img.putpixel((64, 64), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _upload(client, kind, data, content_type="image/png"):
    return await client.post(
        f"/api/v1/admin/skin-images?kind={kind}",
        content=data,
        headers={"Content-Type": content_type},
    )


def _set_body(code: str = "winter") -> dict:
    return {"code": code, "name": "Winter", "description": ""}


def _board_body(code: str, asset: dict) -> dict:
    return {
        "code": code,
        "name": "Winter Board",
        "rarity": "uncommon",
        "value": 60,
        "asset": asset,
    }


async def test_upload_piece_and_get(admin, db) -> None:
    resp = await _upload(admin, "piece", _png((128, 128)))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == {"image", "kind", "url"}
    image = body["image"]
    assert body["kind"] == "piece"
    assert len(image) == 64
    assert body["url"] == f"/api/v1/skins/{image}.png"

    async with anonymous() as anon:
        resp = await anon.get(body["url"])
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert Image.open(io.BytesIO(resp.content)).size == (128, 128)

    audits = (
        await db.scalars(select(AdminAudit).where(AdminAudit.action == "skin_image.upload"))
    ).all()
    assert [a.target for a in audits] == [f"skin_image:{image}"]


async def test_upload_same_twice(admin) -> None:
    data = _png((128, 128))
    first = await _upload(admin, "piece", data)
    second = await _upload(admin, "piece", data)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["image"] == second.json()["image"]


async def test_upload_board(admin) -> None:
    resp = await _upload(admin, "board", _png((1088, 1088), "RGB", (1, 2, 3)))
    assert resp.status_code == 201, resp.text
    assert resp.json()["kind"] == "board"


async def test_upload_errors(admin) -> None:
    cases = [
        (b"not a png", "piece", "image/png", "Нужен файл PNG"),
        (_png((128, 128)), "piece", "image/jpeg", "Нужен файл PNG"),
        (_png((64, 64)), "piece", "image/png", "Фигура должна быть PNG 128×128"),
        (_png((128, 128)), "board", "image/png", "Доска должна быть PNG 1088×1088"),
        (
            _png((128, 128), "RGB", (255, 255, 255)),
            "piece",
            "image/png",
            "У фигуры должен быть прозрачный фон",
        ),
    ]
    for data, kind, content_type, message in cases:
        resp = await _upload(admin, kind, data, content_type)
        assert resp.status_code == 422, (message, resp.text)
        error = resp.json()["error"]
        assert error["code"] == "SKIN_IMAGE_INVALID", (message, resp.text)
        assert error["message"] == message, resp.text

    resp = await _upload(admin, "hat", _png((128, 128)))
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_upload_requires_admin(alice) -> None:
    resp = await _upload(alice, "piece", _png((128, 128)))
    assert resp.status_code == 403
    async with anonymous() as anon:
        resp = await _upload(anon, "piece", _png((128, 128)))
    assert resp.status_code == 401


async def test_get_missing() -> None:
    async with anonymous() as anon:
        resp = await anon.get(f"/api/v1/skins/{'0' * 64}.png")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "SKIN_IMAGE_NOT_FOUND"

        resp = await anon.get("/api/v1/skins/abc.png")
        assert resp.status_code == 404


async def test_seed_images_served() -> None:
    async with anonymous() as anon:
        resp = await anon.get(f"/api/v1/skins/{seed_image_id('base-board')}.png")
    assert resp.status_code == 200
    assert Image.open(io.BytesIO(resp.content)).size == (1088, 1088)


async def test_asset_validation_in_catalog(admin) -> None:
    resp = await admin.post("/api/v1/admin/sets", json=_set_body())
    assert resp.status_code == 201, resp.text
    set_id = resp.json()["id"]
    url = f"/api/v1/admin/sets/{set_id}/boards"

    resp = await admin.post(
        url,
        json=_board_body(
            "winter-board-piece-img",
            seed_asset("base-wp"),
        ),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    resp = await admin.post(
        url,
        json=_board_body(
            "winter-board-missing",
            {"type": "png", "image": "0" * 64, "exteriors": {e: "0" * 64 for e in EXTERIORS}},
        ),
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "SKIN_IMAGE_NOT_FOUND"

    resp = await admin.post(
        url,
        json=_board_body(
            "winter-board-stub",
            {"type": "stub", "light": "#ffffff", "dark": "#000000"},
        ),
    )
    assert resp.status_code == 422, resp.text

    resp = await admin.post(
        url,
        json=_board_body(
            "winter-board-ok",
            seed_asset("base-board"),
        ),
    )
    assert resp.status_code == 201, resp.text
