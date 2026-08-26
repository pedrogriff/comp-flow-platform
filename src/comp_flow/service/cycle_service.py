"""Compensation Planning Cycle & Employee Review Proposal Workflow Service."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from comp_flow.agent.orchestrator import EmployeeCalibrationAgent
from comp_flow.core.metrics import AUDIT_REQUESTS_TOTAL, PROPOSALS_TOTAL
from comp_flow.domain.entities import (
    AuditLog,
    CompensationCycle,
    CycleBudget,
    Department,
    Employee,
    EmployeeReview,
    User,
)
from comp_flow.domain.models import (
    AgentAuditResult,
    BatchAuditResponse,
    CompensationCycleCreate,
    CycleStatus,
    DepartmentBudgetRollup,
    EmployeeReviewProposalCreate,
    ReviewStatus,
)
from comp_flow.domain.state_machine import EmployeeReviewStateMachine
from comp_flow.service.band_service import BandService
from comp_flow.tools.registry import calculate_compa_ratio

calibration_agent = EmployeeCalibrationAgent()


class CycleService:
    """Manages cycle lifecycles, employee review proposals, agent audits, and approvals."""

    @classmethod
    async def create_cycle(
        cls, db: AsyncSession, cycle_in: CompensationCycleCreate
    ) -> CompensationCycle:
        """Creates a new planning cycle and automatically provisions departmental budgets."""
        cycle = CompensationCycle(
            id=uuid.uuid4(),
            name=cycle_in.name,
            fiscal_year=cycle_in.fiscal_year,
            cycle_type=cycle_in.cycle_type,
            global_merit_budget_pct=cycle_in.global_merit_budget_pct,
            bonus_pool_funding_pct=cycle_in.bonus_pool_funding_pct,
            company_performance_factor=cycle_in.company_performance_factor,
            status=CycleStatus.ACTIVE,
            start_date=cycle_in.start_date,
            end_date=cycle_in.end_date,
        )
        db.add(cycle)
        await db.flush()

        # Query all departments and their active employees to initialize budget pools
        dept_stmt = select(Department).options(selectinload(Department.employees))
        dept_res = await db.execute(dept_stmt)
        departments = dept_res.scalars().all()

        for dept in departments:
            active_emps = [e for e in dept.employees if e.is_active]
            total_payroll = sum((e.current_base for e in active_emps), Decimal("0.00"))

            allocated_merit = (
                total_payroll * (cycle_in.global_merit_budget_pct / Decimal("100.0"))
            ).quantize(Decimal("0.01"))
            allocated_bonus = (
                total_payroll
                * Decimal("0.15")
                * (cycle_in.bonus_pool_funding_pct / Decimal("100.0"))
            ).quantize(Decimal("0.01"))
            allocated_equity = len(active_emps) * 1000  # Baseline 1000 GSUs per head pool

            budget = CycleBudget(
                id=uuid.uuid4(),
                cycle_id=cycle.id,
                department_id=dept.id,
                allocated_merit_budget=allocated_merit,
                depleted_merit_budget=Decimal("0.00"),
                allocated_bonus_pool=allocated_bonus,
                depleted_bonus_pool=Decimal("0.00"),
                allocated_equity_pool=allocated_equity,
                depleted_equity_pool=0,
            )
            db.add(budget)

        await db.flush()
        return await cls.get_cycle(db, cycle.id)

    @classmethod
    async def list_cycles(cls, db: AsyncSession) -> list[CompensationCycle]:
        """Lists all compensation cycles."""
        stmt = (
            select(CompensationCycle)
            .options(selectinload(CompensationCycle.budgets).selectinload(CycleBudget.department))
            .order_by(CompensationCycle.created_at.desc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @classmethod
    async def get_cycle(cls, db: AsyncSession, cycle_id: uuid.UUID) -> CompensationCycle:
        """Retrieves a specific compensation cycle with budgets."""
        stmt = (
            select(CompensationCycle)
            .where(CompensationCycle.id == cycle_id)
            .options(selectinload(CompensationCycle.budgets).selectinload(CycleBudget.department))
        )
        res = await db.execute(stmt)
        cycle = res.scalar_one_or_none()
        if not cycle:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
        return cycle

    @classmethod
    async def create_proposal(
        cls,
        db: AsyncSession,
        cycle_id: uuid.UUID,
        proposal_in: EmployeeReviewProposalCreate,
        manager_user: User | None = None,
    ) -> EmployeeReview:
        """Creates a new employee review proposal in DRAFT status."""
        cycle = await cls.get_cycle(db, cycle_id)
        if cycle.status in (CycleStatus.LOCKED, CycleStatus.FINALIZED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot add proposal to a cycle in '{cycle.status.value}' status",
            )

        # Check existing proposal in this cycle
        existing_stmt = select(EmployeeReview).where(
            EmployeeReview.cycle_id == cycle_id,
            EmployeeReview.employee_id == proposal_in.employee_id,
        )
        existing_res = await db.execute(existing_stmt)
        if existing_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A proposal for this employee already exists in this cycle",
            )

        emp_stmt = select(Employee).where(Employee.id == proposal_in.employee_id)
        emp_res = await db.execute(emp_stmt)
        emp = emp_res.scalar_one_or_none()
        if not emp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        # Lookup salary band
        band = await BandService.get_band(db, emp.job_level, emp.job_family, emp.location_tier)
        current_compa = calculate_compa_ratio(emp.current_base, band.mid_base)

        new_band = await BandService.get_band(
            db, proposal_in.proposed_job_level, emp.job_family, emp.location_tier
        )
        proposed_compa = calculate_compa_ratio(proposal_in.proposed_base, new_band.mid_base)

        merit_pct = (
            (
                (proposal_in.proposed_base - emp.current_base) / emp.current_base * Decimal("100.0")
            ).quantize(Decimal("0.01"))
            if emp.current_base > Decimal("0.00")
            else Decimal("0.00")
        )

        review = EmployeeReview(
            id=uuid.uuid4(),
            cycle_id=cycle_id,
            employee_id=proposal_in.employee_id,
            manager_id=manager_user.id if manager_user else None,
            proposed_job_level=proposal_in.proposed_job_level,
            current_base=emp.current_base,
            proposed_base=proposal_in.proposed_base,
            current_compa_ratio=current_compa,
            proposed_compa_ratio=proposed_compa,
            merit_increase_pct=merit_pct,
            proposed_bonus_amount=proposal_in.proposed_bonus_amount,
            individual_perf_factor=proposal_in.individual_perf_factor,
            company_perf_factor=cycle.company_performance_factor,
            proposed_equity_gsus=proposal_in.proposed_equity_gsus,
            performance_rating=proposal_in.performance_rating,
            status=ReviewStatus.DRAFT,
            justification_notes=proposal_in.justification_notes,
        )
        db.add(review)
        await db.flush()

        PROPOSALS_TOTAL.labels(status=ReviewStatus.DRAFT.value).inc()
        return review

    @classmethod
    async def audit_proposal(
        cls,
        db: AsyncSession,
        proposal_id: uuid.UUID,
        actor_email: str = "system@compflow.internal",
    ) -> AgentAuditResult:
        """Submits and audits a review proposal through the deterministic calibration agent."""
        stmt = (
            select(EmployeeReview)
            .where(EmployeeReview.id == proposal_id)
            .options(selectinload(EmployeeReview.employee), selectinload(EmployeeReview.cycle))
        )
        res = await db.execute(stmt)
        proposal = res.scalar_one_or_none()
        if not proposal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")

        prev_status = proposal.status

        # 1. State machine: DRAFT/REJECTED -> SUBMITTED -> AGENT_AUDITING
        if proposal.status in (ReviewStatus.DRAFT, ReviewStatus.REJECTED):
            proposal.status = EmployeeReviewStateMachine.transition(
                proposal.status, ReviewStatus.SUBMITTED, str(proposal.id)
            )

        proposal.status = EmployeeReviewStateMachine.transition(
            proposal.status, ReviewStatus.AGENT_AUDITING, str(proposal.id)
        )

        # 2. Get benchmark salary band
        band = await BandService.get_band(
            db,
            proposal.proposed_job_level,
            proposal.employee.job_family,
            proposal.employee.location_tier,
        )

        # 3. Execute Agentic Audit
        audit_res = calibration_agent.audit_review_proposal(
            review_id=str(proposal.id),
            current_level=proposal.employee.job_level,
            proposed_level=proposal.proposed_job_level,
            job_family=proposal.employee.job_family,
            location_tier=proposal.employee.location_tier,
            current_base=proposal.current_base,
            proposed_base=proposal.proposed_base,
            proposed_bonus=proposal.proposed_bonus_amount,
            individual_perf_factor=proposal.individual_perf_factor,
            company_perf_factor=proposal.company_perf_factor,
            proposed_equity_gsus=proposal.proposed_equity_gsus,
            performance_rating=proposal.performance_rating,
            band=band,
        )

        # 4. State transition based on audit decision
        new_status = ReviewStatus(audit_res.decision)
        proposal.status = EmployeeReviewStateMachine.transition(
            proposal.status, new_status, str(proposal.id)
        )
        proposal.audit_summary = audit_res.model_dump(mode="json")
        proposal.proposed_compa_ratio = audit_res.compa_ratio

        # 5. Log immutable audit trail
        audit_log = AuditLog(
            id=uuid.uuid4(),
            entity_type="EMPLOYEE_REVIEW",
            entity_id=proposal.id,
            action="AGENT_AUDIT",
            actor_email=actor_email,
            previous_status=prev_status.value,
            new_status=new_status.value,
            details=audit_res.model_dump(mode="json"),
        )
        db.add(audit_log)
        await db.flush()

        AUDIT_REQUESTS_TOTAL.labels(
            workflow_type="employee_review", decision=new_status.value
        ).inc()
        PROPOSALS_TOTAL.labels(status=new_status.value).inc()

        return audit_res

    @classmethod
    async def batch_audit_cycle(
        cls,
        db: AsyncSession,
        cycle_id: uuid.UUID,
        actor_email: str,
        proposal_ids: list[uuid.UUID] | None = None,
    ) -> BatchAuditResponse:
        """Audits multiple or all proposals in a cycle."""
        stmt = select(EmployeeReview.id).where(EmployeeReview.cycle_id == cycle_id)
        if proposal_ids:
            stmt = stmt.where(EmployeeReview.id.in_(proposal_ids))
        res = await db.execute(stmt)
        ids_to_audit = res.scalars().all()

        results: list[AgentAuditResult] = []
        auto_approved = 0
        vp_exceptions = 0
        rejected = 0

        for p_id in ids_to_audit:
            audit_result = await cls.audit_proposal(db, p_id, actor_email)
            results.append(audit_result)
            if audit_result.decision == ReviewStatus.AUTO_APPROVED.value:
                auto_approved += 1
            elif audit_result.decision == ReviewStatus.VP_EXCEPTION_REQUIRED.value:
                vp_exceptions += 1
            elif audit_result.decision == ReviewStatus.REJECTED.value:
                rejected += 1

        return BatchAuditResponse(
            cycle_id=cycle_id,
            total_audited=len(results),
            auto_approved_count=auto_approved,
            vp_exception_count=vp_exceptions,
            rejected_count=rejected,
            results=results,
        )

    @classmethod
    async def approve_proposal(
        cls,
        db: AsyncSession,
        proposal_id: uuid.UUID,
        actor_email: str,
        notes: str = "",
    ) -> EmployeeReview:
        """Approves a review proposal in VP_EXCEPTION_REQUIRED status."""
        stmt = select(EmployeeReview).where(EmployeeReview.id == proposal_id)
        res = await db.execute(stmt)
        proposal = res.scalar_one_or_none()
        if not proposal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")

        prev = proposal.status
        proposal.status = EmployeeReviewStateMachine.transition(
            proposal.status, ReviewStatus.VP_APPROVED, str(proposal.id)
        )
        if notes:
            proposal.justification_notes += f" [Approved by {actor_email}: {notes}]"

        log = AuditLog(
            id=uuid.uuid4(),
            entity_type="EMPLOYEE_REVIEW",
            entity_id=proposal.id,
            action="VP_APPROVAL",
            actor_email=actor_email,
            previous_status=prev.value,
            new_status=ReviewStatus.VP_APPROVED.value,
            details={"notes": notes},
        )
        db.add(log)
        await db.flush()

        PROPOSALS_TOTAL.labels(status=ReviewStatus.VP_APPROVED.value).inc()
        return proposal

    @classmethod
    async def finalize_cycle(
        cls,
        db: AsyncSession,
        cycle_id: uuid.UUID,
        actor_email: str,
    ) -> CompensationCycle:
        """Finalizes all approved proposals and applies new base salaries/equity to employees."""
        cycle = await cls.get_cycle(db, cycle_id)
        if cycle.status == CycleStatus.FINALIZED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Cycle is already finalized"
            )

        reviews_stmt = (
            select(EmployeeReview)
            .where(EmployeeReview.cycle_id == cycle_id)
            .options(selectinload(EmployeeReview.employee))
        )
        reviews_res = await db.execute(reviews_stmt)
        reviews = reviews_res.scalars().all()

        # Check for non-terminal / unresolved proposals
        pending = [
            r
            for r in reviews
            if r.status
            in (
                ReviewStatus.SUBMITTED,
                ReviewStatus.AGENT_AUDITING,
                ReviewStatus.VP_EXCEPTION_REQUIRED,
            )
        ]
        if pending:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot finalize cycle: {len(pending)} proposals are pending review or exception sign-off",
            )

        # Transition approved proposals to FINALIZED and apply compensation changes
        for r in reviews:
            if r.status in (ReviewStatus.AUTO_APPROVED, ReviewStatus.VP_APPROVED):
                r.status = EmployeeReviewStateMachine.transition(
                    r.status, ReviewStatus.FINALIZED, str(r.id)
                )
                emp = r.employee
                emp.current_base = r.proposed_base
                emp.job_level = r.proposed_job_level
                emp.current_equity_gsus += r.proposed_equity_gsus
                emp.last_performance_rating = r.performance_rating

        cycle.status = CycleStatus.FINALIZED
        log = AuditLog(
            id=uuid.uuid4(),
            entity_type="COMPENSATION_CYCLE",
            entity_id=cycle.id,
            action="CYCLE_FINALIZATION",
            actor_email=actor_email,
            previous_status=CycleStatus.ACTIVE.value,
            new_status=CycleStatus.FINALIZED.value,
            details={"proposals_finalized": len(reviews)},
        )
        db.add(log)
        await db.flush()
        return await cls.get_cycle(db, cycle.id)

    @classmethod
    async def get_department_budget_rollup(
        cls,
        db: AsyncSession,
        cycle_id: uuid.UUID,
        department_id: uuid.UUID,
    ) -> DepartmentBudgetRollup:
        """Calculates real-time allocated vs depleted budget metrics for a department in a cycle."""
        dept_stmt = (
            select(Department)
            .where(Department.id == department_id)
            .options(selectinload(Department.employees))
        )
        dept_res = await db.execute(dept_stmt)
        dept = dept_res.scalar_one_or_none()
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Department not found"
            )

        budget_stmt = select(CycleBudget).where(
            CycleBudget.cycle_id == cycle_id, CycleBudget.department_id == department_id
        )
        budget_res = await db.execute(budget_stmt)
        budget = budget_res.scalar_one_or_none()

        active_emps = [e for e in dept.employees if e.is_active]
        current_payroll = sum((e.current_base for e in active_emps), Decimal("0.00"))

        # Calculate actual depleted sums from active proposals in this cycle
        proposals_stmt = select(EmployeeReview).where(
            EmployeeReview.cycle_id == cycle_id,
            EmployeeReview.employee_id.in_([e.id for e in active_emps]),
            EmployeeReview.status.notin_([ReviewStatus.REJECTED]),
        )
        p_res = await db.execute(proposals_stmt)
        proposals = p_res.scalars().all()

        depleted_merit = sum(
            (max(Decimal("0.00"), p.proposed_base - p.current_base) for p in proposals),
            Decimal("0.00"),
        )
        depleted_bonus = sum((p.proposed_bonus_amount for p in proposals), Decimal("0.00"))
        depleted_equity = sum((p.proposed_equity_gsus for p in proposals), 0)

        allocated_merit = budget.allocated_merit_budget if budget else Decimal("0.00")
        allocated_bonus = budget.allocated_bonus_pool if budget else Decimal("0.00")
        allocated_equity = budget.allocated_equity_pool if budget else 0

        merit_pct = (
            (depleted_merit / allocated_merit * Decimal("100.0")).quantize(Decimal("0.01"))
            if allocated_merit > Decimal("0.00")
            else Decimal("0.00")
        )
        bonus_pct = (
            (depleted_bonus / allocated_bonus * Decimal("100.0")).quantize(Decimal("0.01"))
            if allocated_bonus > Decimal("0.00")
            else Decimal("0.00")
        )
        equity_pct = (
            (Decimal(depleted_equity) / Decimal(allocated_equity) * Decimal("100.0")).quantize(
                Decimal("0.01")
            )
            if allocated_equity > 0
            else Decimal("0.00")
        )

        return DepartmentBudgetRollup(
            department_id=dept.id,
            department_name=dept.name,
            total_headcount=len(active_emps),
            current_payroll_base=current_payroll,
            allocated_merit_budget=allocated_merit,
            depleted_merit_budget=depleted_merit,
            merit_budget_remaining=allocated_merit - depleted_merit,
            merit_budget_depletion_pct=merit_pct,
            allocated_bonus_pool=allocated_bonus,
            depleted_bonus_pool=depleted_bonus,
            bonus_pool_depletion_pct=bonus_pct,
            allocated_equity_pool=allocated_equity,
            depleted_equity_pool=depleted_equity,
            equity_pool_depletion_pct=equity_pct,
        )
