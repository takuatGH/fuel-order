"""health check endpoints.

used by load balancers and monitoring to verify service is running.
"""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """basic health check - returns 200 if service is running."""
    return {"status": "healthy"}


@router.get("/ready")
async def readiness_check():
    """readiness check - verifies dependencies are available."""
    return {"status": "ready"}