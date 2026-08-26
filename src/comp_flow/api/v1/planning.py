"""Employee Review Proposals & Calibration Planning API Endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.core.database import get_db
from comp_flow.core.security import get_current_user, require_roles
from comp_flow.domain.entities import CompensationCycle, EmployeeReview, User
from comp_flow.domain.models import (
    AgentAuditResult,
    BatchAuditRequest,
    BatchAuditResponse,
    CompensationCycleResponse,
    EmployeeReviewProposalCreate,
    EmployeeReviewProposalResponse,
    StatusTransitionRequest,
    UserRole,
)
from comp_flow.service.cycle_service import CycleService

router = APIRouter(prefix="", tags=["Compensation Planning"])


@router.post("/cycles/{cycle_id}/proposals", response_model=EmployeeReviewProposalResponse)
async def create_proposal(
    cycle_id: uuid.UUID,
    proposal_in: EmployeeReviewProposalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PEOPLE_MANAGER, UserRole.HR_ADMIN)),
) -> EmployeeReview:
    """Creates a manager's employee review proposal in DRAFT status."""
    return await CycleService.create_proposal(db, cycle_id, proposal_in, current_user)


@router.post("/proposals/{proposal_id}/audit", response_model=AgentAuditResult)
async def audit_proposal(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentAuditResult:
    """Submits and triggers deterministic agentic audit on a proposal."""
    return await CycleService.audit_proposal(db, proposal_id, actor_email=current_user.email)


@router.post("/cycles/{cycle_id}/batch-audit", response_model=BatchAuditResponse)
async def batch_audit_cycle_proposals(
    cycle_id: uuid.UUID,
    req: BatchAuditRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PEOPLE_MANAGER, UserRole.HR_ADMIN)),
) -> BatchAuditResponse:
    """Executes deterministic agentic audits across cycle proposals in batch."""
    proposal_ids = req.proposal_ids if req else None
    return await CycleService.batch_audit_cycle(
        db, cycle_id, actor_email=current_user.email, proposal_ids=proposal_ids
    )


@router.post("/proposals/{proposal_id}/approve", response_model=EmployeeReviewProposalResponse)
async def approve_proposal_exception(
    proposal_id: uuid.UUID,
    req: StatusTransitionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.EXECUTIVE_APPROVER, UserRole.COMPENSATION_PARTNER, UserRole.HR_ADMIN)
    ),
) -> EmployeeReview:
    """Approves a proposal requiring VP exception sign-off."""
    notes = req.notes if req else ""
    return await CycleService.approve_proposal(
        db, proposal_id, actor_email=current_user.email, notes=notes
    )


@router.post("/cycles/{cycle_id}/finalize", response_model=CompensationCycleResponse)
async def finalize_cycle(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.HR_ADMIN)),
) -> CompensationCycle:
    """Finalizes compensation cycle and commits updated compensation to employees (requires HR_ADMIN)."""
    return await CycleService.finalize_cycle(db, cycle_id, actor_email=current_user.email)
