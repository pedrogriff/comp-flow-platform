"""Autonomous Agent Orchestrators for Employee Calibration and Candidate Offers."""

from __future__ import annotations

import time
from decimal import Decimal

from comp_flow.domain.models import (
    AgentAuditResult,
    AuditFinding,
    JobFamily,
    JobLevel,
    LocationTier,
    OfferStatus,
    PerformanceRating,
    ReviewStatus,
    SalaryBandBase,
)
from comp_flow.tools.registry import (
    calculate_compa_ratio,
    calculate_offer_total_comp,
    evaluate_base_increase_velocity,
    evaluate_bonus_compliance,
    evaluate_candidate_offer_compliance,
    evaluate_equity_guidelines,
    evaluate_promotion_compliance,
    get_default_salary_band,
    verify_salary_band_compliance,
)


class EmployeeCalibrationAgent:
    """Deterministic agent auditing employee compensation review proposals."""

    def audit_review_proposal(
        self,
        review_id: str,
        current_level: JobLevel,
        proposed_level: JobLevel,
        job_family: JobFamily,
        location_tier: LocationTier,
        current_base: Decimal,
        proposed_base: Decimal,
        proposed_bonus: Decimal,
        individual_perf_factor: Decimal,
        company_perf_factor: Decimal,
        proposed_equity_gsus: int,
        performance_rating: PerformanceRating,
        band: SalaryBandBase | None = None,
    ) -> AgentAuditResult:
        """Audits proposed merit, bonus, equity, and promotion against internal benchmarks."""
        t0 = time.perf_counter()

        target_band = band or get_default_salary_band(proposed_level, job_family, location_tier)
        compa_ratio = calculate_compa_ratio(proposed_base, target_band.mid_base)
        equity_ratio = (
            Decimal(proposed_equity_gsus) / Decimal(target_band.target_equity_gsus)
            if target_band.target_equity_gsus > 0
            else Decimal("0.00")
        )

        findings: list[AuditFinding] = []

        # 1. Base Salary Band Compliance
        findings.append(verify_salary_band_compliance(proposed_base, target_band))

        # 2. Bonus Formula Compliance
        findings.append(
            evaluate_bonus_compliance(
                proposed_bonus=proposed_bonus,
                proposed_base=proposed_base,
                target_bonus_pct=target_band.target_bonus_pct,
                individual_perf_factor=individual_perf_factor,
                company_perf_factor=company_perf_factor,
            )
        )

        # 3. Equity Guideline Compliance
        findings.append(
            evaluate_equity_guidelines(
                proposed_gsus=proposed_equity_gsus,
                band=target_band,
                rating=performance_rating,
            )
        )

        # 4. Base Increase Velocity Compliance
        findings.append(
            evaluate_base_increase_velocity(
                current_base=current_base,
                proposed_base=proposed_base,
                rating=performance_rating,
            )
        )

        # 5. Promotion Compliance (if level changed)
        if current_level != proposed_level:
            findings.append(
                evaluate_promotion_compliance(
                    current_level=current_level,
                    proposed_level=proposed_level,
                    proposed_base=proposed_base,
                    new_band=target_band,
                )
            )

        # Synthesis & Action
        critical_violations = [f for f in findings if f.severity == "CRITICAL" and not f.passed]
        warnings = [f for f in findings if f.severity == "WARNING" and not f.passed]

        # Policy: Needs improvement rating with salary increase -> Hard REJECT
        if (
            performance_rating == PerformanceRating.NEEDS_IMPROVEMENT
            and proposed_base > current_base
        ):
            decision = ReviewStatus.REJECTED.value
            rationale = (
                f"REJECTED: Employee rated {performance_rating.value} is ineligible for "
                f"base salary increases under corporate governance policy."
            )
        elif critical_violations or warnings:
            decision = ReviewStatus.VP_EXCEPTION_REQUIRED.value
            issues = [f.details for f in (critical_violations + warnings)]
            rationale = (
                f"ESCALATED TO VP COMMITTEE: Proposal contains {len(issues)} exception item(s) "
                f"requiring approval: {'; '.join(issues)}."
            )
        else:
            decision = ReviewStatus.AUTO_APPROVED.value
            rationale = (
                f"AUTO-APPROVED: Proposal fully satisfies salary band parity (Compa: {compa_ratio:.3f}), "
                f"bonus formula, equity guidelines ({equity_ratio:.2f}x of target for {performance_rating.value}), "
                f"and merit velocity caps."
            )

        elapsed = time.perf_counter() - t0

        return AgentAuditResult(
            target_id=review_id,
            decision=decision,
            findings=findings,
            compa_ratio=compa_ratio,
            equity_guideline_ratio=equity_ratio,
            rationale=rationale,
            execution_time_seconds=elapsed,
        )


