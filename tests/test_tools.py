"""Unit tests for deterministic compensation audit tools."""

import unittest
from decimal import Decimal

from comp_flow.domain.models import JobLevel, PerformanceRating
from comp_flow.tools.registry import (
    DEFAULT_SALARY_BANDS,
    calculate_compa_ratio,
    evaluate_base_increase_velocity,
    evaluate_equity_guidelines,
    verify_salary_band_compliance,
)


class TestCompensationTools(unittest.TestCase):
    """Test suite for tool registry calculations and compliance checks."""

    def test_compa_ratio_calculation(self) -> None:
        """Verifies exact 3-decimal precision compa-ratio."""
        band = DEFAULT_SALARY_BANDS[JobLevel.L5]  # Mid is $250k
        proposed = Decimal("250000.00")
        ratio = calculate_compa_ratio(proposed, band)
        self.assertEqual(ratio, Decimal("1.000"))

        proposed_high = Decimal("275000.00")
        ratio_high = calculate_compa_ratio(proposed_high, band)
        self.assertEqual(ratio_high, Decimal("1.100"))

    def test_salary_band_compliance(self) -> None:
        """Verifies boundary checks on salary bands."""
        band = DEFAULT_SALARY_BANDS[JobLevel.L4]  # [170k, 230k]

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

    def test_equity_guidelines(self) -> None:
        """Verifies performance rating multiplier ranges."""
        band = DEFAULT_SALARY_BANDS[JobLevel.L5]  # Target: 900 GSUs

        # Exceeds rating (1.10 - 1.45x) -> 990 to 1305 GSUs
        res_ok = evaluate_equity_guidelines(1100, band, PerformanceRating.EXCEEDS)
        self.assertTrue(res_ok.passed)

        res_too_high = evaluate_equity_guidelines(1800, band, PerformanceRating.EXCEEDS)
        self.assertFalse(res_too_high.passed)
        self.assertEqual(res_too_high.severity, "CRITICAL")

    def test_increase_velocity_cap(self) -> None:
        """Verifies 20% annual merit velocity caps."""
        current = Decimal("200000.00")
        proposed_ok = Decimal("220000.00")  # +10%
        proposed_high = Decimal("260000.00")  # +30%

        res_ok = evaluate_base_increase_velocity(current, proposed_ok, PerformanceRating.EXCEEDS)
        self.assertTrue(res_ok.passed)

        res_high = evaluate_base_increase_velocity(current, proposed_high, PerformanceRating.EXCEEDS)
        self.assertFalse(res_high.passed)


if __name__ == "__main__":
    unittest.main()
