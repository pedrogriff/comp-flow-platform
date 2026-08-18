"""Unit tests for ReviewStateMachine transitions."""

import unittest
from decimal import Decimal

from comp_flow.domain.models import (
    CompensationReviewProposal,
    JobLevel,
    PerformanceRating,
    ReviewStatus,
)
from comp_flow.domain.state_machine import IllegalStateTransitionError, ReviewStateMachine


class TestStateMachine(unittest.TestCase):
    """Test suite for state transition invariants."""

    def setUp(self) -> None:
        self.proposal = CompensationReviewProposal(
            review_id="REV-01",
            employee_id="EMP-01",
            job_level=JobLevel.L5,
            current_base=Decimal("220000.00"),
            proposed_base=Decimal("240000.00"),
            proposed_equity_gsus=900,
            performance_rating=PerformanceRating.CONSISTENTLY_MEETS,
            status=ReviewStatus.DRAFT,
        )

    def test_valid_linear_lifecycle(self) -> None:
        """Verifies Draft -> Submitted -> Auditing -> Auto-Approved -> Finalized."""
        ReviewStateMachine.transition(self.proposal, ReviewStatus.SUBMITTED)
        self.assertEqual(self.proposal.status, ReviewStatus.SUBMITTED)

        ReviewStateMachine.transition(self.proposal, ReviewStatus.AGENT_AUDITING)
        self.assertEqual(self.proposal.status, ReviewStatus.AGENT_AUDITING)

        ReviewStateMachine.transition(self.proposal, ReviewStatus.AUTO_APPROVED)
        self.assertEqual(self.proposal.status, ReviewStatus.AUTO_APPROVED)

        ReviewStateMachine.transition(self.proposal, ReviewStatus.FINALIZED)
        self.assertEqual(self.proposal.status, ReviewStatus.FINALIZED)

    def test_illegal_jump_to_finalized(self) -> None:
        """Verifies that skipping audit raises IllegalStateTransitionError."""
        with self.assertRaises(IllegalStateTransitionError):
            ReviewStateMachine.transition(self.proposal, ReviewStatus.FINALIZED)


if __name__ == "__main__":
    unittest.main()
