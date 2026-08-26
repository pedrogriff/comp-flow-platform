"""Domain Models and Pydantic Schemas for Total Rewards Planning and Offers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobLevel(StrEnum):
    """Corporate and engineering levels."""

    L3 = "L3"
    L4 = "L4"
    L5 = "L5"
    L6 = "L6"
    L7 = "L7"
    L8 = "L8"


class JobFamily(StrEnum):
    """Job family domains."""

    SOFTWARE_ENGINEERING = "SOFTWARE_ENGINEERING"
    SYSTEMS_INFRASTRUCTURE = "SYSTEMS_INFRASTRUCTURE"
    MACHINE_LEARNING = "MACHINE_LEARNING"
    PRODUCT_MANAGEMENT = "PRODUCT_MANAGEMENT"
    DATA_SCIENCE = "DATA_SCIENCE"


class LocationTier(StrEnum):
    """Geographic compensation tiers."""

    US_ZONE_1 = "US_ZONE_1"  # SF Bay Area, NYC
    US_ZONE_2 = "US_ZONE_2"  # Seattle, Austin, Boston
    US_ZONE_3 = "US_ZONE_3"  # National / Remote / Other US


class PerformanceRating(StrEnum):
    """Performance evaluation ratings."""

    NEEDS_IMPROVEMENT = "NEEDS_IMPROVEMENT"
    CONSISTENTLY_MEETS = "CONSISTENTLY_MEETS"
    EXCEEDS = "EXCEEDS"
    STRONGLY_OUTPERFORMS = "STRONGLY_OUTPERFORMS"
    SUPERB = "SUPERB"


class ReviewStatus(StrEnum):
    """Lifecycle states of an employee annual review proposal."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    AGENT_AUDITING = "AGENT_AUDITING"
    AUTO_APPROVED = "AUTO_APPROVED"
    VP_EXCEPTION_REQUIRED = "VP_EXCEPTION_REQUIRED"
    VP_APPROVED = "VP_APPROVED"
    FINALIZED = "FINALIZED"
    REJECTED = "REJECTED"


class OfferStatus(StrEnum):
    """Lifecycle states of a new hire candidate offer proposal."""

    OFFER_DRAFT = "OFFER_DRAFT"
    AUDIT_PENDING = "AUDIT_PENDING"
    OFFER_APPROVED = "OFFER_APPROVED"
    VP_EXCEPTION_REQUIRED = "VP_EXCEPTION_REQUIRED"
    OFFER_REJECTED = "OFFER_REJECTED"
    OFFER_EXTENDED = "OFFER_EXTENDED"
    OFFER_ACCEPTED = "OFFER_ACCEPTED"
    OFFER_DECLINED = "OFFER_DECLINED"
    OFFER_RESCINDED = "OFFER_RESCINDED"


class CycleStatus(StrEnum):
    """Lifecycle states of a compensation planning cycle."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    CALIBRATING = "CALIBRATING"
    LOCKED = "LOCKED"
    FINALIZED = "FINALIZED"


class UserRole(StrEnum):
    """Role-based access control roles."""

    HR_ADMIN = "HR_ADMIN"
    COMPENSATION_PARTNER = "COMPENSATION_PARTNER"
    PEOPLE_MANAGER = "PEOPLE_MANAGER"
    EXECUTIVE_APPROVER = "EXECUTIVE_APPROVER"
    RECRUITER = "RECRUITER"


# --- Audit Models ---


class AuditFinding(BaseModel):
    """Single compliance check result produced during deterministic agent audit."""

    check_name: str
    passed: bool
    details: str
    severity: str = "INFO"  # "INFO", "WARNING", "CRITICAL"


class AgentAuditResult(BaseModel):
    """Synthesized audit output and decision from deterministic agent."""

    target_id: str
    decision: str
    findings: list[AuditFinding]
    compa_ratio: Decimal = Field(default=Decimal("0.000"))
    equity_guideline_ratio: Decimal = Field(default=Decimal("0.00"))
    rationale: str
    execution_time_seconds: float = 0.0


# --- Auth & User Schemas ---


class Token(BaseModel):
    """JWT Token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user_role: UserRole
    user_email: str


class TokenPayload(BaseModel):
    """Decoded JWT payload."""

    sub: str
    role: UserRole
    exp: int


class UserBase(BaseModel):
    email: str
    full_name: str
    role: UserRole
    department_id: UUID | None = None


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime


# --- Department Schemas ---


class DepartmentBase(BaseModel):
    name: str
    cost_center: str


class DepartmentCreate(DepartmentBase):
    head_of_department_id: UUID | None = None


