"""SQLAlchemy ORM Database Entities for PostgreSQL."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from comp_flow.domain.benchmarks import BenchmarkSourceType, RadfordLevel
from comp_flow.domain.models import (
    CycleStatus,
    JobFamily,
    JobLevel,
    LocationTier,
    OfferStatus,
    PerformanceRating,
    ReviewStatus,
    UserRole,
)


class Base(DeclarativeBase):
    """Base Declarative ORM class."""

    type_annotation_map = {
        dict[str, Any]: JSON().with_variant(JSONB, "postgresql"),
    }


def utc_now() -> datetime:
    """Returns current UTC timestamp."""
    return datetime.now(UTC)


class User(Base):
    """System User Entity for Authentication and RBAC."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role_enum", native_enum=False),
        nullable=False,
        default=UserRole.PEOPLE_MANAGER,
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Department(Base):
    """Organizational Department / Business Unit."""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    cost_center: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    head_of_department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    employees: Mapped[list[Employee]] = relationship("Employee", back_populates="department")
    budgets: Mapped[list[CycleBudget]] = relationship("CycleBudget", back_populates="department")


class SalaryBand(Base):
    """Internal Compensation Benchmark Bands."""

    __tablename__ = "salary_bands"
    __table_args__ = (
        UniqueConstraint(
            "job_level", "job_family", "location_tier", name="uq_band_level_family_geo"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_level: Mapped[JobLevel] = mapped_column(
        SQLEnum(JobLevel, name="job_level_enum", native_enum=False), nullable=False, index=True
    )
    job_family: Mapped[JobFamily] = mapped_column(
        SQLEnum(JobFamily, name="job_family_enum", native_enum=False),
        nullable=False,
        default=JobFamily.SOFTWARE_ENGINEERING,
        index=True,
    )
    location_tier: Mapped[LocationTier] = mapped_column(
        SQLEnum(LocationTier, name="location_tier_enum", native_enum=False),
        nullable=False,
        default=LocationTier.US_ZONE_1,
        index=True,
    )
    min_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    mid_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    max_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    target_equity_gsus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_bonus_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("15.00")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Employee(Base):
    """Employee Entity with Total Rewards Baseline."""

    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_number: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    job_level: Mapped[JobLevel] = mapped_column(
        SQLEnum(JobLevel, name="job_level_enum", native_enum=False), nullable=False
    )
    job_family: Mapped[JobFamily] = mapped_column(
        SQLEnum(JobFamily, name="job_family_enum", native_enum=False),
        nullable=False,
        default=JobFamily.SOFTWARE_ENGINEERING,
    )
    location_tier: Mapped[LocationTier] = mapped_column(
        SQLEnum(LocationTier, name="location_tier_enum", native_enum=False),
        nullable=False,
        default=LocationTier.US_ZONE_1,
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    current_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    current_equity_gsus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_performance_rating: Mapped[PerformanceRating] = mapped_column(
        SQLEnum(PerformanceRating, name="perf_rating_enum", native_enum=False),
        nullable=False,
        default=PerformanceRating.CONSISTENTLY_MEETS,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    department: Mapped[Department] = relationship("Department", back_populates="employees")
    reviews: Mapped[list[EmployeeReview]] = relationship(
        "EmployeeReview", back_populates="employee"
    )


class CompensationCycle(Base):
    """Annual / Bi-annual Compensation Planning Cycle."""

    __tablename__ = "compensation_cycles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fiscal_year: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    cycle_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="ANNUAL_TOTAL_REWARDS"
    )
    global_merit_budget_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("4.00")
    )
    bonus_pool_funding_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("100.00")
    )
    company_performance_factor: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, default=Decimal("1.00")
    )
    status: Mapped[CycleStatus] = mapped_column(
        SQLEnum(CycleStatus, name="cycle_status_enum", native_enum=False),
        nullable=False,
        default=CycleStatus.DRAFT,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    budgets: Mapped[list[CycleBudget]] = relationship(
        "CycleBudget", back_populates="cycle", cascade="all, delete-orphan"
    )
    reviews: Mapped[list[EmployeeReview]] = relationship(
        "EmployeeReview", back_populates="cycle", cascade="all, delete-orphan"
    )


class CycleBudget(Base):
    """Departmental Allocated and Depleted Budgets for a Planning Cycle."""

    __tablename__ = "cycle_budgets"
    __table_args__ = (
        UniqueConstraint("cycle_id", "department_id", name="uq_cycle_department_budget"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compensation_cycles.id", ondelete="CASCADE"), nullable=False
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    allocated_merit_budget: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    depleted_merit_budget: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    allocated_bonus_pool: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    depleted_bonus_pool: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    allocated_equity_pool: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    depleted_equity_pool: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    cycle: Mapped[CompensationCycle] = relationship("CompensationCycle", back_populates="budgets")
    department: Mapped[Department] = relationship("Department", back_populates="budgets")


class EmployeeReview(Base):
    """Manager Proposed Compensation Adjustment for an Employee in a Planning Cycle."""

    __tablename__ = "employee_reviews"
    __table_args__ = (UniqueConstraint("cycle_id", "employee_id", name="uq_cycle_employee_review"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compensation_cycles.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    proposed_job_level: Mapped[JobLevel] = mapped_column(
        SQLEnum(JobLevel, name="job_level_enum", native_enum=False), nullable=False
    )
    current_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    proposed_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    current_compa_ratio: Mapped[Decimal] = mapped_column(
        Numeric(5, 3), nullable=False, default=Decimal("1.000")
    )
    proposed_compa_ratio: Mapped[Decimal] = mapped_column(
        Numeric(5, 3), nullable=False, default=Decimal("1.000")
    )
    merit_increase_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )
    proposed_bonus_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    individual_perf_factor: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, default=Decimal("1.00")
    )
    company_perf_factor: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, default=Decimal("1.00")
    )
    proposed_equity_gsus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    performance_rating: Mapped[PerformanceRating] = mapped_column(
        SQLEnum(PerformanceRating, name="perf_rating_enum", native_enum=False), nullable=False
    )
    status: Mapped[ReviewStatus] = mapped_column(
        SQLEnum(ReviewStatus, name="review_status_enum", native_enum=False),
        nullable=False,
        default=ReviewStatus.DRAFT,
        index=True,
    )
    audit_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    justification_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    cycle: Mapped[CompensationCycle] = relationship("CompensationCycle", back_populates="reviews")
    employee: Mapped[Employee] = relationship("Employee", back_populates="reviews")


class CandidateOffer(Base):
    """Candidate New Hire Offer Proposal and Approval Workflow."""

    __tablename__ = "candidate_offers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    offer_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    job_level: Mapped[JobLevel] = mapped_column(
        SQLEnum(JobLevel, name="job_level_enum", native_enum=False), nullable=False
    )
    job_family: Mapped[JobFamily] = mapped_column(
        SQLEnum(JobFamily, name="job_family_enum", native_enum=False),
        nullable=False,
        default=JobFamily.SOFTWARE_ENGINEERING,
    )
    location_tier: Mapped[LocationTier] = mapped_column(
        SQLEnum(LocationTier, name="location_tier_enum", native_enum=False),
        nullable=False,
        default=LocationTier.US_ZONE_1,
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    recruiter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    hiring_manager_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    proposed_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    sign_on_bonus: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    proposed_equity_gsus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compa_ratio: Mapped[Decimal] = mapped_column(
        Numeric(5, 3), nullable=False, default=Decimal("1.000")
    )
    total_target_cash: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    first_year_total_comp: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    target_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[OfferStatus] = mapped_column(
        SQLEnum(OfferStatus, name="offer_status_enum", native_enum=False),
        nullable=False,
        default=OfferStatus.OFFER_DRAFT,
        index=True,
    )
    audit_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    department: Mapped[Department] = relationship("Department")


class AuditLog(Base):
    """Immutable Audit Trail for State Changes and Approval Actions."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class MarketBenchmark(Base):
    """Compensation Market Benchmark Data Entity."""

    __tablename__ = "market_benchmarks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    soc_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    job_family: Mapped[JobFamily] = mapped_column(
        SQLEnum(JobFamily, name="benchmark_job_family_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    job_level: Mapped[JobLevel] = mapped_column(
        SQLEnum(JobLevel, name="benchmark_job_level_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    radford_level: Mapped[RadfordLevel] = mapped_column(
        SQLEnum(RadfordLevel, name="benchmark_radford_level_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    geo_tier: Mapped[LocationTier] = mapped_column(
        SQLEnum(LocationTier, name="benchmark_geo_tier_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    metro_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    p10_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    p25_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    p50_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    p75_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    p90_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    target_bonus_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("15.00")
    )
    p50_equity_gsus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    p75_equity_gsus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_type: Mapped[BenchmarkSourceType] = mapped_column(
        SQLEnum(BenchmarkSourceType, name="benchmark_source_type_enum", native_enum=False),
        nullable=False,
        default=BenchmarkSourceType.SYNTHETIC,
        index=True,
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    aged_to_date: Mapped[date] = mapped_column(Date, nullable=False)
    annual_aging_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.0400")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "job_family",
            "job_level",
            "geo_tier",
            "source_type",
            "effective_date",
            name="uq_benchmark_family_level_geo_source",
        ),
    )

