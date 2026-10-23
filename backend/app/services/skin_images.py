"""Проверка, хранение и выдача PNG-картинок скинов (docs/contracts-skins.md)."""
import hashlib
import io
import re

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import AdminAudit, SkinImage, User

PIECE_PX = 128
BOARD_PX = 1088
BOARD_FRAME_PX = 32
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

SKIN_IMAGE_NOT_FOUND = AppError(404, "SKIN_IMAGE_NOT_FOUND", "Картинка скина не найдена")
ASSET_KIND_MISMATCH = AppError(422, "VALIDATION_ERROR", "asset не соответствует виду скина")

_IMAGE_ID_RE = re.compile(r"[0-9a-f]{64}")
NOT_PNG = AppError(422, "SKIN_IMAGE_INVALID", "Нужен файл PNG")
TOO_BIG = AppError(422, "SKIN_IMAGE_INVALID", "Файл больше 2 МБ")
BAD_PIECE_SIZE = AppError(422, "SKIN_IMAGE_INVALID", "Фигура должна быть PNG 128×128")
BAD_BOARD_SIZE = AppError(422, "SKIN_IMAGE_INVALID", "Доска должна быть PNG 1088×1088")
NOT_TRANSPARENT = AppError(422, "SKIN_IMAGE_INVALID", "У фигуры должен быть прозрачный фон")


def skin_url(image_id: str) -> str:
    return f"/api/v1/skins/{image_id}.png"


def normalize_png(kind: str, data: bytes) -> bytes:
    """Проверить PNG по правилам вида и вернуть перекодированные байты (RGBA PNG)."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise TOO_BIG
    if len(data) == 0:
        raise NOT_PNG
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as exc:
        raise NOT_PNG from exc
    if img.format != "PNG":
        raise NOT_PNG
    if kind == "piece" and img.size != (PIECE_PX, PIECE_PX):
        raise BAD_PIECE_SIZE
    if kind == "board" and img.size != (BOARD_PX, BOARD_PX):
        raise BAD_BOARD_SIZE
    try:
        rgba = img.convert("RGBA")
    except Exception as exc:
        raise NOT_PNG from exc
    if kind == "piece":
        for p in ((0, 0), (127, 0), (0, 127), (127, 127)):
            if rgba.getpixel(p)[3] != 0:
                raise NOT_TRANSPARENT
    out = io.BytesIO()
    rgba.save(out, format="PNG", optimize=True)
    return out.getvalue()


async def store_image(db: AsyncSession, admin: User, kind: str, data: bytes) -> SkinImage:
    """normalize_png → sha256 → вставить, если нет; аудит skin_image.upload."""
    png = normalize_png(kind, data)
    image_id = hashlib.sha256(png).hexdigest()
    image = await db.get(SkinImage, image_id)
    if image is None:
        image = SkinImage(id=image_id, kind=kind, data=png)
        db.add(image)
        await db.flush()
    db.add(
        AdminAudit(
            admin_id=admin.id,
            action="skin_image.upload",
            target=f"skin_image:{image_id}",
            payload={"kind": kind},
        )
    )
    return image


async def get_image(db: AsyncSession, image_id: str) -> SkinImage:
    """Картинка по id или SKIN_IMAGE_NOT_FOUND."""
    if not _IMAGE_ID_RE.fullmatch(image_id):
        raise SKIN_IMAGE_NOT_FOUND
    image = await db.get(SkinImage, image_id)
    if image is None:
        raise SKIN_IMAGE_NOT_FOUND
    return image


async def ensure_image(db: AsyncSession, image_id: str, kind: str) -> None:
    """Картинка есть (иначе SKIN_IMAGE_NOT_FOUND) и её kind совпадает (иначе ASSET_KIND_MISMATCH)."""
    image = await get_image(db, image_id)
    if image.kind != kind:
        raise ASSET_KIND_MISMATCH
