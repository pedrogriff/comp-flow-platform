"""Compensation Review Workflow Engine Orchestrating State and Agent Execution."""

from __future__ import annotations

from comp_flow.agent.orchestrator import CompensationCalibrationAgent
from comp_flow.domain.models import CompensationReviewProposal, ReviewStatus
from comp_flow.domain.state_machine import ReviewStateMachine


class ProposalNotFoundError(Exception):
    """Raised when review ID does not exist."""


class CompensationWorkflowEngine:
    """High-level service managing compensation review proposals and agentic audits."""

    def __init__(
        self,
        agent: CompensationCalibrationAgent | None = None,
    ) -> None:
        """Initializes workflow engine with calibration agent and in-memory store."""
        self.agent = agent or CompensationCalibrationAgent()
        self._proposals: dict[str, CompensationReviewProposal] = {}

    def register_draft(self, proposal: CompensationReviewProposal) -> CompensationReviewProposal:
        """Registers a new proposal in DRAFT status."""
        proposal.status = ReviewStatus.DRAFT
        self._proposals[proposal.review_id] = proposal
        return proposal

    def get_proposal(self, review_id: str) -> CompensationReviewProposal:
        """Retrieves proposal by review_id."""
        if review_id not in self._proposals:
            raise ProposalNotFoundError(f"Proposal {review_id} not found.")
        return self._proposals[review_id]

    def submit_and_audit(self, review_id: str) -> CompensationReviewProposal:
        """Submits proposal and triggers autonomous agentic audit and state transitions."""
        proposal = self.get_proposal(review_id)

        # 1. State Machine: Draft -> Submitted
        ReviewStateMachine.transition(proposal, ReviewStatus.SUBMITTED)

        # 2. State Machine: Submitted -> Agent Auditing
        ReviewStateMachine.transition(proposal, ReviewStatus.AGENT_AUDITING)

        # 3. Agentic Audit Execution
        audit_result = self.agent.audit_proposal(proposal)
        proposal.audit_result = audit_result

        # 4. State Machine: Transition to Agent Decision
        ReviewStateMachine.transition(proposal, audit_result.decision)

        return proposal

    def approve_vp_exception(self, review_id: str, vp_notes: str = "") -> CompensationReviewProposal:
        """Approves an escalated proposal in VP_EXCEPTION_REQUIRED status."""
        proposal = self.get_proposal(review_id)
        ReviewStateMachine.transition(proposal, ReviewStatus.VP_APPROVED)
        if vp_notes:
            proposal.manager_notes += f" [VP Approved: {vp_notes}]"
        return proposal

    def finalize_review(self, review_id: str) -> CompensationReviewProposal:
        """Finalizes an approved review proposal (AUTO_APPROVED or VP_APPROVED)."""
        proposal = self.get_proposal(review_id)
        ReviewStateMachine.transition(proposal, ReviewStatus.FINALIZED)
        return proposal
