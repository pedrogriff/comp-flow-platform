"""Initial schema for CompFlow Total Rewards Platform

Revision ID: 001_initial_schema
Revises: None
Create Date: 2026-08-25 19:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Users Table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # 2. Departments Table
    op.create_table(
        "departments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("cost_center", sa.String(64), nullable=False, unique=True),
        sa.Column("head_of_department_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 3. Salary Bands Table
    op.create_table(
        "salary_bands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_level", sa.String(32), nullable=False, index=True),
        sa.Column("job_family", sa.String(64), nullable=False, index=True),
        sa.Column("location_tier", sa.String(64), nullable=False, index=True),
        sa.Column("min_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("mid_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("max_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("target_equity_gsus", sa.Integer(), nullable=False, default=0),
        sa.Column("target_bonus_pct", sa.Numeric(5, 2), nullable=False, default=15.00),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "job_level", "job_family", "location_tier", name="uq_band_level_family_geo"
        ),
    )

    # 4. Employees Table
    op.create_table(
        "employees",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_number", sa.String(64), nullable=False, unique=True),
        sa.Column("first_name", sa.String(128), nullable=False),
        sa.Column("last_name", sa.String(128), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("job_level", sa.String(32), nullable=False),
        sa.Column("job_family", sa.String(64), nullable=False),
        sa.Column("location_tier", sa.String(64), nullable=False),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("current_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("current_equity_gsus", sa.Integer(), nullable=False, default=0),
        sa.Column("last_performance_rating", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_employees_employee_number", "employees", ["employee_number"])

    # 5. Compensation Cycles Table
    op.create_table(
        "compensation_cycles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("fiscal_year", sa.String(16), nullable=False, index=True),
        sa.Column("cycle_type", sa.String(64), nullable=False),
        sa.Column("global_merit_budget_pct", sa.Numeric(5, 2), nullable=False, default=4.00),
        sa.Column("bonus_pool_funding_pct", sa.Numeric(5, 2), nullable=False, default=100.00),
        sa.Column("company_performance_factor", sa.Numeric(4, 2), nullable=False, default=1.00),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 6. Cycle Budgets Table
    op.create_table(
        "cycle_budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cycle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("compensation_cycles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("allocated_merit_budget", sa.Numeric(14, 2), nullable=False, default=0.00),
        sa.Column("depleted_merit_budget", sa.Numeric(14, 2), nullable=False, default=0.00),
        sa.Column("allocated_bonus_pool", sa.Numeric(14, 2), nullable=False, default=0.00),
        sa.Column("depleted_bonus_pool", sa.Numeric(14, 2), nullable=False, default=0.00),
        sa.Column("allocated_equity_pool", sa.Integer(), nullable=False, default=0),
        sa.Column("depleted_equity_pool", sa.Integer(), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("cycle_id", "department_id", name="uq_cycle_department_budget"),
    )

    # 7. Employee Reviews Table
    op.create_table(
        "employee_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cycle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("compensation_cycles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("manager_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposed_job_level", sa.String(32), nullable=False),
        sa.Column("current_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("proposed_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("current_compa_ratio", sa.Numeric(5, 3), nullable=False, default=1.000),
        sa.Column("proposed_compa_ratio", sa.Numeric(5, 3), nullable=False, default=1.000),
        sa.Column("merit_increase_pct", sa.Numeric(5, 2), nullable=False, default=0.00),
        sa.Column("proposed_bonus_amount", sa.Numeric(12, 2), nullable=False, default=0.00),
        sa.Column("individual_perf_factor", sa.Numeric(4, 2), nullable=False, default=1.00),
        sa.Column("company_perf_factor", sa.Numeric(4, 2), nullable=False, default=1.00),
        sa.Column("proposed_equity_gsus", sa.Integer(), nullable=False, default=0),
        sa.Column("performance_rating", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("audit_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("justification_notes", sa.Text(), nullable=False, default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("cycle_id", "employee_id", name="uq_cycle_employee_review"),
    )

    # 8. Candidate Offers Table
    op.create_table(
        "candidate_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("offer_number", sa.String(64), nullable=False, unique=True),
        sa.Column("candidate_name", sa.String(255), nullable=False),
        sa.Column("candidate_email", sa.String(255), nullable=False, index=True),
        sa.Column("job_level", sa.String(32), nullable=False),
        sa.Column("job_family", sa.String(64), nullable=False),
        sa.Column("location_tier", sa.String(64), nullable=False),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("recruiter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("hiring_manager_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposed_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("sign_on_bonus", sa.Numeric(12, 2), nullable=False, default=0.00),
        sa.Column("proposed_equity_gsus", sa.Integer(), nullable=False, default=0),
        sa.Column("compa_ratio", sa.Numeric(5, 3), nullable=False, default=1.000),
        sa.Column("total_target_cash", sa.Numeric(12, 2), nullable=False, default=0.00),
        sa.Column("first_year_total_comp", sa.Numeric(12, 2), nullable=False, default=0.00),
        sa.Column("target_start_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("audit_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 9. Audit Logs Table
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(64), nullable=False, index=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("actor_email", sa.String(255), nullable=False),
        sa.Column("previous_status", sa.String(64), nullable=True),
        sa.Column("new_status", sa.String(64), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("candidate_offers")
    op.drop_table("employee_reviews")
    op.drop_table("cycle_budgets")
    op.drop_table("compensation_cycles")
    op.drop_table("employees")
    op.drop_table("salary_bands")
    op.drop_table("departments")
    op.drop_table("users")