class OfferApprovalAgent:
    """Deterministic agent auditing candidate new hire offer proposals."""

    def audit_offer_package(
        self,
        offer_id: str,
        job_level: JobLevel,
        job_family: JobFamily,
        location_tier: LocationTier,
        proposed_base: Decimal,
        sign_on_bonus: Decimal,
        proposed_equity_gsus: int,
        band: SalaryBandBase | None = None,
    ) -> AgentAuditResult:
        """Audits candidate offer package against location-tiered bands and sign-on/equity caps."""
        t0 = time.perf_counter()

        target_band = band or get_default_salary_band(job_level, job_family, location_tier)
        compa_ratio = calculate_compa_ratio(proposed_base, target_band.mid_base)
        equity_ratio = (
            Decimal(proposed_equity_gsus) / Decimal(target_band.target_equity_gsus)
            if target_band.target_equity_gsus > 0
            else Decimal("0.00")
        )

        findings = evaluate_candidate_offer_compliance(
            proposed_base=proposed_base,
            sign_on_bonus=sign_on_bonus,
            proposed_equity_gsus=proposed_equity_gsus,
            band=target_band,
        )

        critical_violations = [f for f in findings if f.severity == "CRITICAL" and not f.passed]
        warnings = [f for f in findings if f.severity == "WARNING" and not f.passed]

        if (
            compa_ratio > Decimal("1.200")
            or sign_on_bonus > Decimal("50000.00")
            or critical_violations
        ):
            decision = OfferStatus.VP_EXCEPTION_REQUIRED.value
            issues = [f.details for f in (critical_violations + warnings)]
            rationale = (
                f"VP EXCEPTION REQUIRED: Candidate offer package exceeds standard parameters: "
                f"{'; '.join(issues) if issues else 'Compa-ratio > 1.20 or sign-on > $50k'}."
            )
        elif warnings:
            decision = OfferStatus.VP_EXCEPTION_REQUIRED.value
            issues = [f.details for f in warnings]
            rationale = f"VP EXCEPTION REQUIRED: {'; '.join(issues)}."
        else:
            decision = OfferStatus.OFFER_APPROVED.value
            totals = calculate_offer_total_comp(
                proposed_base=proposed_base,
                sign_on_bonus=sign_on_bonus,
                target_bonus_pct=target_band.target_bonus_pct,
                proposed_equity_gsus=proposed_equity_gsus,
            )
            rationale = (
                f"OFFER APPROVED: Package complies with {job_level.value} {location_tier.value} guidelines "
                f"(Compa-Ratio: {compa_ratio:.3f}, TTC: ${totals['total_target_cash']:,.2f}, "
                f"First Year Total Comp: ${totals['first_year_total_comp']:,.2f})."
            )

        elapsed = time.perf_counter() - t0

        return AgentAuditResult(
            target_id=offer_id,
            decision=decision,
            findings=findings,
            compa_ratio=compa_ratio,
            equity_guideline_ratio=equity_ratio,
            rationale=rationale,
            execution_time_seconds=elapsed,
        )
