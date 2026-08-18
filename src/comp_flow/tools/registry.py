"""Deterministic Tool Registry for Compensation Auditing and Compliance."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from comp_flow.domain.models import (
    AuditFinding,
    JobLevel,
    PerformanceRating,
    SalaryBand,
)

# Standard Enterprise Benchmark Salary Bands
DEFAULT_SALARY_BANDS: dict[JobLevel, SalaryBand] = {
    JobLevel.L3: SalaryBand(
        job_level=JobLevel.L3,
        min_base=Decimal("140000.00"),
        mid_base=Decimal("165000.00"),
        max_base=Decimal("190000.00"),
        target_equity_gsus=400,
    ),
    JobLevel.L4: SalaryBand(
        job_level=JobLevel.L4,
        min_base=Decimal("170000.00"),
        mid_base=Decimal("200000.00"),
        max_base=Decimal("230000.00"),
        target_equity_gsus=650,
    ),
    JobLevel.L5: SalaryBand(
        job_level=JobLevel.L5,
        min_base=Decimal("210000.00"),
        mid_base=Decimal("250000.00"),
        max_base=Decimal("290000.00"),
        target_equity_gsus=900,
    ),
    JobLevel.L6: SalaryBand(
        job_level=JobLevel.L6,
        min_base=Decimal("260000.00"),
        mid_base=Decimal("310000.00"),
        max_base=Decimal("360000.00"),
        target_equity_gsus=1400,
    ),
    JobLevel.L7: SalaryBand(
        job_level=JobLevel.L7,
        min_base=Decimal("320000.00"),
        mid_base=Decimal("380000.00"),
        max_base=Decimal("440000.00"),
        target_equity_gsus=2200,
    ),
    JobLevel.L8: SalaryBand(
        job_level=JobLevel.L8,
        min_base=Decimal("400000.00"),
        mid_base=Decimal("480000.00"),
        max_base=Decimal("560000.00"),
        target_equity_gsus=3500,
    ),
}


def calculate_compa_ratio(proposed_base: Decimal, band: SalaryBand) -> Decimal:
    """Calculates compa-ratio (proposed_base / band.mid_base) with 3 decimal places."""
    raw_ratio = proposed_base / band.mid_base
    return raw_ratio.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def verify_salary_band_compliance(proposed_base: Decimal, band: SalaryBand) -> AuditFinding:
    """Verifies that proposed base salary falls strictly within internal salary band."""
    compa_ratio = calculate_compa_ratio(proposed_base, band)

    if proposed_base < band.min_base:
        return AuditFinding(
            check_name="SALARY_BAND_COMPLIANCE",
            passed=False,
            details=f"Proposed base ${proposed_base:,.2f} is below band minimum ${band.min_base:,.2f} (Compa-Ratio: {compa_ratio:.2f})",
            severity="WARNING",
        )

    if proposed_base > band.max_base:
        return AuditFinding(
            check_name="SALARY_BAND_COMPLIANCE",
            passed=False,
            details=f"Proposed base ${proposed_base:,.2f} exceeds band maximum ${band.max_base:,.2f} (Compa-Ratio: {compa_ratio:.2f})",
            severity="CRITICAL",
        )

    return AuditFinding(
        check_name="SALARY_BAND_COMPLIANCE",
        passed=True,
        details=f"Proposed base ${proposed_base:,.2f} is compliant within [{band.min_base:,.2f}, {band.max_base:,.2f}] (Compa-Ratio: {compa_ratio:.2f})",
        severity="INFO",
    )


def evaluate_equity_guidelines(
    proposed_gsus: int,
    band: SalaryBand,
    rating: PerformanceRating,
) -> AuditFinding:
    """Evaluates proposed GSU equity grant against target guidelines adjusted for performance."""
    target = band.target_equity_gsus

    # Multiplier ranges by performance rating
    rating_ranges: dict[PerformanceRating, tuple[Decimal, Decimal]] = {
        PerformanceRating.NEEDS_IMPROVEMENT: (Decimal("0.0"), Decimal("0.0")),
        PerformanceRating.CONSISTENTLY_MEETS: (Decimal("0.80"), Decimal("1.20")),
        PerformanceRating.EXCEEDS: (Decimal("1.10"), Decimal("1.45")),
        PerformanceRating.STRONGLY_OUTPERFORMS: (Decimal("1.35"), Decimal("1.80")),
        PerformanceRating.SUPERB: (Decimal("1.70"), Decimal("2.30")),
    }

    min_mult, max_mult = rating_ranges[rating]
    min_allowed = int(Decimal(target) * min_mult)
    max_allowed = int(Decimal(target) * max_mult)

    ratio = Decimal(proposed_gsus) / Decimal(target) if target > 0 else Decimal("0.0")

    if proposed_gsus < min_allowed:
        return AuditFinding(
            check_name="EQUITY_GUIDELINE_COMPLIANCE",
            passed=False,
            details=f"Proposed {proposed_gsus:,d} GSUs is below allowable range [{min_allowed:,d}, {max_allowed:,d}] for {rating.value} (Target: {target:,d})",
            severity="WARNING",
        )

    if proposed_gsus > max_allowed:
        return AuditFinding(
            check_name="EQUITY_GUIDELINE_COMPLIANCE",
            passed=False,
            details=f"Proposed {proposed_gsus:,d} GSUs exceeds allowable maximum {max_allowed:,d} for {rating.value} (Target: {target:,d}, Ratio: {ratio:.2f}x)",
            severity="CRITICAL",
        )

    return AuditFinding(
        check_name="EQUITY_GUIDELINE_COMPLIANCE",
        passed=True,
        details=f"Proposed {proposed_gsus:,d} GSUs is within guidelines [{min_allowed:,d}, {max_allowed:,d}] for {rating.value} ({ratio:.2f}x of target)",
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
