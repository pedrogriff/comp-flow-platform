"""Analytics and Distribution Metrics API Endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.core.database import get_db
from comp_flow.core.security import get_current_user
from comp_flow.domain.entities import User
from comp_flow.service.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics & Reporting"])


@router.get("/cycles/{cycle_id}")
async def get_cycle_analytics(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieves cycle distribution analytics, compa-ratio buckets, and budget burn."""
    return await AnalyticsService.get_cycle_analytics(db, cycle_id)
