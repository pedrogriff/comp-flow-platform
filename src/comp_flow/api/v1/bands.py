"""Salary Bands API Endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.core.database import get_db
from comp_flow.core.security import get_current_user, require_roles
from comp_flow.domain.entities import SalaryBand, User
from comp_flow.domain.models import (
    SalaryBandCreate,
    SalaryBandResponse,
    UserRole,
)
from comp_flow.service.band_service import BandService

router = APIRouter(prefix="/bands", tags=["Salary Bands"])


@router.get("", response_model=list[SalaryBandResponse])
async def list_salary_bands(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[SalaryBand]:
    """Lists all benchmark salary bands."""
    return await BandService.list_bands(db)


@router.post("", response_model=SalaryBandResponse)
async def upsert_salary_band(
    band_in: SalaryBandCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_roles(UserRole.HR_ADMIN)),
) -> SalaryBand:
    """Creates or updates a benchmark salary band (requires HR_ADMIN)."""
    return await BandService.upsert_band(db, band_in)
