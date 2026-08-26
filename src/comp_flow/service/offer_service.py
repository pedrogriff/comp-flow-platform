"""Candidate New Hire Offer Management and Approval Service."""

from __future__ import annotations

import random
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.agent.orchestrator import OfferApprovalAgent
from comp_flow.core.metrics import AUDIT_REQUESTS_TOTAL, OFFERS_TOTAL
from comp_flow.domain.entities import AuditLog, CandidateOffer, User
from comp_flow.domain.models import (
    AgentAuditResult,
    CandidateOfferCreate,
    OfferStatus,
)
from comp_flow.domain.state_machine import OfferStateMachine
from comp_flow.service.band_service import BandService
from comp_flow.tools.registry import calculate_compa_ratio, calculate_offer_total_comp

offer_agent = OfferApprovalAgent()


class OfferService:
    """Manages candidate offer proposals, deterministic audits, and state progression."""

    @classmethod
    async def create_offer(
        cls,
        db: AsyncSession,
        offer_in: CandidateOfferCreate,
        recruiter_user: User | None = None,
    ) -> CandidateOffer:
        """Creates a new candidate offer proposal in OFFER_DRAFT status."""
        band = await BandService.get_band(
            db, offer_in.job_level, offer_in.job_family, offer_in.location_tier
        )

        compa = calculate_compa_ratio(offer_in.proposed_base, band.mid_base)
        totals = calculate_offer_total_comp(
            proposed_base=offer_in.proposed_base,
            sign_on_bonus=offer_in.sign_on_bonus,
            target_bonus_pct=band.target_bonus_pct,
            proposed_equity_gsus=offer_in.proposed_equity_gsus,
        )

        random_suffix = random.randint(1000, 9999)
        offer_number = f"OFF-2026-{random_suffix}"

        offer = CandidateOffer(
            id=uuid.uuid4(),
            offer_number=offer_number,
            candidate_name=offer_in.candidate_name,
            candidate_email=offer_in.candidate_email,
            job_level=offer_in.job_level,
            job_family=offer_in.job_family,
            location_tier=offer_in.location_tier,
            department_id=offer_in.department_id,
            recruiter_id=recruiter_user.id if recruiter_user else None,
            hiring_manager_id=offer_in.hiring_manager_id,
            proposed_base=offer_in.proposed_base,
            sign_on_bonus=offer_in.sign_on_bonus,
            proposed_equity_gsus=offer_in.proposed_equity_gsus,
            compa_ratio=compa,
            total_target_cash=totals["total_target_cash"],
            first_year_total_comp=totals["first_year_total_comp"],
            target_start_date=offer_in.target_start_date,
            status=OfferStatus.OFFER_DRAFT,
            notes=offer_in.notes,
        )
        db.add(offer)
        await db.flush()

        OFFERS_TOTAL.labels(status=OfferStatus.OFFER_DRAFT.value).inc()
        return offer

    @classmethod
    async def get_offer(cls, db: AsyncSession, offer_id: uuid.UUID) -> CandidateOffer:
        """Retrieves offer by ID."""
        stmt = select(CandidateOffer).where(CandidateOffer.id == offer_id)
        res = await db.execute(stmt)
        offer = res.scalar_one_or_none()
        if not offer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
        return offer

    @classmethod
    async def list_offers(
        cls,
        db: AsyncSession,
        status_filter: OfferStatus | None = None,
        department_id: uuid.UUID | None = None,
    ) -> list[CandidateOffer]:
        """Lists candidate offers with optional filtering."""
        stmt = select(CandidateOffer).order_by(CandidateOffer.created_at.desc())
        if status_filter:
            stmt = stmt.where(CandidateOffer.status == status_filter)
        if department_id:
            stmt = stmt.where(CandidateOffer.department_id == department_id)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @classmethod
    async def audit_offer(
        cls,
        db: AsyncSession,
        offer_id: uuid.UUID,
        actor_email: str = "system@compflow.internal",
    ) -> AgentAuditResult:
        """Executes deterministic audit on candidate offer and updates status."""
        offer = await cls.get_offer(db, offer_id)
        prev = offer.status

        # 1. State machine: DRAFT/REJECTED -> AUDIT_PENDING
        if offer.status in (OfferStatus.OFFER_DRAFT, OfferStatus.OFFER_REJECTED):
            offer.status = OfferStateMachine.transition(
                offer.status, OfferStatus.AUDIT_PENDING, offer.offer_number
            )

        band = await BandService.get_band(
            db, offer.job_level, offer.job_family, offer.location_tier
        )

        # 2. Agentic Audit Execution
        audit_res = offer_agent.audit_offer_package(
            offer_id=str(offer.id),
            job_level=offer.job_level,
            job_family=offer.job_family,
            location_tier=offer.location_tier,
            proposed_base=offer.proposed_base,
            sign_on_bonus=offer.sign_on_bonus,
            proposed_equity_gsus=offer.proposed_equity_gsus,
            band=band,
        )

        # 3. Transition to decision status
        new_status = OfferStatus(audit_res.decision)
        offer.status = OfferStateMachine.transition(offer.status, new_status, offer.offer_number)
        offer.audit_summary = audit_res.model_dump(mode="json")
        offer.compa_ratio = audit_res.compa_ratio

        # 4. Record Audit Log
        log = AuditLog(
            id=uuid.uuid4(),
            entity_type="CANDIDATE_OFFER",
            entity_id=offer.id,
            action="OFFER_AUDIT",
            actor_email=actor_email,
            previous_status=prev.value,
            new_status=new_status.value,
            details=audit_res.model_dump(mode="json"),
        )
        db.add(log)
        await db.flush()

        AUDIT_REQUESTS_TOTAL.labels(
            workflow_type="candidate_offer", decision=new_status.value
        ).inc()
        OFFERS_TOTAL.labels(status=new_status.value).inc()

        return audit_res

    @classmethod
    async def approve_offer(
        cls,
        db: AsyncSession,
        offer_id: uuid.UUID,
        actor_email: str,
        notes: str = "",
    ) -> CandidateOffer:
        """Approves an offer in VP_EXCEPTION_REQUIRED status."""
        offer = await cls.get_offer(db, offer_id)
        prev = offer.status

        offer.status = OfferStateMachine.transition(
            offer.status, OfferStatus.OFFER_APPROVED, offer.offer_number
        )
        if notes:
            offer.notes += f" [Approved by {actor_email}: {notes}]"

        log = AuditLog(
            id=uuid.uuid4(),
            entity_type="CANDIDATE_OFFER",
            entity_id=offer.id,
            action="OFFER_APPROVAL",
            actor_email=actor_email,
            previous_status=prev.value,
            new_status=OfferStatus.OFFER_APPROVED.value,
            details={"notes": notes},
        )
        db.add(log)
        await db.flush()

        OFFERS_TOTAL.labels(status=OfferStatus.OFFER_APPROVED.value).inc()
        return offer

    @classmethod
    async def extend_offer(
        cls,
        db: AsyncSession,
        offer_id: uuid.UUID,
        actor_email: str,
        notes: str = "",
    ) -> CandidateOffer:
        """Marks offer as officially extended to candidate."""
        offer = await cls.get_offer(db, offer_id)
        prev = offer.status

        offer.status = OfferStateMachine.transition(
            offer.status, OfferStatus.OFFER_EXTENDED, offer.offer_number
        )
        if notes:
            offer.notes += f" [Extended by {actor_email}: {notes}]"

        log = AuditLog(
            id=uuid.uuid4(),
            entity_type="CANDIDATE_OFFER",
            entity_id=offer.id,
            action="OFFER_EXTENDED",
            actor_email=actor_email,
            previous_status=prev.value,
            new_status=OfferStatus.OFFER_EXTENDED.value,
            details={"notes": notes},
        )
        db.add(log)
        await db.flush()

        OFFERS_TOTAL.labels(status=OfferStatus.OFFER_EXTENDED.value).inc()
        return offer

    @classmethod
    async def record_candidate_decision(
        cls,
        db: AsyncSession,
        offer_id: uuid.UUID,
        decision_status: OfferStatus,
        actor_email: str,
        notes: str = "",
    ) -> CandidateOffer:
        """Records candidate acceptance, decline, or organization rescission."""
        if decision_status not in (
            OfferStatus.OFFER_ACCEPTED,
            OfferStatus.OFFER_DECLINED,
            OfferStatus.OFFER_RESCINDED,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid decision status '{decision_status.value}'",
            )

        offer = await cls.get_offer(db, offer_id)
        prev = offer.status

        offer.status = OfferStateMachine.transition(
            offer.status, decision_status, offer.offer_number
        )
        if notes:
            offer.notes += f" [Decision {decision_status.value} recorded by {actor_email}: {notes}]"

        log = AuditLog(
            id=uuid.uuid4(),
            entity_type="CANDIDATE_OFFER",
            entity_id=offer.id,
            action=f"DECISION_{decision_status.value}",
            actor_email=actor_email,
            previous_status=prev.value,
            new_status=decision_status.value,
            details={"notes": notes},
        )
        db.add(log)
        await db.flush()

        OFFERS_TOTAL.labels(status=decision_status.value).inc()
        return offer
