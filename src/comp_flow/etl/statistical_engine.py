"""Statistical Engine for Outlier Pruning, Percentiles, Survey Aging, and Monotonic Smoothing."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from comp_flow.domain.benchmarks import BenchmarkPercentiles


class BenchmarkStatisticalEngine:
    """Calculates non-parametric percentiles, survey aging, and outlier pruning."""

    MIN_SAFE_HARBOR_COUNT = 5  # Department of Justice / FTC Antitrust Safe Harbor requirement
    DEFAULT_ANNUAL_AGING_RATE = Decimal("0.0400")  # 4.0% annual wage movement index

    @classmethod
    def filter_outliers_iqr(cls, wages: Sequence[Decimal | float]) -> list[Decimal]:
        """Filters extreme outliers using Tukey's Interquartile Range (IQR) method."""
        sorted_wages = sorted(Decimal(str(w)) for w in wages if Decimal(str(w)) >= Decimal("40000"))
        n = len(sorted_wages)

        if n < 4:
            return sorted_wages

        q1 = cls._calculate_single_percentile(sorted_wages, 25.0)
        q3 = cls._calculate_single_percentile(sorted_wages, 75.0)
        iqr = q3 - q1

        lower_bound = max(Decimal("40000"), q1 - (Decimal("1.5") * iqr))
        upper_bound = min(Decimal("1500000"), q3 + (Decimal("1.5") * iqr))

        return [w for w in sorted_wages if lower_bound <= w <= upper_bound]

    @classmethod
    def calculate_percentiles(cls, wages: Sequence[Decimal | float]) -> BenchmarkPercentiles:
        """Calculates P10, P25, P50 (Median), P75, and P90 percentiles from cleaned observations."""
        cleaned = cls.filter_outliers_iqr(wages)
        n = len(cleaned)

        if n == 0:
            return BenchmarkPercentiles(
                p10_base=Decimal("0.00"),
                p25_base=Decimal("0.00"),
                p50_base=Decimal("0.00"),
                p75_base=Decimal("0.00"),
                p90_base=Decimal("0.00"),
                sample_size=0,
            )

        p10 = cls._calculate_single_percentile(cleaned, 10.0)
        p25 = cls._calculate_single_percentile(cleaned, 25.0)
        p50 = cls._calculate_single_percentile(cleaned, 50.0)
        p75 = cls._calculate_single_percentile(cleaned, 75.0)
        p90 = cls._calculate_single_percentile(cleaned, 90.0)

        return BenchmarkPercentiles(
            p10_base=p10.quantize(Decimal("0.01")),
            p25_base=p25.quantize(Decimal("0.01")),
            p50_base=p50.quantize(Decimal("0.01")),
            p75_base=p75.quantize(Decimal("0.01")),
            p90_base=p90.quantize(Decimal("0.01")),
            sample_size=n,
        )

    @classmethod
    def age_wage_dataset(
        cls,
        percentiles: BenchmarkPercentiles,
        effective_date: date,
        target_date: date,
        annual_rate: Decimal | None = None,
    ) -> BenchmarkPercentiles:
        """Ages historical survey/LCA percentiles forward using compound market movement inflation.

        Formula: Wage_aged = Wage_effective * (1 + r) ^ (days / 365.25)
        """
        rate = annual_rate if annual_rate is not None else cls.DEFAULT_ANNUAL_AGING_RATE
        days_diff = (target_date - effective_date).days

        if days_diff <= 0:
            return percentiles

        time_years = Decimal(str(days_diff)) / Decimal("365.25")
        # Growth multiplier: (1 + r)^t
        multiplier = Decimal(str(math.pow(float(Decimal("1.0") + rate), float(time_years))))

        return BenchmarkPercentiles(
            p10_base=(percentiles.p10_base * multiplier).quantize(Decimal("0.01")),
            p25_base=(percentiles.p25_base * multiplier).quantize(Decimal("0.01")),
            p50_base=(percentiles.p50_base * multiplier).quantize(Decimal("0.01")),
            p75_base=(percentiles.p75_base * multiplier).quantize(Decimal("0.01")),
            p90_base=(percentiles.p90_base * multiplier).quantize(Decimal("0.01")),
            target_bonus_pct=percentiles.target_bonus_pct,
            p50_equity_gsus=percentiles.p50_equity_gsus,
            p75_equity_gsus=percentiles.p75_equity_gsus,
            sample_size=percentiles.sample_size,
        )

    @classmethod
    def smooth_level_monotonicity(
        cls, level_percentiles: dict[str, BenchmarkPercentiles]
    ) -> dict[str, BenchmarkPercentiles]:
        """Ensures monotonic progression across seniority levels (L3 -> L8).

        Guarantees that senior levels are never priced lower than junior levels due to small cohort sampling.
        """
        ordered_levels = ["L3", "L4", "L5", "L6", "L7", "L8"]
        smoothed: dict[str, BenchmarkPercentiles] = {}
        prev_p50 = Decimal("0.00")

        for lvl in ordered_levels:
            if lvl not in level_percentiles:
                continue

            curr = level_percentiles[lvl]
            if curr.p50_base < prev_p50:
                # Adjust midpoint and dependent percentiles proportionally
                adjustment_ratio = (prev_p50 * Decimal("1.05")) / max(curr.p50_base, Decimal("1.0"))
                curr = BenchmarkPercentiles(
                    p10_base=(curr.p10_base * adjustment_ratio).quantize(Decimal("0.01")),
                    p25_base=(curr.p25_base * adjustment_ratio).quantize(Decimal("0.01")),
                    p50_base=(curr.p50_base * adjustment_ratio).quantize(Decimal("0.01")),
                    p75_base=(curr.p75_base * adjustment_ratio).quantize(Decimal("0.01")),
                    p90_base=(curr.p90_base * adjustment_ratio).quantize(Decimal("0.01")),
                    target_bonus_pct=curr.target_bonus_pct,
                    p50_equity_gsus=curr.p50_equity_gsus,
                    p75_equity_gsus=curr.p75_equity_gsus,
                    sample_size=curr.sample_size,
                )

            prev_p50 = curr.p50_base
            smoothed[lvl] = curr

        return smoothed

    @classmethod
    def _calculate_single_percentile(cls, sorted_wages: list[Decimal], p: float) -> Decimal:
        """Calculates percentile via linear rank interpolation."""
        n = len(sorted_wages)
        if n == 1:
            return sorted_wages[0]

        rank = (p / 100.0) * (n - 1)
        lower_idx = int(math.floor(rank))
        upper_idx = int(math.ceil(rank))
        weight = Decimal(str(rank - lower_idx))

        if lower_idx == upper_idx:
            return sorted_wages[lower_idx]

        lower_val = sorted_wages[lower_idx]
        upper_val = sorted_wages[upper_idx]
        return lower_val + (weight * (upper_val - lower_val))
