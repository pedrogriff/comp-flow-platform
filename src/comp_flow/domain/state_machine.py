"""Dual-Lifecycle State Machines Enforcing Valid Review and Offer Transitions."""

from __future__ import annotations

from comp_flow.domain.models import OfferStatus, ReviewStatus


class IllegalStateTransitionError(Exception):
    """Raised when attempting an unauthorized status transition."""


class EmployeeReviewStateMachine:
    """Governs valid lifecycle status transitions for Employee Compensation Review Proposals."""

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
        ReviewStatus.FINALIZED: set(),  # Terminal state
        ReviewStatus.REJECTED: {ReviewStatus.DRAFT},  # Can reset to DRAFT for modifications
    }

    @classmethod
    def can_transition(cls, current_status: ReviewStatus, target_status: ReviewStatus) -> bool:
        """Returns True if transition from current_status to target_status is allowed."""
        allowed = cls.VALID_TRANSITIONS.get(current_status, set())
        return target_status in allowed

    @classmethod
    def transition(
        cls, current_status: ReviewStatus, target_status: ReviewStatus, entity_id: str = ""
    ) -> ReviewStatus:
        """Validates and returns new status, or raises IllegalStateTransitionError."""
        if not cls.can_transition(current_status, target_status):
            allowed = cls.VALID_TRANSITIONS.get(current_status, set())
            raise IllegalStateTransitionError(
                f"Cannot transition Employee Review {entity_id} from '{current_status.value}' "
                f"to '{target_status.value}'. Allowed transitions: {[s.value for s in allowed]}"
            )
        return target_status


class OfferStateMachine:
    """Governs valid lifecycle status transitions for Candidate New Hire Offers."""

    VALID_TRANSITIONS: dict[OfferStatus, set[OfferStatus]] = {
        OfferStatus.OFFER_DRAFT: {OfferStatus.AUDIT_PENDING},
        OfferStatus.AUDIT_PENDING: {
            OfferStatus.OFFER_APPROVED,
            OfferStatus.VP_EXCEPTION_REQUIRED,
            OfferStatus.OFFER_REJECTED,
        },
        OfferStatus.VP_EXCEPTION_REQUIRED: {
            OfferStatus.OFFER_APPROVED,
            OfferStatus.OFFER_REJECTED,
        },
        OfferStatus.OFFER_APPROVED: {OfferStatus.OFFER_EXTENDED, OfferStatus.OFFER_RESCINDED},
        OfferStatus.OFFER_EXTENDED: {
            OfferStatus.OFFER_ACCEPTED,
            OfferStatus.OFFER_DECLINED,
            OfferStatus.OFFER_RESCINDED,
        },
        OfferStatus.OFFER_REJECTED: {OfferStatus.OFFER_DRAFT},  # Can revise and retry
        OfferStatus.OFFER_ACCEPTED: set(),  # Terminal
        OfferStatus.OFFER_DECLINED: set(),  # Terminal
        OfferStatus.OFFER_RESCINDED: set(),  # Terminal
    }

    @classmethod
    def can_transition(cls, current_status: OfferStatus, target_status: OfferStatus) -> bool:
        """Returns True if transition from current_status to target_status is allowed."""
        allowed = cls.VALID_TRANSITIONS.get(current_status, set())
        return target_status in allowed

    @classmethod
    def transition(
        cls, current_status: OfferStatus, target_status: OfferStatus, offer_number: str = ""
    ) -> OfferStatus:
        """Validates and returns new status, or raises IllegalStateTransitionError."""
        if not cls.can_transition(current_status, target_status):
            allowed = cls.VALID_TRANSITIONS.get(current_status, set())
            raise IllegalStateTransitionError(
                f"Cannot transition Candidate Offer {offer_number} from '{current_status.value}' "
                f"to '{target_status.value}'. Allowed transitions: {[s.value for s in allowed]}"
            )
        return target_status
