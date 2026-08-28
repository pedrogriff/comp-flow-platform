"""Add market_benchmarks table for compensation benchmarking

Revision ID: 002_market_benchmarks
Revises: 001_initial_schema
Create Date: 2026-08-27 18:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "002_market_benchmarks"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_benchmarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("soc_code", sa.String(16), nullable=False, index=True),
        sa.Column("job_family", sa.String(64), nullable=False, index=True),
        sa.Column("job_level", sa.String(32), nullable=False, index=True),
        sa.Column("radford_level", sa.String(16), nullable=False, index=True),
        sa.Column("geo_tier", sa.String(64), nullable=False, index=True),
        sa.Column("metro_area", sa.String(255), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, default="USD"),
        sa.Column("p10_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("p25_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("p50_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("p75_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("p90_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("target_bonus_pct", sa.Numeric(5, 2), nullable=False, default=15.00),
        sa.Column("p50_equity_gsus", sa.Integer(), nullable=False, default=0),
        sa.Column("p75_equity_gsus", sa.Integer(), nullable=False, default=0),
        sa.Column("sample_size", sa.Integer(), nullable=False, default=0),
        sa.Column("source_type", sa.String(64), nullable=False, index=True),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("aged_to_date", sa.Date(), nullable=False),
        sa.Column("annual_aging_rate", sa.Numeric(5, 4), nullable=False, default=0.0400),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "job_family",
            "job_level",
            "geo_tier",
            "source_type",
            "effective_date",
            name="uq_benchmark_family_level_geo_source",
        ),
    )
    op.create_index("ix_benchmark_lookup", "market_benchmarks", ["job_family", "job_level", "geo_tier", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_benchmark_lookup", table_name="market_benchmarks")
    op.drop_table("market_benchmarks")
