"""Deterministic Mathematical Tool Registry for Total Rewards and Candidate Offers."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from comp_flow.domain.models import (
    AuditFinding,
    JobFamily,
    JobLevel,
    LocationTier,
    PerformanceRating,
    SalaryBandBase,
)

# Standard Multipliers for Equity Refreshes based on Performance Rating
EQUITY_PERFORMANCE_MULTIPLIERS: dict[PerformanceRating, tuple[Decimal, Decimal]] = {
    PerformanceRating.NEEDS_IMPROVEMENT: (Decimal("0.0"), Decimal("0.0")),
    PerformanceRating.CONSISTENTLY_MEETS: (Decimal("0.80"), Decimal("1.20")),
    PerformanceRating.EXCEEDS: (Decimal("1.10"), Decimal("1.45")),
    PerformanceRating.STRONGLY_OUTPERFORMS: (Decimal("1.35"), Decimal("1.80")),
    PerformanceRating.SUPERB: (Decimal("1.70"), Decimal("2.30")),
}

# Location Tier Cost of Labor Adjustment Factors
GEO_FACTORS: dict[LocationTier, Decimal] = {
    LocationTier.US_ZONE_1: Decimal("1.00"),  # SF Bay Area, NYC (100% Benchmark)
    LocationTier.US_ZONE_2: Decimal("0.90"),  # Seattle, Austin (90% Benchmark)
    LocationTier.US_ZONE_3: Decimal("0.80"),  # Remote / National (80% Benchmark)
}

# Standard Base Salary Benchmarks for Zone 1 Software Engineering
DEFAULT_ZONE_1_BENCHMARKS: dict[JobLevel, tuple[Decimal, Decimal, Decimal, int, Decimal]] = {
    JobLevel.L3: (
        Decimal("140000.00"),
        Decimal("165000.00"),
        Decimal("190000.00"),
        400,
        Decimal("10.00"),
    ),
    JobLevel.L4: (
        Decimal("170000.00"),
        Decimal("200000.00"),
        Decimal("230000.00"),
        650,
        Decimal("15.00"),
    ),
    JobLevel.L5: (
        Decimal("210000.00"),
        Decimal("250000.00"),
        Decimal("290000.00"),
        900,
        Decimal("15.00"),
    ),
    JobLevel.L6: (
        Decimal("260000.00"),
        Decimal("310000.00"),
        Decimal("360000.00"),
        1400,
        Decimal("20.00"),
    ),
    JobLevel.L7: (
        Decimal("320000.00"),
        Decimal("380000.00"),
        Decimal("440000.00"),
        2200,
        Decimal("25.00"),
    ),
    JobLevel.L8: (
        Decimal("400000.00"),
        Decimal("480000.00"),
        Decimal("560000.00"),
        3500,
        Decimal("30.00"),
    ),
}


def get_default_salary_band(
    job_level: JobLevel,
    job_family: JobFamily = JobFamily.SOFTWARE_ENGINEERING,
    location_tier: LocationTier = LocationTier.US_ZONE_1,
) -> SalaryBandBase:
    """Generates standard benchmark salary band adjusted for geographic cost of labor."""
    min_base, mid_base, max_base, target_equity, target_bonus_pct = DEFAULT_ZONE_1_BENCHMARKS[
        job_level
    ]
    geo_factor = GEO_FACTORS.get(location_tier, Decimal("1.00"))

    adjusted_min = (min_base * geo_factor).quantize(Decimal("100.00"), rounding=ROUND_HALF_UP)
    adjusted_mid = (mid_base * geo_factor).quantize(Decimal("100.00"), rounding=ROUND_HALF_UP)
    adjusted_max = (max_base * geo_factor).quantize(Decimal("100.00"), rounding=ROUND_HALF_UP)

    return SalaryBandBase(
        job_level=job_level,
        job_family=job_family,
        location_tier=location_tier,
        min_base=adjusted_min,
        mid_base=adjusted_mid,
        max_base=adjusted_max,
        target_equity_rsus=target_equity,
        target_bonus_pct=target_bonus_pct,
    )


def calculate_compa_ratio(proposed_base: Decimal, mid_base: Decimal) -> Decimal:
    """Calculates compa-ratio (proposed_base / mid_base) with 3 decimal precision."""
    if mid_base <= Decimal("0.00"):
        return Decimal("1.000")
    raw_ratio = proposed_base / mid_base
    return raw_ratio.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def verify_salary_band_compliance(
    proposed_base: Decimal,
    band: SalaryBandBase,
) -> AuditFinding:
    """Verifies that proposed base salary falls within the internal salary band."""
    compa = calculate_compa_ratio(proposed_base, band.mid_base)

    if proposed_base < band.min_base:
        return AuditFinding(
            check_name="SALARY_BAND_COMPLIANCE",
            passed=False,
            details=(
                f"Proposed base ${proposed_base:,.2f} is below band minimum "
                f"${band.min_base:,.2f} (Compa-Ratio: {compa:.3f})"
            ),
            severity="WARNING",
        )

    if proposed_base > band.max_base:
        return AuditFinding(
            check_name="SALARY_BAND_COMPLIANCE",
            passed=False,
            details=(
                f"Proposed base ${proposed_base:,.2f} exceeds band maximum "
                f"${band.max_base:,.2f} (Compa-Ratio: {compa:.3f})"
            ),
            severity="CRITICAL",
        )

    return AuditFinding(
        check_name="SALARY_BAND_COMPLIANCE",
        passed=True,
        details=(
            f"Proposed base ${proposed_base:,.2f} is compliant within "
            f"[${band.min_base:,.2f}, ${band.max_base:,.2f}] (Compa-Ratio: {compa:.3f})"
        ),
        severity="INFO",
    )


def calculate_target_bonus_amount(
    proposed_base: Decimal,
    target_bonus_pct: Decimal,
    individual_perf_factor: Decimal = Decimal("1.00"),
    company_perf_factor: Decimal = Decimal("1.00"),
) -> Decimal:
    """Calculates standard annual bonus: Base * (Target% / 100) * IPF * CPF."""
    base_bonus = proposed_base * (target_bonus_pct / Decimal("100.0"))
    final_bonus = base_bonus * individual_perf_factor * company_perf_factor
    return final_bonus.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def evaluate_bonus_compliance(
    proposed_bonus: Decimal,
    proposed_base: Decimal,
    target_bonus_pct: Decimal,
    individual_perf_factor: Decimal,
    company_perf_factor: Decimal,
) -> AuditFinding:
    """Audits proposed bonus payout against the formula target."""
    target_amount = calculate_target_bonus_amount(
        proposed_base, target_bonus_pct, individual_perf_factor, company_perf_factor
    )
    deviation = (
        abs(proposed_bonus - target_amount) / target_amount * Decimal("100.0")
        if target_amount > Decimal("0.00")
        else Decimal("0.0")
    )

    if deviation > Decimal("25.0"):
        return AuditFinding(
            check_name="BONUS_FORMULA_COMPLIANCE",
            passed=False,
            details=(
                f"Proposed bonus ${proposed_bonus:,.2f} deviates {deviation:.1f}% from "
                f"formula target ${target_amount:,.2f} (Target: {target_bonus_pct}%, "
                f"IPF: {individual_perf_factor}x, CPF: {company_perf_factor}x)"
            ),
            severity="WARNING",
        )

    return AuditFinding(
        check_name="BONUS_FORMULA_COMPLIANCE",
        passed=True,
        details=(
            f"Proposed bonus ${proposed_bonus:,.2f} aligns with formula target "
            f"${target_amount:,.2f} (IPF: {individual_perf_factor}x, CPF: {company_perf_factor}x)"
        ),
        severity="INFO",
    )


def evaluate_equity_guidelines(
    proposed_rsus: int = 0,
    band: SalaryBandBase = None,  # type: ignore[assignment]
    rating: PerformanceRating = PerformanceRating.CONSISTENTLY_MEETS,
    **kwargs: Any,
) -> AuditFinding:
    """Evaluates proposed RSU equity grant against target guidelines adjusted for performance."""
    if "proposed_gsus" in kwargs and not proposed_rsus:
        proposed_rsus = int(kwargs["proposed_gsus"])
    target = band.target_equity_rsus
    min_mult, max_mult = EQUITY_PERFORMANCE_MULTIPLIERS[rating]
    min_allowed = int(Decimal(target) * min_mult)
    max_allowed = int(Decimal(target) * max_mult)

    ratio = Decimal(proposed_rsus) / Decimal(target) if target > 0 else Decimal("0.0")

    if proposed_rsus < min_allowed:
        return AuditFinding(
            check_name="EQUITY_GUIDELINE_COMPLIANCE",
            passed=False,
            details=(
                f"Proposed {proposed_rsus:,d} RSUs is below allowable range "
                f"[{min_allowed:,d}, {max_allowed:,d}] for {rating.value} (Target: {target:,d})"
            ),
            severity="WARNING",
        )

    if proposed_rsus > max_allowed:
        return AuditFinding(
            check_name="EQUITY_GUIDELINE_COMPLIANCE",
            passed=False,
            details=(
                f"Proposed {proposed_rsus:,d} RSUs exceeds allowable maximum "
                f"{max_allowed:,d} for {rating.value} (Target: {target:,d}, Ratio: {ratio:.2f}x)"
            ),
            severity="CRITICAL",
        )

    return AuditFinding(
        check_name="EQUITY_GUIDELINE_COMPLIANCE",
        passed=True,
        details=(
            f"Proposed {proposed_rsus:,d} RSUs is within guidelines "
            f"[{min_allowed:,d}, {max_allowed:,d}] for {rating.value} ({ratio:.2f}x of target)"
        ),
        severity="INFO",
    )


def evaluate_base_increase_velocity(
    current_base: Decimal,
    proposed_base: Decimal,
    rating: PerformanceRating,
) -> AuditFinding:
    """Verifies that base salary increase percentage aligns with policy caps."""
    if current_base <= Decimal("0.00"):
        return AuditFinding(
            check_name="INCREASE_VELOCITY",
            passed=True,
            details="New hire / zero baseline",
            severity="INFO",
        )

    increase_pct = (proposed_base - current_base) / current_base * Decimal("100.0")

    if rating == PerformanceRating.NEEDS_IMPROVEMENT and proposed_base > current_base:
        return AuditFinding(
            check_name="INCREASE_VELOCITY",
            passed=False,
            details=f"Salary increases not permitted for rating {rating.value} (+{increase_pct:.1f}%)",
            severity="CRITICAL",
        )

    if increase_pct > Decimal("20.0"):
        return AuditFinding(
            check_name="INCREASE_VELOCITY",
            passed=False,
            details=f"Increase velocity +{increase_pct:.1f}% exceeds standard annual cap (+20.0%)",
            severity="CRITICAL",
        )

    return AuditFinding(
        check_name="INCREASE_VELOCITY",
        passed=True,
        details=f"Increase velocity +{increase_pct:.1f}% is within normal merit bounds",
        severity="INFO",
    )


def evaluate_promotion_compliance(
    current_level: JobLevel,
    proposed_level: JobLevel,
    proposed_base: Decimal,
    new_band: SalaryBandBase,
) -> AuditFinding:
    """Verifies promotion eligibility and minimum base salary placement for new level."""
    levels = list(JobLevel)
    current_idx = levels.index(current_level)
    proposed_idx = levels.index(proposed_level)

    if proposed_idx < current_idx:
        return AuditFinding(
            check_name="PROMOTION_COMPLIANCE",
            passed=False,
            details=f"Proposed level {proposed_level.value} represents a demotion from {current_level.value}",
            severity="WARNING",
        )

    if proposed_idx > current_idx + 1:
        return AuditFinding(
            check_name="PROMOTION_COMPLIANCE",
            passed=False,
            details=f"Multi-level jump from {current_level.value} to {proposed_level.value} requires VP exception",
            severity="WARNING",
        )

    if proposed_idx > current_idx and proposed_base < new_band.min_base:
        return AuditFinding(
            check_name="PROMOTION_COMPLIANCE",
            passed=False,
            details=(
                f"Promoted base ${proposed_base:,.2f} is below minimum for "
                f"new level {proposed_level.value} (${new_band.min_base:,.2f})"
            ),
            severity="CRITICAL",
        )

    return AuditFinding(
        check_name="PROMOTION_COMPLIANCE",
        passed=True,
        details=f"Level placement {proposed_level.value} is compliant",
        severity="INFO",
    )


def evaluate_candidate_offer_compliance(
    proposed_base: Decimal,
    sign_on_bonus: Decimal,
    proposed_equity_rsus: int = 0,
    band: SalaryBandBase = None,  # type: ignore[assignment]
    **kwargs: Any,
) -> list[AuditFinding]:
    """Runs compliance checks on candidate new hire offer package."""
    if "proposed_equity_gsus" in kwargs and not proposed_equity_rsus:
        proposed_equity_rsus = int(kwargs["proposed_equity_gsus"])

    findings: list[AuditFinding] = []

    # 1. Base Salary Band Check
    base_check = verify_salary_band_compliance(proposed_base, band)
    findings.append(base_check)

    # 2. Sign-on Bonus Cap Check ($50,000 threshold)
    if sign_on_bonus > Decimal("50000.00"):
        findings.append(
            AuditFinding(
                check_name="SIGN_ON_BONUS_CAP",
                passed=False,
                details=f"Sign-on bonus ${sign_on_bonus:,.2f} exceeds standard $50,000.00 cap",
                severity="CRITICAL",
            )
        )
    else:
        findings.append(
            AuditFinding(
                check_name="SIGN_ON_BONUS_CAP",
                passed=True,
                details=f"Sign-on bonus ${sign_on_bonus:,.2f} is within policy cap",
                severity="INFO",
            )
        )

    # 3. New Hire Equity Grant Cap (1.5x of annual target)
    max_new_hire_equity = int(Decimal(band.target_equity_rsus) * Decimal("1.50"))
    if proposed_equity_rsus > max_new_hire_equity:
        findings.append(
            AuditFinding(
                check_name="NEW_HIRE_EQUITY_CAP",
                passed=False,
                details=(
                    f"Proposed equity {proposed_equity_rsus:,d} RSUs exceeds new hire cap "
                    f"{max_new_hire_equity:,d} (Target: {band.target_equity_rsus:,d})"
                ),
                severity="CRITICAL",
            )
        )
    else:
        findings.append(
            AuditFinding(
                check_name="NEW_HIRE_EQUITY_CAP",
                passed=True,
                details=f"Proposed equity {proposed_equity_rsus:,d} RSUs is within new hire guidelines",
                severity="INFO",
            )
        )

    return findings


def calculate_offer_total_comp(
    proposed_base: Decimal,
    sign_on_bonus: Decimal,
    target_bonus_pct: Decimal,
    proposed_equity_rsus: int = 0,
    estimated_rsu_price: Decimal = Decimal("150.00"),
    **kwargs: Any,
) -> dict[str, Decimal]:
    """Calculates Total Target Cash and First Year Total Direct Comp for an offer."""
    if "proposed_equity_gsus" in kwargs and not proposed_equity_rsus:
        proposed_equity_rsus = int(kwargs["proposed_equity_gsus"])
    if "estimated_gsu_price" in kwargs:
        estimated_rsu_price = Decimal(str(kwargs["estimated_gsu_price"]))

    target_bonus = (proposed_base * target_bonus_pct / Decimal("100.0")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    total_target_cash = proposed_base + target_bonus

    # Standard Year 1 Front-loaded equity tranche (33.33%)
    year_1_equity_val = (
        Decimal(proposed_equity_rsus) * Decimal("0.33333333") * estimated_rsu_price
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    first_year_total_comp = proposed_base + sign_on_bonus + target_bonus + year_1_equity_val

    return {
        "target_bonus": target_bonus,
        "total_target_cash": total_target_cash,
        "first_year_total_comp": first_year_total_comp,
    }


def evaluate_market_benchmark_positioning(
    proposed_base: Decimal,
    p10_base: Decimal,
    p50_base: Decimal,
    p90_base: Decimal,
) -> AuditFinding:
    """Evaluates proposed base salary against market percentiles (P10, P50, P90)."""
    compa_ratio = (proposed_base / p50_base).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    if proposed_base < p10_base:
        return AuditFinding(
            check_name="MARKET_BENCHMARK_ALIGNMENT",
            passed=False,
            details=f"Proposed base ${proposed_base:,.2f} is below market 10th percentile (${p10_base:,.2f}, Market Compa: {compa_ratio})",
            severity="WARNING",
        )
    elif proposed_base > p90_base:
        return AuditFinding(
            check_name="MARKET_BENCHMARK_ALIGNMENT",
            passed=False,
            details=f"Proposed base ${proposed_base:,.2f} exceeds market 90th percentile (${p90_base:,.2f}, Market Compa: {compa_ratio})",
            severity="WARNING",
        )
    return AuditFinding(
        check_name="MARKET_BENCHMARK_ALIGNMENT",
        passed=True,
        details=f"Proposed base ${proposed_base:,.2f} is aligned with market P10-P90 range (Market Compa: {compa_ratio})",
        severity="INFO",
    )
