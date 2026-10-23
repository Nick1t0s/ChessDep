"""Проверка, хранение и выдача PNG-картинок скинов (docs/contracts-skins.md)."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import SkinImage, User

PIECE_PX = 128
BOARD_PX = 1088
BOARD_FRAME_PX = 32
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

SKIN_IMAGE_NOT_FOUND = AppError(404, "SKIN_IMAGE_NOT_FOUND", "Картинка скина не найдена")
ASSET_KIND_MISMATCH = AppError(422, "VALIDATION_ERROR", "asset не соответствует виду скина")


def skin_url(image_id: str) -> str:
    return f"/api/v1/skins/{image_id}.png"


def normalize_png(kind: str, data: bytes) -> bytes:
    """Проверить PNG по правилам вида и вернуть перекодированные байты (RGBA PNG)."""
    raise NotImplementedError


async def store_image(db: AsyncSession, admin: User, kind: str, data: bytes) -> SkinImage:
    """normalize_png → sha256 → вставить, если нет; аудит skin_image.upload."""
    raise NotImplementedError


async def get_image(db: AsyncSession, image_id: str) -> SkinImage:
    """Картинка по id или SKIN_IMAGE_NOT_FOUND."""
    raise NotImplementedError


async def ensure_image(db: AsyncSession, image_id: str, kind: str) -> None:
    """Картинка есть (иначе SKIN_IMAGE_NOT_FOUND) и её kind совпадает (иначе ASSET_KIND_MISMATCH)."""
    raise NotImplementedError
