"""Candidate New Hire Offers API Endpoints."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.core.database import get_db
from comp_flow.core.security import get_current_user, get_optional_user, require_roles
from comp_flow.domain.entities import CandidateOffer, User
from comp_flow.domain.models import (
    AgentAuditResult,
    CandidateOfferCreate,
    CandidateOfferResponse,
    OfferStatus,
    StatusTransitionRequest,
    UserRole,
)
from comp_flow.domain.negotiation import (
    CompetingOfferInput,
    CounterOfferSimulationResult,
    OurOfferInput,
)
from comp_flow.service.negotiation_service import NegotiationService
from comp_flow.service.offer_service import OfferService

router = APIRouter(prefix="/offers", tags=["Candidate Offers"])


@router.post("", response_model=CandidateOfferResponse)
async def create_offer(
    offer_in: CandidateOfferCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            UserRole.RECRUTER if hasattr(UserRole, "RECRUTER") else UserRole.RECRUITER,
            UserRole.HR_ADMIN,
        )
    ),
) -> CandidateOffer:
    """Creates a new candidate offer proposal in DRAFT status."""
    return await OfferService.create_offer(db, offer_in, recruiter_user=current_user)


@router.get("", response_model=list[CandidateOfferResponse])
async def list_offers(
    status: OfferStatus | None = Query(default=None),
    department_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[CandidateOffer]:
    """Lists candidate offers with optional filtering."""
    return await OfferService.list_offers(db, status_filter=status, department_id=department_id)


@router.get("/{offer_id}", response_model=CandidateOfferResponse)
async def get_offer(
    offer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CandidateOffer:
    """Retrieves detailed candidate offer proposal."""
    return await OfferService.get_offer(db, offer_id)


@router.post("/{offer_id}/audit", response_model=AgentAuditResult)
async def audit_offer(
    offer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentAuditResult:
    """Runs deterministic policy audit on candidate offer package."""
    return await OfferService.audit_offer(db, offer_id, actor_email=current_user.email)


@router.post("/{offer_id}/approve", response_model=CandidateOfferResponse)
async def approve_offer_exception(
    offer_id: uuid.UUID,
    req: StatusTransitionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.EXECUTIVE_APPROVER, UserRole.COMPENSATION_PARTNER, UserRole.HR_ADMIN)
    ),
) -> CandidateOffer:
    """Approves an offer package requiring executive exception sign-off."""
    notes = req.notes if req else ""
    return await OfferService.approve_offer(
        db, offer_id, actor_email=current_user.email, notes=notes
    )


@router.post("/{offer_id}/extend", response_model=CandidateOfferResponse)
async def extend_offer(
    offer_id: uuid.UUID,
    req: StatusTransitionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.HR_ADMIN)),
) -> CandidateOffer:
    """Marks approved offer package as officially extended to candidate."""
    notes = req.notes if req else ""
    return await OfferService.extend_offer(
        db, offer_id, actor_email=current_user.email, notes=notes
    )


@router.post("/{offer_id}/decision", response_model=CandidateOfferResponse)
async def record_candidate_decision(
    offer_id: uuid.UUID,
    target_status: OfferStatus = Query(
        ..., description="OFFER_ACCEPTED, OFFER_DECLINED, or OFFER_RESCINDED"
    ),
    req: StatusTransitionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.HR_ADMIN)),
) -> CandidateOffer:
    """Records final candidate decision (ACCEPTED / DECLINED) or company rescission."""
    notes = req.notes if req else ""
    return await OfferService.record_candidate_decision(
        db, offer_id, decision_status=target_status, actor_email=current_user.email, notes=notes
    )


class CounterOfferSimulationPayload(BaseModel):
    """Payload for counter-offer simulation."""

    our_offer: OurOfferInput
    competing_offer: CompetingOfferInput


@router.post("/negotiation/simulate", response_model=CounterOfferSimulationResult)
async def simulate_counter_offer(
    payload: CounterOfferSimulationPayload,
    _user: User | None = Depends(get_optional_user),
) -> CounterOfferSimulationResult:
    """Simulates multi-year TDC comparison, forfeiture buyouts, and candidate win-rate elasticity."""
    return NegotiationService.simulate_counter_offer(
        our_offer=payload.our_offer,
        competing_offer=payload.competing_offer,
    )


@router.post("/{offer_id}/counter-simulator", response_model=CounterOfferSimulationResult)
async def simulate_offer_counter(
    offer_id: uuid.UUID,
    competing_offer: CompetingOfferInput,
    db: AsyncSession = Depends(get_db),
    _user: User | None = Depends(get_optional_user),
) -> CounterOfferSimulationResult:
    """Evaluates an existing draft offer in DB against a competing counter-offer."""
    offer = await OfferService.get_offer(db, offer_id)
    our_offer = OurOfferInput(
        base_salary=offer.proposed_base,
        target_bonus_pct=Decimal("15.00"),
        signon_bonus=offer.sign_on_bonus,
        equity_rsus_4yr=offer.proposed_equity_rsus,
        job_level=offer.job_level,
        job_family=offer.job_family,
        location_tier=offer.location_tier,
    )
    return NegotiationService.simulate_counter_offer(
        our_offer=our_offer,
        competing_offer=competing_offer,
    )
