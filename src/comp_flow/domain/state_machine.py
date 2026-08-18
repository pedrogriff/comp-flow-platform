"""State Machine Enforcing Valid Compensation Review Cycle Transitions."""

from __future__ import annotations

from comp_flow.domain.models import CompensationReviewProposal, ReviewStatus


class IllegalStateTransitionError(Exception):
    """Raised when attempting an unauthorized review status transition."""


class ReviewStateMachine:
    """Governs valid status transitions for compensation review proposals."""

    VALID_TRANSITIONS: dict[ReviewStatus, set[ReviewStatus]] = {
        ReviewStatus.DRAFT: {ReviewStatus.SUBMITTED},
        ReviewStatus.SUBMITTED: {ReviewStatus.AGENT_AUDITING},
        ReviewStatus.AGENT_AUDITING: {
            ReviewStatus.AUTO_APPROVED,
            ReviewStatus.VP_EXCEPTION_REQUIRED,
            ReviewStatus.REJECTED,
        },
        ReviewStatus.VP_EXCEPTION_REQUIRED: {
            ReviewStatus.VP_APPROVED,
            ReviewStatus.REJECTED,
        },
        ReviewStatus.AUTO_APPROVED: {ReviewStatus.FINALIZED},
        ReviewStatus.VP_APPROVED: {ReviewStatus.FINALIZED},
        ReviewStatus.FINALIZED: set(),  # Terminal
        ReviewStatus.REJECTED: {ReviewStatus.DRAFT},  # Can reset to draft for revisions
    }

    @classmethod
    def transition(
        cls,
        proposal: CompensationReviewProposal,
        target_status: ReviewStatus,
    ) -> None:
        """Transitions proposal to target_status if valid, otherwise raises error."""
        current = proposal.status
        allowed = cls.VALID_TRANSITIONS.get(current, set())

        if target_status not in allowed:
            raise IllegalStateTransitionError(
                f"Cannot transition review {proposal.review_id} from {current} to {target_status}. "
                f"Allowed transitions: {allowed}"
            )

        proposal.status = target_status
