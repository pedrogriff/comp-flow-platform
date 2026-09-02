"""Rename GSU equity columns to RSU across all schema tables

Revision ID: 003_rename_gsu_to_rsu
Revises: 002_market_benchmarks
Create Date: 2026-09-02 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "003_rename_gsu_to_rsu"
down_revision: str | None = "002_market_benchmarks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("salary_bands", "target_equity_gsus", new_column_name="target_equity_rsus")
    op.alter_column("employees", "current_equity_gsus", new_column_name="current_equity_rsus")
    op.alter_column(
        "employee_reviews", "proposed_equity_gsus", new_column_name="proposed_equity_rsus"
    )
    op.alter_column(
        "candidate_offers", "proposed_equity_gsus", new_column_name="proposed_equity_rsus"
    )
    op.alter_column("market_benchmarks", "p50_equity_gsus", new_column_name="p50_equity_rsus")
    op.alter_column("market_benchmarks", "p75_equity_gsus", new_column_name="p75_equity_rsus")


def downgrade() -> None:
    op.alter_column("market_benchmarks", "p75_equity_rsus", new_column_name="p75_equity_gsus")
    op.alter_column("market_benchmarks", "p50_equity_rsus", new_column_name="p50_equity_gsus")
    op.alter_column(
        "candidate_offers", "proposed_equity_rsus", new_column_name="proposed_equity_gsus"
    )
    op.alter_column(
        "employee_reviews", "proposed_equity_rsus", new_column_name="proposed_equity_gsus"
    )
    op.alter_column("employees", "current_equity_rsus", new_column_name="current_equity_gsus")
    op.alter_column("salary_bands", "target_equity_rsus", new_column_name="target_equity_gsus")
