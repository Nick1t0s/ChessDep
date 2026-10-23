"""PNG-картинки скинов: загрузка админом и публичная раздача (docs/contracts-skins.md §4)."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.db import get_db
from app.models import User
from app.schemas.items import SkinImageOut
from app.services.skin_images import NOT_PNG, get_image, skin_url, store_image

router = APIRouter(tags=["skins"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_admin)]

_CACHE_FOREVER = "public, max-age=31536000, immutable"


@router.post("/api/v1/admin/skin-images", response_model=SkinImageOut, status_code=201)
async def upload_skin_image(
    request: Request, kind: Literal["piece", "board"], admin: AdminDep, db: DbDep
) -> SkinImageOut:
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "image/png":
        raise NOT_PNG
    data = await request.body()
    image = await store_image(db, admin, kind, data)
    return SkinImageOut(image=image.id, kind=image.kind, url=skin_url(image.id))


@router.get("/api/v1/skins/{image_id}.png")
async def get_skin_image(image_id: str, db: DbDep) -> Response:
    image = await get_image(db, image_id)
    return Response(
        content=image.data, media_type="image/png", headers={"Cache-Control": _CACHE_FOREVER}
    )
