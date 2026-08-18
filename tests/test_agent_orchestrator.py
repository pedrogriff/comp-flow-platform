"""Unit tests for CompensationCalibrationAgent decision logic."""

import unittest
from decimal import Decimal

from comp_flow.agent.orchestrator import CompensationCalibrationAgent
from comp_flow.domain.models import (
    CompensationReviewProposal,
    JobLevel,
    PerformanceRating,
    ReviewStatus,
)


class TestAgentOrchestrator(unittest.TestCase):
    """Test suite for agent ReAct audit decisions and rationale synthesis."""

    def setUp(self) -> None:
        self.agent = CompensationCalibrationAgent()

    def test_auto_approve_compliant_proposal(self) -> None:
        """Verifies compliant proposal is immediately AUTO_APPROVED."""
        proposal = CompensationReviewProposal(
            review_id="REV-100",
            employee_id="EMP-100",
            job_level=JobLevel.L5,  # Band: [210k - 250k - 290k], Target: 900 GSUs
            current_base=Decimal("230000.00"),
            proposed_base=Decimal("250000.00"),  # +8.6%, Compa: 1.00
            proposed_equity_gsus=950,
            performance_rating=PerformanceRating.CONSISTENTLY_MEETS,
        )

        audit = self.agent.audit_proposal(proposal)
        self.assertEqual(audit.decision, ReviewStatus.AUTO_APPROVED)
        self.assertEqual(audit.compa_ratio, Decimal("1.000"))
        self.assertIn("AUTO-APPROVED", audit.rationale)

    def test_escalation_for_out_of_band_equity(self) -> None:
        """Verifies out-of-band equity grant escalates to VP_EXCEPTION_REQUIRED."""
        proposal = CompensationReviewProposal(
            review_id="REV-101",
            employee_id="EMP-101",
            job_level=JobLevel.L5,
            current_base=Decimal("230000.00"),
            proposed_base=Decimal("250000.00"),
            proposed_equity_gsus=2000,  # Far above 900 target
            performance_rating=PerformanceRating.CONSISTENTLY_MEETS,
        )

        audit = self.agent.audit_proposal(proposal)
        self.assertEqual(audit.decision, ReviewStatus.VP_EXCEPTION_REQUIRED)
        self.assertIn("ESCALATED TO VP COMMITTEE", audit.rationale)

    def test_rejection_for_needs_improvement_raise(self) -> None:
        """Verifies pay raise for Needs Improvement is REJECTED."""
        proposal = CompensationReviewProposal(
            review_id="REV-102",
            employee_id="EMP-102",
            job_level=JobLevel.L4,
            current_base=Decimal("180000.00"),
            proposed_base=Decimal("195000.00"),
            proposed_equity_gsus=0,
            performance_rating=PerformanceRating.NEEDS_IMPROVEMENT,
        )

        audit = self.agent.audit_proposal(proposal)
        self.assertEqual(audit.decision, ReviewStatus.REJECTED)
        self.assertIn("REJECTED", audit.rationale)


if __name__ == "__main__":
    unittest.main()
