"""Domain models and Pydantic schemas for Compensation Benchmarking."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from comp_flow.domain.models import JobFamily, JobLevel, LocationTier


class BenchmarkSourceType(StrEnum):
    """Authoritative source of compensation market data."""

    DOL_OFLC = "DOL_OFLC"  # US Department of Labor Foreign Labor Certification (H-1B/LCA/PERM)
    BLS_OEWS = "BLS_OEWS"  # US Bureau of Labor Statistics Occupational Employment & Wage Statistics
    LEVELS_FYI = "LEVELS_FYI"  # Community tech crowdsourced compensation datasets
    RADFORD_SURVEY = "RADFORD_SURVEY"  # Radford Global Technology Survey standard
    SYNTHETIC = "SYNTHETIC"  # High-fidelity statistically calibrated seed data


class RadfordLevel(StrEnum):
    """Radford-style standardized job levels."""

    P1 = "P1"  # Entry / Associate (L3)
    P2 = "P2"  # Developing / Intermediate (L4)
    P3 = "P3"  # Career / Senior (L5)
    P4 = "P4"  # Advanced / Staff (L6)
    P5 = "P5"  # Expert / Senior Staff / Principal (L7)
    P6 = "P6"  # Principal / Fellow / Distinguished (L8)
    M1 = "M1"  # Team Lead / Supervisor
    M2 = "M2"  # Manager
    M3 = "M3"  # Senior Manager
    M4 = "M4"  # Director
    M5 = "M5"  # Senior Director / VP


class RawWageObservation(BaseModel):
    """A single raw wage data point extracted from a source disclosure dataset."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    employer_name: str
    job_title: str
    soc_code: str
    wage_rate: Decimal
    wage_unit: str = "YEAR"  # "HOUR", "MONTH", "YEAR", "BI_WEEKLY"
    city: str | None = None
    state: str | None = None
    metro_area: str | None = None
    effective_date: date


class BenchmarkPercentiles(BaseModel):
    """Standardized 5-tier market compensation percentiles."""

    model_config = ConfigDict(frozen=True)

    p10_base: Decimal = Field(..., description="10th percentile base salary")
    p25_base: Decimal = Field(..., description="25th percentile base salary")
    p50_base: Decimal = Field(..., description="50th percentile (Median / Midpoint) base salary")
    p75_base: Decimal = Field(..., description="75th percentile base salary")
    p90_base: Decimal = Field(..., description="90th percentile base salary")

    target_bonus_pct: Decimal = Field(default=Decimal("15.00"), description="Market target bonus %")
    p50_equity_gsus: int = Field(default=0, description="Market median equity grant (GSUs)")
    p75_equity_gsus: int = Field(default=0, description="75th percentile equity grant (GSUs)")

    sample_size: int = Field(default=0, description="Number of observations after outlier trimming")


class MarketBenchmark(BaseModel):
    """Comprehensive Market Benchmark domain record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    soc_code: str = Field(..., description="Standard Occupational Classification code (e.g. 15-1252.00)")
    job_family: JobFamily
    job_level: JobLevel
    radford_level: RadfordLevel
    geo_tier: LocationTier
    metro_area: str | None = None
    currency: str = "USD"

    # Base Salary Percentiles
    p10_base: Decimal
    p25_base: Decimal
    p50_base: Decimal
    p75_base: Decimal
    p90_base: Decimal

    # Total Direct Comp Percentiles
    target_bonus_pct: Decimal
    p50_equity_gsus: int = 0
    p75_equity_gsus: int = 0

    # Metadata & Data Provenance
    sample_size: int
    source_type: BenchmarkSourceType
    effective_date: date
    aged_to_date: date
    annual_aging_rate: Decimal = Decimal("0.040")  # 4.0% annual wage movement index
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BenchmarkComparisonResult(BaseModel):
    """Comparative benchmarking positioning for an employee or candidate offer."""

    model_config = ConfigDict(frozen=True)

    proposed_base: Decimal
    benchmark: MarketBenchmark
    compa_ratio: Decimal = Field(..., description="Proposed Base / Benchmark P50 (Midpoint)")
    range_penetration_pct: Decimal = Field(..., description="(Base - P10) / (P90 - P10) * 100")
    market_percentile_estimate: Decimal = Field(..., description="Estimated market percentile [0-100]")
    total_target_cash: Decimal = Field(..., description="Base + Calculated Target Bonus")
    first_year_direct_comp: Decimal = Field(..., description="TTC + Sign-on Bonus")
    predicted_offer_win_rate: Decimal = Field(..., description="Estimated candidate acceptance rate [0-100%]")
    within_market_band: bool = Field(..., description="True if proposed base is between P10 and P90")
