"""Unit tests for EmployeeCalibrationAgent and OfferApprovalAgent."""

import unittest
from decimal import Decimal

from comp_flow.agent.orchestrator import (
    EmployeeCalibrationAgent,
    OfferApprovalAgent,
)
from comp_flow.domain.models import (
    JobFamily,
    JobLevel,
    LocationTier,
    OfferStatus,
    PerformanceRating,
    ReviewStatus,
)


class TestAgentOrchestrator(unittest.TestCase):
    """Test suite for agent deterministic decision logic and synthesis."""

    def setUp(self) -> None:
        self.review_agent = EmployeeCalibrationAgent()
        self.offer_agent = OfferApprovalAgent()

    def test_employee_review_auto_approval(self) -> None:
        """Verifies compliant employee review is AUTO_APPROVED."""
        audit = self.review_agent.audit_review_proposal(
            review_id="REV-100",
            current_level=JobLevel.L5,
            proposed_level=JobLevel.L5,
            job_family=JobFamily.SOFTWARE_ENGINEERING,
            location_tier=LocationTier.US_ZONE_1,
            current_base=Decimal("230000.00"),
            proposed_base=Decimal("250000.00"),  # Compa: 1.000
            proposed_bonus=Decimal("37500.00"),  # Exact 15% target
            individual_perf_factor=Decimal("1.00"),
            company_perf_factor=Decimal("1.00"),
            proposed_equity_rsus=950,  # Target: 900
            performance_rating=PerformanceRating.CONSISTENTLY_MEETS,
        )

        self.assertEqual(audit.decision, ReviewStatus.AUTO_APPROVED.value)
        self.assertEqual(audit.compa_ratio, Decimal("1.000"))
        self.assertIn("AUTO-APPROVED", audit.rationale)

    def test_employee_review_vp_exception_on_excessive_equity(self) -> None:
        """Verifies out-of-band equity grant requires VP exception."""
        audit = self.review_agent.audit_review_proposal(
            review_id="REV-101",
            current_level=JobLevel.L5,
            proposed_level=JobLevel.L5,
            job_family=JobFamily.SOFTWARE_ENGINEERING,
            location_tier=LocationTier.US_ZONE_1,
            current_base=Decimal("230000.00"),
            proposed_base=Decimal("250000.00"),
            proposed_bonus=Decimal("37500.00"),
            individual_perf_factor=Decimal("1.00"),
            company_perf_factor=Decimal("1.00"),
            proposed_equity_rsus=2500,  # Far above 900 target
            performance_rating=PerformanceRating.CONSISTENTLY_MEETS,
        )

        self.assertEqual(audit.decision, ReviewStatus.VP_EXCEPTION_REQUIRED.value)
        self.assertIn("ESCALATED TO VP COMMITTEE", audit.rationale)

    def test_employee_review_rejection_needs_improvement_raise(self) -> None:
        """Verifies salary increase for Needs Improvement rating is REJECTED."""
        audit = self.review_agent.audit_review_proposal(
            review_id="REV-102",
            current_level=JobLevel.L4,
            proposed_level=JobLevel.L4,
            job_family=JobFamily.SOFTWARE_ENGINEERING,
            location_tier=LocationTier.US_ZONE_1,
            current_base=Decimal("180000.00"),
            proposed_base=Decimal("195000.00"),
            proposed_bonus=Decimal("0.00"),
            individual_perf_factor=Decimal("0.00"),
            company_perf_factor=Decimal("1.00"),
            proposed_equity_rsus=0,
            performance_rating=PerformanceRating.NEEDS_IMPROVEMENT,
        )

        self.assertEqual(audit.decision, ReviewStatus.REJECTED.value)
        self.assertIn("REJECTED", audit.rationale)

    def test_candidate_offer_approval(self) -> None:
        """Verifies compliant candidate offer is approved."""
        audit = self.offer_agent.audit_offer_package(
            offer_id="OFF-201",
            job_level=JobLevel.L5,
            job_family=JobFamily.SOFTWARE_ENGINEERING,
            location_tier=LocationTier.US_ZONE_1,
            proposed_base=Decimal("245000.00"),  # Compa ~0.980
            sign_on_bonus=Decimal("25000.00"),  # < $50k
            proposed_equity_rsus=1000,  # < 1350 max new hire
        )

        self.assertEqual(audit.decision, OfferStatus.OFFER_APPROVED.value)
        self.assertIn("OFFER APPROVED", audit.rationale)

    def test_candidate_offer_vp_exception_sign_on(self) -> None:
        """Verifies high sign-on bonus ($75k) requires VP exception."""
        audit = self.offer_agent.audit_offer_package(
            offer_id="OFF-202",
            job_level=JobLevel.L6,
            job_family=JobFamily.SOFTWARE_ENGINEERING,
            location_tier=LocationTier.US_ZONE_1,
            proposed_base=Decimal("310000.00"),
            sign_on_bonus=Decimal("75000.00"),  # Exceeds $50k cap
            proposed_equity_rsus=1400,
        )

        self.assertEqual(audit.decision, OfferStatus.VP_EXCEPTION_REQUIRED.value)
        self.assertIn("VP EXCEPTION REQUIRED", audit.rationale)


if __name__ == "__main__":
    unittest.main()
