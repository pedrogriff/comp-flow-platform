"""API v1 Router aggregating authentication, bands, cycles, planning, offers, and analytics."""

from fastapi import APIRouter

from comp_flow.api.v1.analytics import router as analytics_router
from comp_flow.api.v1.auth import router as auth_router
from comp_flow.api.v1.bands import router as bands_router
from comp_flow.api.v1.cycles import router as cycles_router
from comp_flow.api.v1.offers import router as offers_router
from comp_flow.api.v1.planning import router as planning_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(bands_router)
api_v1_router.include_router(cycles_router)
api_v1_router.include_router(planning_router)
api_v1_router.include_router(offers_router)
api_v1_router.include_router(analytics_router)

__all__ = ["api_v1_router"]
