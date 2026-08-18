"""Unit tests for end-to-end CompensationWorkflowEngine service."""

import unittest
from decimal import Decimal

from comp_flow.domain.models import (
    CompensationReviewProposal,
    JobLevel,
    PerformanceRating,
    ReviewStatus,
)
from comp_flow.service.workflow_engine import CompensationWorkflowEngine


class TestWorkflowEngine(unittest.TestCase):
    """Test suite for full review lifecycle orchestration."""

    def setUp(self) -> None:
        self.engine = CompensationWorkflowEngine()

    def test_full_auto_approval_lifecycle(self) -> None:
        """Verifies Draft -> Submit & Audit -> Auto-Approved -> Finalized."""
        proposal = CompensationReviewProposal(
            review_id="REV-200",
            employee_id="EMP-200",
            job_level=JobLevel.L6,
            current_base=Decimal("280000.00"),
            proposed_base=Decimal("300000.00"),
            proposed_equity_gsus=1600,  # Within [1540, 2030] for EXCEEDS rating (Target: 1400)
            performance_rating=PerformanceRating.EXCEEDS,
        )

        self.engine.register_draft(proposal)
        self.assertEqual(proposal.status, ReviewStatus.DRAFT)

        # Run agentic submission and audit
        audited = self.engine.submit_and_audit("REV-200")
        self.assertEqual(audited.status, ReviewStatus.AUTO_APPROVED)
        self.assertIsNotNone(audited.audit_result)

        # Finalize
        finalized = self.engine.finalize_review("REV-200")
        self.assertEqual(finalized.status, ReviewStatus.FINALIZED)

    def test_full_vp_escalation_lifecycle(self) -> None:
        """Verifies Draft -> Submit -> VP Exception -> VP Approve -> Finalized."""
        proposal = CompensationReviewProposal(
            review_id="REV-201",
            employee_id="EMP-201",
            job_level=JobLevel.L5,
            current_base=Decimal("220000.00"),
            proposed_base=Decimal("295000.00"),  # Exceeds max ($290k)
            proposed_equity_gsus=900,
            performance_rating=PerformanceRating.SUPERB,
        )

        self.engine.register_draft(proposal)
        audited = self.engine.submit_and_audit("REV-201")
        self.assertEqual(audited.status, ReviewStatus.VP_EXCEPTION_REQUIRED)

        # Executive approval
        vp_approved = self.engine.approve_vp_exception("REV-201", vp_notes="Critical retention case approved by VP")
        self.assertEqual(vp_approved.status, ReviewStatus.VP_APPROVED)

        # Finalize
        finalized = self.engine.finalize_review("REV-201")
        self.assertEqual(finalized.status, ReviewStatus.FINALIZED)


if __name__ == "__main__":
    unittest.main()
