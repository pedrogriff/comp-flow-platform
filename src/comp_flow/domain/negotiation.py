"""Domain models for Candidate Counter-Offer and Negotiation Simulation."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from comp_flow.domain.models import JobFamily, JobLevel, LocationTier


class VestingScheduleType(StrEnum):
    """Standardized tech vesting schedule archetypes."""

    ENTERPRISE_FRONT_LOADED_33_33_22_12 = (
        "ENTERPRISE_FRONT_LOADED_33_33_22_12"  # 33% / 33% / 22% / 12%
    )
    STANDARD_FOUR_YEAR_EQUAL_25 = "STANDARD_FOUR_YEAR_EQUAL_25"  # 25% / 25% / 25% / 25%
    BACK_LOADED_5_15_40_40 = "BACK_LOADED_5_15_40_40"  # 5% / 15% / 40% / 40%
    SEMI_ANNUAL_EQUAL = "SEMI_ANNUAL_EQUAL"  # 12.5% every 6 months


class WinRateTier(StrEnum):
    """Predictive win-rate competitive positioning tier."""

    HIGHLY_COMPETITIVE = "HIGHLY_COMPETITIVE"  # >= 80%
    COMPETITIVE = "COMPETITIVE"  # 65% - 79%
    MARGINAL = "MARGINAL"  # 50% - 64%
    AT_RISK = "AT_RISK"  # < 50%


class CompetingOfferInput(BaseModel):
    """Details of candidate's external competing offer or counter-offer."""

    model_config = ConfigDict(frozen=True)

    competitor_name: str = Field(
        ..., description="Name of competing employer (e.g. Stripe, Datadog)"
    )
    base_salary: Decimal = Field(..., ge=0, description="Competing annual base salary")
    target_bonus_pct: Decimal = Field(default=Decimal("15.00"), ge=0, description="Target bonus %")
    signon_bonus: Decimal = Field(
        default=Decimal("0.00"), ge=0, description="Competing upfront sign-on bonus"
    )
    equity_rsus_4yr: int = Field(
        default=0, ge=0, description="Competing 4-year total equity grant in RSUs"
    )
    share_price_estimate: Decimal = Field(
        default=Decimal("100.00"), gt=0, description="Estimated share price of competing company"
    )
    vesting_schedule: VestingScheduleType = Field(
        default=VestingScheduleType.STANDARD_FOUR_YEAR_EQUAL_25,
        description="Vesting progression schedule",
    )
    forfeited_unvested_equity: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        description="Unvested equity forfeited if candidate leaves current role",
    )


class OurOfferInput(BaseModel):
    """Our company's proposed offer parameters under evaluation."""

    model_config = ConfigDict(frozen=True)

    base_salary: Decimal = Field(..., ge=0, description="Proposed annual base salary")
    target_bonus_pct: Decimal = Field(default=Decimal("15.00"), ge=0, description="Target bonus %")
    signon_bonus: Decimal = Field(
        default=Decimal("0.00"), ge=0, description="Proposed sign-on bonus / buyout bridge"
    )
    equity_rsus_4yr: int = Field(..., ge=0, description="Proposed 4-year RSU grant")
    share_price_estimate: Decimal = Field(
        default=Decimal("100.00"), gt=0, description="Assumed internal company share valuation"
    )
    vesting_schedule: VestingScheduleType = Field(
        default=VestingScheduleType.ENTERPRISE_FRONT_LOADED_33_33_22_12,
        description="Our company's vesting schedule",
    )
    job_level: JobLevel = Field(default=JobLevel.L5, description="Candidate job level")
    job_family: JobFamily = Field(
        default=JobFamily.SOFTWARE_ENGINEERING, description="Candidate job family"
    )
    location_tier: LocationTier = Field(
        default=LocationTier.US_ZONE_1, description="Location cost tier"
    )


class YearByYearTDC(BaseModel):
    """Year-by-year cash, equity, and Total Direct Compensation (TDC) comparison."""

    model_config = ConfigDict(frozen=True)

    year: int = Field(..., ge=1, le=4)
    our_cash: Decimal
    our_equity_value: Decimal
    our_tdc: Decimal
    comp_cash: Decimal
    comp_equity_value: Decimal
    comp_tdc: Decimal
    delta_tdc: Decimal = Field(..., description="Our TDC - Competitor TDC (positive favors us)")


class RecommendedCounter(BaseModel):
    """Algorithmically generated counter-offer lever recommendations to maximize win-rate."""

    model_config = ConfigDict(frozen=True)

    recommended_base: Decimal
    recommended_signon: Decimal
    recommended_equity_rsus: int
    target_win_rate_pct: Decimal
    rationale: str


class CounterOfferSimulationResult(BaseModel):
    """Comprehensive analytical evaluation of competing offer dynamics and win probability."""

    model_config = ConfigDict(frozen=True)

    first_year_our_tdc: Decimal
    first_year_comp_tdc: Decimal
    first_year_tdc_delta: Decimal
    four_year_our_tdc: Decimal
    four_year_comp_tdc: Decimal
    four_year_tdc_delta: Decimal
    forfeiture_coverage_pct: Decimal = Field(
        ...,
        description="Percentage of forfeited equity covered by our sign-on and Yr 1 equity surplus",
    )
    predicted_win_rate_pct: Decimal = Field(
        ..., description="Probability of candidate acceptance [0.0 - 100.0%]"
    )
    win_rate_tier: WinRateTier
    year_by_year: list[YearByYearTDC]
    recommended_counter: RecommendedCounter
    recruiter_talking_points: list[str] = Field(
        ...,
        description="Data-driven negotiation talking points highlighting our total rewards value proposition",
    )
