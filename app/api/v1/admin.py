from fastapi import APIRouter, Depends

from app.api.dependencies import require_roles
from app.models.user import User


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health")
def admin_health(current_user: User = Depends(require_roles(["admin"]))):
    return {"status": "admin-ok", "user": str(current_user.id)}


