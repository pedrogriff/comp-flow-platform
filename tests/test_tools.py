"""Unit tests for deterministic compensation calculation and audit tools."""

import unittest
from decimal import Decimal

from comp_flow.domain.models import (
    JobFamily,
    JobLevel,
    LocationTier,
    PerformanceRating,
)
from comp_flow.tools.registry import (
    calculate_compa_ratio,
    calculate_offer_total_comp,
    calculate_target_bonus_amount,
    evaluate_base_increase_velocity,
    evaluate_bonus_compliance,
    evaluate_candidate_offer_compliance,
    evaluate_equity_guidelines,
    evaluate_market_benchmark_positioning,
    evaluate_promotion_compliance,
    get_default_salary_band,
    verify_salary_band_compliance,
)


class TestCompensationTools(unittest.TestCase):
    """Test suite for deterministic tool calculations and compliance rules."""

    def test_compa_ratio_calculation(self) -> None:
        """Verifies exact 3-decimal precision compa-ratio."""
        mid = Decimal("250000.00")
        self.assertEqual(calculate_compa_ratio(Decimal("250000.00"), mid), Decimal("1.000"))
        self.assertEqual(calculate_compa_ratio(Decimal("275000.00"), mid), Decimal("1.100"))
        self.assertEqual(calculate_compa_ratio(Decimal("200000.00"), mid), Decimal("0.800"))
        self.assertEqual(
            calculate_compa_ratio(Decimal("100000.00"), Decimal("0.00")), Decimal("1.000")
        )

    def test_geo_adjusted_salary_bands(self) -> None:
        """Verifies geographic tier discounts for salary bands."""
        zone_1 = get_default_salary_band(
            JobLevel.L5, JobFamily.SOFTWARE_ENGINEERING, LocationTier.US_ZONE_1
        )
        zone_2 = get_default_salary_band(
            JobLevel.L5, JobFamily.SOFTWARE_ENGINEERING, LocationTier.US_ZONE_2
        )
        zone_3 = get_default_salary_band(
            JobLevel.L5, JobFamily.SOFTWARE_ENGINEERING, LocationTier.US_ZONE_3
        )

        self.assertEqual(zone_1.mid_base, Decimal("250000.00"))
        self.assertEqual(zone_2.mid_base, Decimal("225000.00"))  # 90%
        self.assertEqual(zone_3.mid_base, Decimal("200000.00"))  # 80%

    def test_salary_band_compliance(self) -> None:
        """Verifies boundary checks on salary bands."""
        band = get_default_salary_band(
            JobLevel.L4, JobFamily.SOFTWARE_ENGINEERING, LocationTier.US_ZONE_1
        )
        # L4 Zone 1: [170k, 230k]

        # Valid in-band
        res_valid = verify_salary_band_compliance(Decimal("200000.00"), band)
        self.assertTrue(res_valid.passed)

        # Under minimum
        res_under = verify_salary_band_compliance(Decimal("160000.00"), band)
        self.assertFalse(res_under.passed)
        self.assertEqual(res_under.severity, "WARNING")

        # Exceeds maximum
        res_over = verify_salary_band_compliance(Decimal("240000.00"), band)
        self.assertFalse(res_over.passed)
        self.assertEqual(res_over.severity, "CRITICAL")

    def test_bonus_formula_and_compliance(self) -> None:
        """Verifies target bonus formula: Base * Target% * IPF * CPF."""
        base = Decimal("200000.00")
        target_pct = Decimal("15.00")
        ipf = Decimal("1.20")
        cpf = Decimal("1.10")

        # Target amount = 200,000 * 0.15 * 1.20 * 1.10 = $39,600.00
        target = calculate_target_bonus_amount(base, target_pct, ipf, cpf)
        self.assertEqual(target, Decimal("39600.00"))

        # In-line proposed bonus
        res_ok = evaluate_bonus_compliance(Decimal("40000.00"), base, target_pct, ipf, cpf)
        self.assertTrue(res_ok.passed)

        # Deviant proposed bonus (e.g. $60,000 > 25% deviation)
        res_dev = evaluate_bonus_compliance(Decimal("60000.00"), base, target_pct, ipf, cpf)
        self.assertFalse(res_dev.passed)
        self.assertEqual(res_dev.severity, "WARNING")

    def test_equity_guidelines(self) -> None:
        """Verifies performance rating multiplier ranges."""
        band = get_default_salary_band(
            JobLevel.L5, JobFamily.SOFTWARE_ENGINEERING, LocationTier.US_ZONE_1
        )
        # Target: 900 RSUs

        # Exceeds rating (1.10 - 1.45x) -> [990, 1305] RSUs
        res_ok = evaluate_equity_guidelines(1100, band, PerformanceRating.EXCEEDS)
        self.assertTrue(res_ok.passed)

        res_too_high = evaluate_equity_guidelines(1800, band, PerformanceRating.EXCEEDS)
        self.assertFalse(res_too_high.passed)
        self.assertEqual(res_too_high.severity, "CRITICAL")

        res_too_low = evaluate_equity_guidelines(500, band, PerformanceRating.EXCEEDS)
        self.assertFalse(res_too_low.passed)
        self.assertEqual(res_too_low.severity, "WARNING")

    def test_increase_velocity_cap(self) -> None:
        """Verifies merit velocity caps and needs improvement restrictions."""
        current = Decimal("200000.00")
        proposed_ok = Decimal("220000.00")  # +10%
        proposed_high = Decimal("260000.00")  # +30%

        res_ok = evaluate_base_increase_velocity(current, proposed_ok, PerformanceRating.EXCEEDS)
        self.assertTrue(res_ok.passed)

        res_high = evaluate_base_increase_velocity(
            current, proposed_high, PerformanceRating.EXCEEDS
        )
        self.assertFalse(res_high.passed)
        self.assertEqual(res_high.severity, "CRITICAL")

        # Raise for Needs Improvement is rejected
        res_ni = evaluate_base_increase_velocity(
            current, proposed_ok, PerformanceRating.NEEDS_IMPROVEMENT
        )
        self.assertFalse(res_ni.passed)
        self.assertEqual(res_ni.severity, "CRITICAL")

    def test_promotion_compliance(self) -> None:
        """Verifies promotion step checks."""
        l5_band = get_default_salary_band(
            JobLevel.L5, JobFamily.SOFTWARE_ENGINEERING, LocationTier.US_ZONE_1
        )

        # Valid promotion L4 -> L5 with salary >= min L5 ($210k)
        res_valid = evaluate_promotion_compliance(
            JobLevel.L4, JobLevel.L5, Decimal("220000.00"), l5_band
        )
        self.assertTrue(res_valid.passed)

        # Multi-level jump L4 -> L6
        l6_band = get_default_salary_band(
            JobLevel.L6, JobFamily.SOFTWARE_ENGINEERING, LocationTier.US_ZONE_1
        )
        res_jump = evaluate_promotion_compliance(
            JobLevel.L4, JobLevel.L6, Decimal("270000.00"), l6_band
        )
        self.assertFalse(res_jump.passed)

        # Promotion with below min base
        res_below = evaluate_promotion_compliance(
            JobLevel.L4, JobLevel.L5, Decimal("190000.00"), l5_band
        )
        self.assertFalse(res_below.passed)

    def test_candidate_offer_compliance_and_totals(self) -> None:
        """Verifies candidate offer sign-on and equity caps, plus total comp calculations."""
        band = get_default_salary_band(
            JobLevel.L5, JobFamily.SOFTWARE_ENGINEERING, LocationTier.US_ZONE_1
        )
        # Target equity: 900 RSUs, max new hire (1.5x) = 1350

        # Normal offer
        findings_ok = evaluate_candidate_offer_compliance(
            proposed_base=Decimal("240000.00"),
            sign_on_bonus=Decimal("20000.00"),
            proposed_equity_rsus=1000,
            band=band,
        )
        self.assertTrue(all(f.passed for f in findings_ok))

        # Sign-on > $50k
        findings_high_sign_on = evaluate_candidate_offer_compliance(
            proposed_base=Decimal("240000.00"),
            sign_on_bonus=Decimal("60000.00"),
            proposed_equity_rsus=1000,
            band=band,
        )
        sign_on_check = [f for f in findings_high_sign_on if f.check_name == "SIGN_ON_BONUS_CAP"][0]
        self.assertFalse(sign_on_check.passed)

        # Total comp calculation
        totals = calculate_offer_total_comp(
            proposed_base=Decimal("200000.00"),
            sign_on_bonus=Decimal("30000.00"),
            target_bonus_pct=Decimal("15.00"),
            proposed_equity_rsus=1200,
            estimated_rsu_price=Decimal("150.00"),
        )
        self.assertEqual(totals["target_bonus"], Decimal("30000.00"))
        self.assertEqual(totals["total_target_cash"], Decimal("230000.00"))
        # First year total comp = 200k + 30k + 30k + (1200 * 0.33333333 * 150 = ~60,000) = $320,000.00
        self.assertEqual(totals["first_year_total_comp"], Decimal("320000.00"))

    def test_market_benchmark_positioning(self) -> None:
        """Verifies market benchmark percentile alignment evaluation."""
        p10 = Decimal("200000.00")
        p50 = Decimal("250000.00")
        p90 = Decimal("300000.00")

        # Aligned
        finding_ok = evaluate_market_benchmark_positioning(Decimal("250000.00"), p10, p50, p90)
        self.assertTrue(finding_ok.passed)
        self.assertEqual(finding_ok.severity, "INFO")

        # Below P10
        finding_low = evaluate_market_benchmark_positioning(Decimal("180000.00"), p10, p50, p90)
        self.assertFalse(finding_low.passed)
        self.assertEqual(finding_low.severity, "WARNING")

        # Above P90
        finding_high = evaluate_market_benchmark_positioning(Decimal("350000.00"), p10, p50, p90)
        self.assertFalse(finding_high.passed)
        self.assertEqual(finding_high.severity, "WARNING")


if __name__ == "__main__":
    unittest.main()
