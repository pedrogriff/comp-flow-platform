"""Technical Solutions Engineer (TSE) Incident Triage & Diagnostic Engine.

Provides automated root cause analysis, trace context correlation, policy violation
dissection, and cryptographic SOX ledger integrity checks for customer-facing incidents.
"""

from __future__ import annotations

import logging
import time
import uuid
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from comp_flow.core.ledger import SoxLedgerService
from comp_flow.domain.entities import (
    CandidateOffer,
    CycleBudget,
    EmployeeReview,
)
from comp_flow.domain.models import (
    ReviewStatus,
    TseAuditFindingReport,
    TseDiagnosticReport,
)
from comp_flow.service.band_service import BandService
from comp_flow.tools.registry import (
    calculate_compa_ratio,
    verify_salary_band_compliance,
)

logger = logging.getLogger(__name__)


class TseIncidentTriageService:
    """TSE Diagnostic Engine for Total Rewards Incidents and Policy Failures."""

    @classmethod
    async def diagnose(
        cls,
        db: AsyncSession,
        trace_id: str | None = None,
        review_id: UUID | None = None,
        offer_id: UUID | None = None,
    ) -> TseDiagnosticReport:
        """Executes full diagnostic triage across trace context, ledger integrity, and compensation rules."""
        t0 = time.perf_counter()
        incident_id = uuid.uuid4()

        # 1. Resolve Target Entity from Arguments or Trace ID
        resolved_review_id = review_id
        resolved_offer_id = offer_id
        effective_trace_id = trace_id

        if effective_trace_id and not resolved_review_id and not resolved_offer_id:
            # Look up ledger entries matching trace_id
            entries = await SoxLedgerService.get_entries_by_trace_id(db, effective_trace_id)
            if entries:
                first = entries[0]
                if first.entity_type == "EMPLOYEE_REVIEW":
                    resolved_review_id = first.entity_id
                elif first.entity_type == "CANDIDATE_OFFER":
                    resolved_offer_id = first.entity_id

        # 2. Verify Cryptographic SOX Ledger Chain
        ledger_result = await SoxLedgerService.verify_chain(db)

        # 3. Handle Employee Review Diagnosis
        if resolved_review_id:
            return await cls._diagnose_employee_review(
                db=db,
                incident_id=incident_id,
                review_id=resolved_review_id,
                trace_id=effective_trace_id,
                ledger_result=ledger_result,
                start_time=t0,
            )

        # 4. Handle Candidate Offer Diagnosis
        if resolved_offer_id:
            return await cls._diagnose_candidate_offer(
                db=db,
                incident_id=incident_id,
                offer_id=resolved_offer_id,
                trace_id=effective_trace_id,
                ledger_result=ledger_result,
                start_time=t0,
            )

        # If no target could be resolved
        duration_ms = (time.perf_counter() - t0) * 1000.0
        from datetime import UTC, datetime

        return TseDiagnosticReport(
            incident_id=incident_id,
            timestamp=datetime.now(UTC),
            trace_id=effective_trace_id,
            entity_type="UNKNOWN",
            entity_id=None,
            target_name=None,
            current_status=None,
            ledger_integrity=ledger_result,
            policy_findings=[],
            root_cause_category="UNRESOLVED_TARGET",
            customer_summary="No matching employee review or candidate offer found for the provided identifiers.",
            technical_analysis=(
                f"Query parameters (trace_id={effective_trace_id}, review_id={review_id}, offer_id={offer_id}) "
                "did not match any indexed ledger entries or active entity records."
            ),
            recommended_actions=[
                "Verify the provided review_id or offer_id UUID format",
                "Ensure the transaction was committed and not rolled back",
                "Check OpenTelemetry distributed trace collector for recent HTTP spans",
            ],
            execution_time_ms=round(duration_ms, 2),
        )

    @classmethod
    async def _diagnose_employee_review(
        cls,
        db: AsyncSession,
        incident_id: UUID,
        review_id: UUID,
        trace_id: str | None,
        ledger_result: Any,
        start_time: float,
    ) -> TseDiagnosticReport:
        """Deep deterministic triage of an employee review proposal."""
        from datetime import UTC, datetime

        stmt = (
            select(EmployeeReview)
            .where(EmployeeReview.id == review_id)
            .options(
                selectinload(EmployeeReview.employee),
                selectinload(EmployeeReview.cycle),
            )
        )
        res = await db.execute(stmt)
        review = res.scalars().first()

        if not review:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return TseDiagnosticReport(
                incident_id=incident_id,
                timestamp=datetime.now(UTC),
                trace_id=trace_id,
                entity_type="EMPLOYEE_REVIEW",
                entity_id=review_id,
                target_name=None,
                current_status=None,
                ledger_integrity=ledger_result,
                policy_findings=[],
                root_cause_category="REVIEW_NOT_FOUND",
                customer_summary=f"Employee review proposal {review_id} does not exist in the platform database.",
                technical_analysis=f"SQL query for review_id={review_id} returned 0 rows.",
                recommended_actions=[
                    "Verify proposal UUID",
                    "Confirm planning cycle has not been purged",
                ],
                execution_time_ms=round(duration_ms, 2),
            )

        emp = review.employee
        target_band = await BandService.get_band(
            db=db,
            job_level=review.proposed_job_level,
            job_family=emp.job_family,
            location_tier=emp.location_tier,
        )

        compa = calculate_compa_ratio(review.proposed_base, target_band.mid_base)
        findings: list[TseAuditFindingReport] = []

        # 1. Evaluate Salary Band Rule
        band_check = verify_salary_band_compliance(review.proposed_base, target_band)
        findings.append(
            TseAuditFindingReport(
                rule_name="salary_band_compliance",
                passed=band_check.passed,
                details=band_check.details,
                severity=band_check.severity,
            )
        )

        # 2. Check Department Budget Depletion
        budget_overrun = False
        budget_stmt = select(CycleBudget).where(
            CycleBudget.cycle_id == review.cycle_id,
            CycleBudget.department_id == emp.department_id,
        )
        b_res = await db.execute(budget_stmt)
        budget = b_res.scalars().first()
        if budget:
            merit_delta = max(Decimal("0.00"), review.proposed_base - review.current_base)
            remaining_merit = budget.allocated_merit_budget - budget.depleted_merit_budget
            if merit_delta > remaining_merit and remaining_merit < Decimal("0.00"):
                budget_overrun = True
                findings.append(
                    TseAuditFindingReport(
                        rule_name="department_budget_availability",
                        passed=False,
                        details=(
                            f"Department merit budget exceeded: allocated=${budget.allocated_merit_budget:,.2f}, "
                            f"depleted=${budget.depleted_merit_budget:,.2f}"
                        ),
                        severity="CRITICAL",
                    )
                )
            else:
                findings.append(
                    TseAuditFindingReport(
                        rule_name="department_budget_availability",
                        passed=True,
                        details=f"Budget remaining: ${remaining_merit:,.2f}",
                        severity="INFO",
                    )
                )

        # 3. Synthesize Root Cause & Recommendations
        actions: list[str] = []
        if not ledger_result.is_valid:
            root_cause = "CRITICAL_LEDGER_TAMPERING_DETECTED"
            summary = "CRITICAL: The SOX Section 404 audit ledger hash chain has been compromised."
            analysis = (
                f"Ledger sequence #{ledger_result.tampered_sequence_id} failed cryptographic verification: "
                f"{ledger_result.error_reason}. Historical compensation decisions cannot be verified."
            )
            actions = [
                "Escalate immediately to Platform Security & SRE Incident Response",
                "Freeze active compensation payout runs",
                "Compare audit table checksum against GCS offsite backup",
            ]
        elif not band_check.passed:
            if review.proposed_base > target_band.max_base:
                root_cause = "OUT_OF_BAND_COMPENSATION_CEILING"
                summary = (
                    f"Employee {emp.full_name}'s proposed base salary (${review.proposed_base:,.2f}) "
                    f"exceeds the level {review.proposed_job_level.value} maximum band ceiling (${target_band.max_base:,.2f}). "
                    f"Compa-ratio is {compa:.3f} (target: 1.000)."
                )
            else:
                root_cause = "OUT_OF_BAND_COMPENSATION_FLOOR"
                summary = (
                    f"Employee {emp.full_name}'s proposed base salary (${review.proposed_base:,.2f}) "
                    f"is below the level {review.proposed_job_level.value} minimum band floor (${target_band.min_base:,.2f})."
                )
            analysis = (
                f"Deterministic audit rejected automatic approval. Review transitioned to {review.status.value}. "
                f"Salary band mid-point: ${target_band.mid_base:,.2f}, span: [${target_band.min_base:,.2f} - ${target_band.max_base:,.2f}]."
            )
            actions = [
                "Obtain executive VP / Compensation Committee exception sign-off via `/api/v1/cycles/reviews/{id}/vp-approve`",
                f"Or adjust proposed base salary between ${target_band.min_base:,.2f} and ${target_band.max_base:,.2f}",
                "Review market benchmark percentiles for level and geo-tier",
            ]
        elif budget_overrun:
            root_cause = "DEPARTMENT_MERIT_BUDGET_EXHAUSTED"
            summary = "Department merit budget allocation has been depleted."
            analysis = "The total proposed salary adjustments in this cycle exceed the authorized departmental merit pool."
            actions = [
                "Request departmental budget reallocation from HR Admin",
                "Calibrate other employee merit increases to rebalance the pool",
            ]
        elif review.status == ReviewStatus.VP_EXCEPTION_REQUIRED:
            root_cause = "AWAITING_VP_EXCEPTION_APPROVAL"
            summary = f"Review for {emp.full_name} is awaiting executive sign-off."
            analysis = f"Review was flagged by policy rules: {review.audit_summary.get('rationale', 'Exception required') if review.audit_summary else 'Pending VP Approval'}."
            actions = [
                "Notify Department VP or Executive Approver to review the proposal dossier",
                "Ensure manager justification notes are comprehensive before approval",
            ]
        elif review.status == ReviewStatus.AUTO_APPROVED:
            root_cause = "HEALTHY_AUTO_APPROVED"
            summary = f"Review for {emp.full_name} is fully compliant and automatically approved."
            analysis = f"Compa-ratio {compa:.3f} is within guidelines. All deterministic policy rules passed."
            actions = [
                "No remediation required",
                "Proceed with scheduled cycle finalization",
            ]
        else:
            root_cause = f"STATUS_{review.status.value}"
            summary = f"Review is currently in {review.status.value} status."
            analysis = f"Current review state: {review.status.value}."
            actions = ["Inspect review workflow lifecycle history in audit logs"]

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return TseDiagnosticReport(
            incident_id=incident_id,
            timestamp=datetime.now(UTC),
            trace_id=trace_id,
            entity_type="EMPLOYEE_REVIEW",
            entity_id=review.id,
            target_name=emp.full_name,
            current_status=review.status.value,
            job_level=review.proposed_job_level.value,
            job_family=emp.job_family.value,
            location_tier=emp.location_tier.value,
            current_base=review.current_base,
            proposed_base=review.proposed_base,
            compa_ratio=compa,
            salary_band_mid=target_band.mid_base,
            ledger_integrity=ledger_result,
            policy_findings=findings,
            root_cause_category=root_cause,
            customer_summary=summary,
            technical_analysis=analysis,
            recommended_actions=actions,
            execution_time_ms=round(duration_ms, 2),
        )

    @classmethod
    async def _diagnose_candidate_offer(
        cls,
        db: AsyncSession,
        incident_id: UUID,
        offer_id: UUID,
        trace_id: str | None,
        ledger_result: Any,
        start_time: float,
    ) -> TseDiagnosticReport:
        """Deep deterministic triage of a candidate offer proposal."""
        from datetime import UTC, datetime

        stmt = select(CandidateOffer).where(CandidateOffer.id == offer_id)
        res = await db.execute(stmt)
        offer = res.scalars().first()

        if not offer:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return TseDiagnosticReport(
                incident_id=incident_id,
                timestamp=datetime.now(UTC),
                trace_id=trace_id,
                entity_type="CANDIDATE_OFFER",
                entity_id=offer_id,
                target_name=None,
                current_status=None,
                ledger_integrity=ledger_result,
                policy_findings=[],
                root_cause_category="OFFER_NOT_FOUND",
                customer_summary=f"Candidate offer {offer_id} does not exist in the platform database.",
                technical_analysis=f"SQL query for offer_id={offer_id} returned 0 rows.",
                recommended_actions=["Verify candidate offer UUID"],
                execution_time_ms=round(duration_ms, 2),
            )

        target_band = await BandService.get_band(
            db=db,
            job_level=offer.job_level,
            job_family=offer.job_family,
            location_tier=offer.location_tier,
        )

        compa = calculate_compa_ratio(offer.proposed_base, target_band.mid_base)
        band_check = verify_salary_band_compliance(offer.proposed_base, target_band)

        findings = [
            TseAuditFindingReport(
                rule_name="candidate_salary_band_compliance",
                passed=band_check.passed,
                details=band_check.details,
                severity=band_check.severity,
            )
        ]

        actions: list[str] = []
        if not ledger_result.is_valid:
            root_cause = "CRITICAL_LEDGER_TAMPERING_DETECTED"
            summary = "CRITICAL: The SOX audit ledger cryptographic chain has been compromised."
            analysis = f"Ledger sequence #{ledger_result.tampered_sequence_id} failed verification."
            actions = ["Escalate to security", "Freeze candidate offer issuance"]
        elif not band_check.passed:
            root_cause = "OUT_OF_BAND_CANDIDATE_OFFER"
            summary = (
                f"Candidate {offer.candidate_name}'s offer base (${offer.proposed_base:,.2f}) "
                f"is outside the target band for {offer.job_level.value}."
            )
            analysis = f"Compa-ratio {compa:.3f} violates standard hiring corridor [0.80 - 1.20]."
            actions = [
                "Obtain VP Exception approval via `/api/v1/offers/{id}/vp-approve`",
                f"Align offer base salary within [${target_band.min_base:,.2f} - ${target_band.max_base:,.2f}]",
            ]
        else:
            root_cause = f"OFFER_STATUS_{offer.status.value}"
            summary = f"Offer for {offer.candidate_name} is in {offer.status.value} status."
            analysis = f"Compa-ratio: {compa:.3f}, target mid: ${target_band.mid_base:,.2f}."
            actions = ["Follow standard recruiting pipeline steps"]

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return TseDiagnosticReport(
            incident_id=incident_id,
            timestamp=datetime.now(UTC),
            trace_id=trace_id,
            entity_type="CANDIDATE_OFFER",
            entity_id=offer.id,
            target_name=offer.candidate_name,
            current_status=offer.status.value,
            job_level=offer.job_level.value,
            job_family=offer.job_family.value,
            location_tier=offer.location_tier.value,
            current_base=None,
            proposed_base=offer.proposed_base,
            compa_ratio=compa,
            salary_band_mid=target_band.mid_base,
            ledger_integrity=ledger_result,
            policy_findings=findings,
            root_cause_category=root_cause,
            customer_summary=summary,
            technical_analysis=analysis,
            recommended_actions=actions,
            execution_time_ms=round(duration_ms, 2),
        )
