"""Domain Models for Compensation Review Cycles and Agentic Audits."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class ReviewStatus(StrEnum):
    """Lifecycle states of a compensation review proposal."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    AGENT_AUDITING = "AGENT_AUDITING"
    AUTO_APPROVED = "AUTO_APPROVED"
    VP_EXCEPTION_REQUIRED = "VP_EXCEPTION_REQUIRED"
    VP_APPROVED = "VP_APPROVED"
    FINALIZED = "FINALIZED"
    REJECTED = "REJECTED"


class JobLevel(StrEnum):
    """Standard software engineering / corporate levels."""

    L3 = "L3"
    L4 = "L4"
    L5 = "L5"
    L6 = "L6"
    L7 = "L7"
    L8 = "L8"


class PerformanceRating(StrEnum):
    """Performance evaluation ratings."""

    NEEDS_IMPROVEMENT = "NEEDS_IMPROVEMENT"
    CONSISTENTLY_MEETS = "CONSISTENTLY_MEETS"
    EXCEEDS = "EXCEEDS"
    STRONGLY_OUTPERFORMS = "STRONGLY_OUTPERFORMS"
    SUPERB = "SUPERB"


@dataclass(frozen=True)
class SalaryBand:
    """Internal compensation benchmark band for a job level."""

    job_level: JobLevel
    min_base: Decimal
    mid_base: Decimal
    max_base: Decimal
    target_equity_gsus: int


@dataclass
class CompensationReviewProposal:
    """A manager's proposed compensation adjustments for an employee."""

    review_id: str
    employee_id: str
    job_level: JobLevel
    current_base: Decimal
    proposed_base: Decimal
    proposed_equity_gsus: int
    performance_rating: PerformanceRating
    status: ReviewStatus = ReviewStatus.DRAFT
    manager_notes: str = ""
    audit_result: AgentAuditResult | None = None


@dataclass(frozen=True)
class AuditFinding:
    """An individual validation check produced during agentic audit."""

    check_name: str
    passed: bool
    details: str
    severity: str = "INFO"  # "INFO", "WARNING", "CRITICAL"


@dataclass(frozen=True)
class AgentAuditResult:
    """The synthesized decision and audit trail from the Compensation Agent."""

    review_id: str
    decision: ReviewStatus
    findings: list[AuditFinding]
    compa_ratio: Decimal
    equity_guideline_ratio: Decimal
    rationale: str
    execution_time_seconds: float = field(default=0.0)