class DepartmentResponse(DepartmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    head_of_department_id: UUID | None = None
    created_at: datetime


# --- Salary Band Schemas ---


class SalaryBandBase(BaseModel):
    job_level: JobLevel
    job_family: JobFamily = JobFamily.SOFTWARE_ENGINEERING
    location_tier: LocationTier = LocationTier.US_ZONE_1
    min_base: Decimal = Field(gt=0)
    mid_base: Decimal = Field(gt=0)
    max_base: Decimal = Field(gt=0)
    target_equity_gsus: int = Field(ge=0)
    target_bonus_pct: Decimal = Field(default=Decimal("15.0"), ge=0, le=100)


class SalaryBandCreate(SalaryBandBase):
    pass


class SalaryBandResponse(SalaryBandBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    updated_at: datetime


# --- Employee Schemas ---


class EmployeeBase(BaseModel):
    employee_number: str
    first_name: str
    last_name: str
    email: str
    job_level: JobLevel
    job_family: JobFamily = JobFamily.SOFTWARE_ENGINEERING
    location_tier: LocationTier = LocationTier.US_ZONE_1
    department_id: UUID
    current_base: Decimal = Field(gt=0)
    current_equity_gsus: int = Field(default=0, ge=0)
    last_performance_rating: PerformanceRating = PerformanceRating.CONSISTENTLY_MEETS


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeResponse(EmployeeBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime


# --- Compensation Cycle & Budget Schemas ---


class CompensationCycleBase(BaseModel):
    name: str
    fiscal_year: str
    cycle_type: str = "ANNUAL_TOTAL_REWARDS"
    global_merit_budget_pct: Decimal = Field(default=Decimal("4.00"), ge=0, le=20)
    bonus_pool_funding_pct: Decimal = Field(default=Decimal("100.00"), ge=0, le=200)
    company_performance_factor: Decimal = Field(default=Decimal("1.00"), ge=0, le=2.0)
    start_date: date
    end_date: date


class CompensationCycleCreate(CompensationCycleBase):
    pass


class CycleBudgetBase(BaseModel):
    cycle_id: UUID
    department_id: UUID
    allocated_merit_budget: Decimal = Field(default=Decimal("0.00"), ge=0)
    allocated_bonus_pool: Decimal = Field(default=Decimal("0.00"), ge=0)
    allocated_equity_pool: int = Field(default=0, ge=0)


class CycleBudgetCreate(CycleBudgetBase):
    pass


class CycleBudgetResponse(CycleBudgetBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    depleted_merit_budget: Decimal
    depleted_bonus_pool: Decimal
    depleted_equity_pool: int
    merit_depletion_pct: Decimal = Field(default=Decimal("0.00"))
    bonus_depletion_pct: Decimal = Field(default=Decimal("0.00"))
    equity_depletion_pct: Decimal = Field(default=Decimal("0.00"))


class CompensationCycleResponse(CompensationCycleBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: CycleStatus
    budgets: list[CycleBudgetResponse] = []
    created_at: datetime


# --- Employee Review Proposal Schemas ---


class EmployeeReviewProposalBase(BaseModel):
    cycle_id: UUID
    employee_id: UUID
    proposed_job_level: JobLevel
    proposed_base: Decimal = Field(gt=0)
    proposed_bonus_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    individual_perf_factor: Decimal = Field(default=Decimal("1.00"), ge=0, le=2.5)
    proposed_equity_gsus: int = Field(default=0, ge=0)
    performance_rating: PerformanceRating
    justification_notes: str = ""


class EmployeeReviewProposalCreate(EmployeeReviewProposalBase):
    pass


class EmployeeReviewProposalUpdate(BaseModel):
    proposed_job_level: JobLevel | None = None
    proposed_base: Decimal | None = None
    proposed_bonus_amount: Decimal | None = None
    individual_perf_factor: Decimal | None = None
    proposed_equity_gsus: int | None = None
    performance_rating: PerformanceRating | None = None
    justification_notes: str | None = None


class EmployeeReviewProposalResponse(EmployeeReviewProposalBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    manager_id: UUID | None = None
    current_base: Decimal
    current_compa_ratio: Decimal
    proposed_compa_ratio: Decimal
    merit_increase_pct: Decimal
    status: ReviewStatus
    audit_summary: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


# --- Candidate Offer Schemas ---


class CandidateOfferBase(BaseModel):
    candidate_name: str
    candidate_email: str
    job_level: JobLevel
    job_family: JobFamily = JobFamily.SOFTWARE_ENGINEERING
    location_tier: LocationTier = LocationTier.US_ZONE_1
    department_id: UUID
    proposed_base: Decimal = Field(gt=0)
    sign_on_bonus: Decimal = Field(default=Decimal("0.00"), ge=0)
    proposed_equity_gsus: int = Field(default=0, ge=0)
    target_start_date: date
    notes: str = ""


class CandidateOfferCreate(CandidateOfferBase):
    hiring_manager_id: UUID | None = None


class CandidateOfferUpdate(BaseModel):
    job_level: JobLevel | None = None
    location_tier: LocationTier | None = None
    proposed_base: Decimal | None = None
    sign_on_bonus: Decimal | None = None
    proposed_equity_gsus: int | None = None
    target_start_date: date | None = None
    notes: str | None = None


class CandidateOfferResponse(CandidateOfferBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    offer_number: str
    recruiter_id: UUID | None = None
    hiring_manager_id: UUID | None = None
    compa_ratio: Decimal
    total_target_cash: Decimal
    first_year_total_comp: Decimal
    status: OfferStatus
    audit_summary: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


# --- Action Request / Response Schemas ---


class StatusTransitionRequest(BaseModel):
    notes: str = ""


class BatchAuditRequest(BaseModel):
    proposal_ids: list[UUID]


class BatchAuditResponse(BaseModel):
    cycle_id: UUID
    total_audited: int
    auto_approved_count: int
    vp_exception_count: int
    rejected_count: int
    results: list[AgentAuditResult]


class DepartmentBudgetRollup(BaseModel):
    department_id: UUID
    department_name: str
    total_headcount: int
    current_payroll_base: Decimal
    allocated_merit_budget: Decimal
    depleted_merit_budget: Decimal
    merit_budget_remaining: Decimal
    merit_budget_depletion_pct: Decimal
    allocated_bonus_pool: Decimal
    depleted_bonus_pool: Decimal
    bonus_pool_depletion_pct: Decimal
    allocated_equity_pool: int
    depleted_equity_pool: int
    equity_pool_depletion_pct: Decimal
