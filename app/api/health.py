from fastapi import APIRouter

from app.globals import settings

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness check", response_description="Service status")
def health_check() -> dict[str, str]:
    """Basic liveness probe used by orchestrators/load balancers."""
    return {"status": "ok", "env": settings.env.value}
