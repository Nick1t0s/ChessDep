from fastapi import APIRouter, Depends

from app.core.deps import require_admin

router = APIRouter(prefix="/api/v1", tags=["internal"])


@router.get("/internal/require-admin", status_code=204)
async def require_admin_endpoint(user=Depends(require_admin)) -> None:
    return None
