"""Unit tests for EmployeeReviewStateMachine and OfferStateMachine."""

import unittest

from comp_flow.domain.models import OfferStatus, ReviewStatus
from comp_flow.domain.state_machine import (
    EmployeeReviewStateMachine,
    IllegalStateTransitionError,
    OfferStateMachine,
)


class TestStateMachines(unittest.TestCase):
    """Test suite for dual-lifecycle state transitions and invariant rules."""

    def test_employee_review_valid_linear_lifecycle(self) -> None:
        """Verifies Draft -> Submitted -> Auditing -> Auto-Approved -> Finalized."""
        status = ReviewStatus.DRAFT
        status = EmployeeReviewStateMachine.transition(status, ReviewStatus.SUBMITTED, "REV-01")
        self.assertEqual(status, ReviewStatus.SUBMITTED)

        status = EmployeeReviewStateMachine.transition(
            status, ReviewStatus.AGENT_AUDITING, "REV-01"
        )
        self.assertEqual(status, ReviewStatus.AGENT_AUDITING)

        status = EmployeeReviewStateMachine.transition(status, ReviewStatus.AUTO_APPROVED, "REV-01")
        self.assertEqual(status, ReviewStatus.AUTO_APPROVED)

        status = EmployeeReviewStateMachine.transition(status, ReviewStatus.FINALIZED, "REV-01")
        self.assertEqual(status, ReviewStatus.FINALIZED)

    def test_employee_review_vp_exception_lifecycle(self) -> None:
        """Verifies Draft -> Submitted -> Auditing -> VP Exception -> VP Approved -> Finalized."""
        status = ReviewStatus.DRAFT
        status = EmployeeReviewStateMachine.transition(status, ReviewStatus.SUBMITTED, "REV-02")
        status = EmployeeReviewStateMachine.transition(
            status, ReviewStatus.AGENT_AUDITING, "REV-02"
        )
        status = EmployeeReviewStateMachine.transition(
            status, ReviewStatus.VP_EXCEPTION_REQUIRED, "REV-02"
        )
        self.assertEqual(status, ReviewStatus.VP_EXCEPTION_REQUIRED)

        status = EmployeeReviewStateMachine.transition(status, ReviewStatus.VP_APPROVED, "REV-02")
        self.assertEqual(status, ReviewStatus.VP_APPROVED)

        status = EmployeeReviewStateMachine.transition(status, ReviewStatus.FINALIZED, "REV-02")
        self.assertEqual(status, ReviewStatus.FINALIZED)

    def test_employee_review_illegal_jump(self) -> None:
        """Verifies illegal transition raises IllegalStateTransitionError."""
        with self.assertRaises(IllegalStateTransitionError):
            EmployeeReviewStateMachine.transition(
                ReviewStatus.DRAFT, ReviewStatus.FINALIZED, "REV-03"
            )

    def test_offer_valid_linear_lifecycle(self) -> None:
        """Verifies Offer Draft -> Audit Pending -> Approved -> Extended -> Accepted."""
        status = OfferStatus.OFFER_DRAFT
        status = OfferStateMachine.transition(status, OfferStatus.AUDIT_PENDING, "OFF-01")
        self.assertEqual(status, OfferStatus.AUDIT_PENDING)

        status = OfferStateMachine.transition(status, OfferStatus.OFFER_APPROVED, "OFF-01")
        self.assertEqual(status, OfferStatus.OFFER_APPROVED)

        status = OfferStateMachine.transition(status, OfferStatus.OFFER_EXTENDED, "OFF-01")
        self.assertEqual(status, OfferStatus.OFFER_EXTENDED)

        status = OfferStateMachine.transition(status, OfferStatus.OFFER_ACCEPTED, "OFF-01")
        self.assertEqual(status, OfferStatus.OFFER_ACCEPTED)

    def test_offer_vp_exception_and_rescission(self) -> None:
        """Verifies Offer Draft -> Audit Pending -> VP Exception -> Approved -> Extended -> Rescinded."""
        status = OfferStatus.OFFER_DRAFT
        status = OfferStateMachine.transition(status, OfferStatus.AUDIT_PENDING, "OFF-02")
        status = OfferStateMachine.transition(status, OfferStatus.VP_EXCEPTION_REQUIRED, "OFF-02")
        status = OfferStateMachine.transition(status, OfferStatus.OFFER_APPROVED, "OFF-02")
        status = OfferStateMachine.transition(status, OfferStatus.OFFER_EXTENDED, "OFF-02")
        status = OfferStateMachine.transition(status, OfferStatus.OFFER_RESCINDED, "OFF-02")
        self.assertEqual(status, OfferStatus.OFFER_RESCINDED)

    def test_offer_illegal_transition(self) -> None:
        """Verifies illegal jump from Draft to Accepted."""
        with self.assertRaises(IllegalStateTransitionError):
            OfferStateMachine.transition(
                OfferStatus.OFFER_DRAFT, OfferStatus.OFFER_ACCEPTED, "OFF-03"
            )


if __name__ == "__main__":
    unittest.main()
