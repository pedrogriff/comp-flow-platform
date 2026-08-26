"""Compensation Cycles & Budgets API Endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.core.database import get_db
from comp_flow.core.security import get_current_user, require_roles
from comp_flow.domain.entities import CompensationCycle, User
from comp_flow.domain.models import (
    CompensationCycleCreate,
    CompensationCycleResponse,
    DepartmentBudgetRollup,
    UserRole,
)
from comp_flow.service.cycle_service import CycleService

router = APIRouter(prefix="/cycles", tags=["Compensation Cycles"])


@router.get("", response_model=list[CompensationCycleResponse])
async def list_cycles(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[CompensationCycle]:
    """Lists all compensation planning cycles."""
    return await CycleService.list_cycles(db)


@router.post("", response_model=CompensationCycleResponse)
async def create_cycle(
    cycle_in: CompensationCycleCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_roles(UserRole.HR_ADMIN)),
) -> CompensationCycle:
    """Creates a new compensation planning cycle and sets departmental budgets (requires HR_ADMIN)."""
    return await CycleService.create_cycle(db, cycle_in)


@router.get("/{cycle_id}", response_model=CompensationCycleResponse)
async def get_cycle(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CompensationCycle:
    """Retrieves a specific compensation planning cycle with budget allocations."""
    return await CycleService.get_cycle(db, cycle_id)


@router.get("/{cycle_id}/budgets/{department_id}", response_model=DepartmentBudgetRollup)
async def get_department_budget_rollup(
    cycle_id: uuid.UUID,
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DepartmentBudgetRollup:
    """Retrieves real-time allocated vs depleted budget breakdown for a department."""
    return await CycleService.get_department_budget_rollup(db, cycle_id, department_id)
