"""Compensation Calibration Agent Orchestrator."""

from __future__ import annotations

import time
from decimal import Decimal

from comp_flow.domain.models import (
    AgentAuditResult,
    AuditFinding,
    CompensationReviewProposal,
    JobLevel,
    PerformanceRating,
    ReviewStatus,
    SalaryBand,
)
from comp_flow.tools.registry import (
    DEFAULT_SALARY_BANDS,
    calculate_compa_ratio,
    evaluate_base_increase_velocity,
    evaluate_equity_guidelines,
    verify_salary_band_compliance,
)


class CompensationCalibrationAgent:
    """Autonomous Agent executing multi-step compliance audits and calibration synthesis."""

    def __init__(
        self,
        salary_bands: dict[JobLevel, SalaryBand] | None = None,
    ) -> None:
        """Initializes agent with organization salary benchmark bands."""
        self.salary_bands = salary_bands or DEFAULT_SALARY_BANDS

    def audit_proposal(
        self,
        proposal: CompensationReviewProposal,
    ) -> AgentAuditResult:
        """Executes the autonomous ReAct audit loop over a compensation review proposal.

        Steps:
        1. Tool: Retrieve Salary Band & Calculate Compa-Ratio.
        2. Tool: Verify Base Salary Band Compliance.
        3. Tool: Evaluate Equity Guidelines against Performance Rating.
        4. Tool: Evaluate Base Salary Increase Velocity.
        5. Synthesize: Formulate decision (AUTO_APPROVED vs VP_EXCEPTION_REQUIRED vs REJECTED).
        """
        t0 = time.perf_counter()

        band = self.salary_bands.get(proposal.job_level)
        if not band:
            elapsed = time.perf_counter() - t0
            return AgentAuditResult(
                review_id=proposal.review_id,
                decision=ReviewStatus.REJECTED,
                findings=[
                    AuditFinding(
                        check_name="BAND_LOOKUP",
                        passed=False,
                        details=f"No salary band benchmark configured for job level {proposal.job_level}",
                        severity="CRITICAL",
                    )
                ],
                compa_ratio=Decimal("0.000"),
                equity_guideline_ratio=Decimal("0.00"),
                rationale="Audit failed: missing salary band benchmark.",
                execution_time_seconds=elapsed,
            )

        # 1. Calculate ratios
        compa_ratio = calculate_compa_ratio(proposal.proposed_base, band)
        equity_ratio = (
            Decimal(proposal.proposed_equity_gsus) / Decimal(band.target_equity_gsus)
            if band.target_equity_gsus > 0
            else Decimal("0.00")
        )

        # 2. Invoke Audit Tools
        findings: list[AuditFinding] = []

        base_finding = verify_salary_band_compliance(proposal.proposed_base, band)
        findings.append(base_finding)

        equity_finding = evaluate_equity_guidelines(
            proposal.proposed_equity_gsus,
            band,
            proposal.performance_rating,
        )
        findings.append(equity_finding)

        velocity_finding = evaluate_base_increase_velocity(
            proposal.current_base,
            proposal.proposed_base,
            proposal.performance_rating,
        )
        findings.append(velocity_finding)

        # 3. Synthesize Decision & Action
        critical_violations = [f for f in findings if f.severity == "CRITICAL" and not f.passed]
        warnings = [f for f in findings if f.severity == "WARNING" and not f.passed]

        # Policy: Needs improvement with pay increase -> Hard Reject
        if (
            proposal.performance_rating == PerformanceRating.NEEDS_IMPROVEMENT
            and proposal.proposed_base > proposal.current_base
        ):
            decision = ReviewStatus.REJECTED
            rationale = (
                f"REJECTED: Employee rated {proposal.performance_rating.value} is ineligible for "
                f"base salary increases under corporate governance policy."
            )
        elif critical_violations or warnings:
            decision = ReviewStatus.VP_EXCEPTION_REQUIRED
            issue_descriptions = [f.details for f in (critical_violations + warnings)]
            rationale = (
                f"ESCALATED TO VP COMMITTEE: Proposal contains {len(issue_descriptions)} non-standard "
                f"deviations requiring executive approval: {'; '.join(issue_descriptions)}."
            )
        else:
            decision = ReviewStatus.AUTO_APPROVED
            rationale = (
                f"AUTO-APPROVED: Proposal satisfies all salary band limits (Compa-Ratio: {compa_ratio:.2f}), "
                f"equity guidelines ({equity_ratio:.2f}x of target for {proposal.performance_rating.value}), "
                f"and merit velocity caps."
            )

        elapsed = time.perf_counter() - t0

        return AgentAuditResult(
            review_id=proposal.review_id,
            decision=decision,
            findings=findings,
            compa_ratio=compa_ratio,
            equity_guideline_ratio=equity_ratio,
            rationale=rationale,
            execution_time_seconds=elapsed,
        )
