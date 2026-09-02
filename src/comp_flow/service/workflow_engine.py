"""In-Memory Fast Workflow Engine for Benchmarks and Offline Audits."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from comp_flow.agent.orchestrator import EmployeeCalibrationAgent
from comp_flow.domain.models import (
    AgentAuditResult,
    JobFamily,
    JobLevel,
    LocationTier,
    PerformanceRating,
    ReviewStatus,
)
from comp_flow.domain.state_machine import EmployeeReviewStateMachine


class ProposalNotFoundError(Exception):
    """Raised when review ID does not exist in the in-memory registry."""


@dataclass
class InMemProposal:
    """In-memory representation of a review proposal."""

    review_id: str
    employee_id: str
    job_level: JobLevel
    current_base: Decimal
    proposed_base: Decimal
    proposed_equity_rsus: int
    performance_rating: PerformanceRating
    job_family: JobFamily = JobFamily.SOFTWARE_ENGINEERING
    location_tier: LocationTier = LocationTier.US_ZONE_1
    status: ReviewStatus = ReviewStatus.DRAFT
    manager_notes: str = ""
    audit_result: AgentAuditResult | None = None

    @property
    def proposed_equity_gsus(self) -> int:
        return self.proposed_equity_rsus


class CompensationWorkflowEngine:
    """High-performance in-memory service for batch audits and throughput benchmarking."""

    def __init__(self, agent: EmployeeCalibrationAgent | None = None) -> None:
        self.agent = agent or EmployeeCalibrationAgent()
        self._proposals: dict[str, InMemProposal] = {}

    def register_draft(self, proposal: InMemProposal) -> InMemProposal:
        """Registers a new proposal in DRAFT status."""
        proposal.status = ReviewStatus.DRAFT
        self._proposals[proposal.review_id] = proposal
        return proposal

    def get_proposal(self, review_id: str) -> InMemProposal:
        """Retrieves proposal by review_id."""
        if review_id not in self._proposals:
            raise ProposalNotFoundError(f"Proposal {review_id} not found.")
        return self._proposals[review_id]

    def submit_and_audit(self, review_id: str) -> InMemProposal:
        """Submits proposal and executes deterministic audit loop."""
        p = self.get_proposal(review_id)

        # 1. State transitions: DRAFT -> SUBMITTED -> AGENT_AUDITING
        p.status = EmployeeReviewStateMachine.transition(
            p.status, ReviewStatus.SUBMITTED, p.review_id
        )
        p.status = EmployeeReviewStateMachine.transition(
            p.status, ReviewStatus.AGENT_AUDITING, p.review_id
        )

        from comp_flow.tools.registry import calculate_target_bonus_amount, get_default_salary_band

        band = get_default_salary_band(p.job_level, p.job_family, p.location_tier)
        bonus = calculate_target_bonus_amount(p.proposed_base, band.target_bonus_pct)

        # 2. Agent audit
        audit_res = self.agent.audit_review_proposal(
            review_id=p.review_id,
            current_level=p.job_level,
            proposed_level=p.job_level,
            job_family=p.job_family,
            location_tier=p.location_tier,
            current_base=p.current_base,
            proposed_base=p.proposed_base,
            proposed_bonus=bonus,
            individual_perf_factor=Decimal("1.00"),
            company_perf_factor=Decimal("1.00"),
            proposed_equity_rsus=p.proposed_equity_rsus,
            performance_rating=p.performance_rating,
        )
        p.audit_result = audit_res

        # 3. Transition to decision
        target_status = ReviewStatus(audit_res.decision)
        p.status = EmployeeReviewStateMachine.transition(p.status, target_status, p.review_id)

        return p

    def approve_vp_exception(self, review_id: str, vp_notes: str = "") -> InMemProposal:
        """Approves a proposal in VP_EXCEPTION_REQUIRED status."""
        p = self.get_proposal(review_id)
        p.status = EmployeeReviewStateMachine.transition(
            p.status, ReviewStatus.VP_APPROVED, p.review_id
        )
        if vp_notes:
            p.manager_notes += f" [VP Approved: {vp_notes}]"
        return p

    def finalize_review(self, review_id: str) -> InMemProposal:
        """Finalizes an approved review proposal."""
        p = self.get_proposal(review_id)
        p.status = EmployeeReviewStateMachine.transition(
            p.status, ReviewStatus.FINALIZED, p.review_id
        )
        return p
