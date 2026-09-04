"""Unit and integration tests for Counter-Offer and Negotiation Simulator."""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient

from comp_flow.domain.models import JobFamily, JobLevel, LocationTier
from comp_flow.domain.negotiation import (
    CompetingOfferInput,
    OurOfferInput,
    VestingScheduleType,
    WinRateTier,
)
from comp_flow.service.negotiation_service import NegotiationService


def test_simulate_counter_offer_front_loaded_advantage():
    """Verifies enterprise 33/33/22/12 vesting produces superior Year 1 and Year 2 cash/equity flow."""
    our_offer = OurOfferInput(
        base_salary=Decimal("220000.00"),
        target_bonus_pct=Decimal("15.00"),
        signon_bonus=Decimal("30000.00"),
        equity_rsus_4yr=1600,
        share_price_estimate=Decimal("100.00"),  # $160k equity total ($52.8k Yr 1)
        vesting_schedule=VestingScheduleType.ENTERPRISE_FRONT_LOADED_33_33_22_12,
        job_level=JobLevel.L5,
        job_family=JobFamily.SOFTWARE_ENGINEERING,
        location_tier=LocationTier.US_ZONE_1,
    )

    competing_offer = CompetingOfferInput(
        competitor_name="Datadog",
        base_salary=Decimal("220000.00"),
        target_bonus_pct=Decimal("15.00"),
        signon_bonus=Decimal("20000.00"),
        equity_rsus_4yr=1600,
        share_price_estimate=Decimal("100.00"),  # $160k equity total ($40k Yr 1)
        vesting_schedule=VestingScheduleType.STANDARD_FOUR_YEAR_EQUAL_25,
        forfeited_unvested_equity=Decimal("0.00"),
    )

    result = NegotiationService.simulate_counter_offer(our_offer, competing_offer)

    # Year 1 equity: Our 33% = $52,800 vs Comp 25% = $40,000
    assert result.year_by_year[0].our_equity_value == Decimal("52800.00")
    assert result.year_by_year[0].comp_equity_value == Decimal("40000.00")

    # Year 1 TDC delta includes +$10k signon and +$12.8k equity = +$22.8k
    assert result.first_year_tdc_delta > Decimal("20000.00")
    assert result.predicted_win_rate_pct >= Decimal("65.0")
    assert result.win_rate_tier in (WinRateTier.HIGHLY_COMPETITIVE, WinRateTier.COMPETITIVE)
    assert any("Front-Loaded Equity Advantage" in pt for pt in result.recruiter_talking_points)


def test_unvested_equity_forfeiture_buyout_bridge():
    """Verifies that unvested equity forfeiture drops win-rate unless bridged with sign-on bonus."""
    # Scenario A: Candidate forfeits $100,000 unvested equity, our signon is $0
    offer_no_buyout = OurOfferInput(
        base_salary=Decimal("200000.00"),
        signon_bonus=Decimal("0.00"),
        equity_rsus_4yr=1000,
        share_price_estimate=Decimal("100.00"),
    )
    comp_with_forfeit = CompetingOfferInput(
        competitor_name="Stripe",
        base_salary=Decimal("200000.00"),
        signon_bonus=Decimal("0.00"),
        equity_rsus_4yr=1000,
        share_price_estimate=Decimal("100.00"),
        forfeited_unvested_equity=Decimal("100000.00"),
    )

    res_no_buyout = NegotiationService.simulate_counter_offer(offer_no_buyout, comp_with_forfeit)
    assert res_no_buyout.forfeiture_coverage_pct < Decimal("50.0")
    assert res_no_buyout.predicted_win_rate_pct < Decimal("60.0")

    # Scenario B: We bridge the forfeiture with $80,000 sign-on bonus
    offer_with_buyout = OurOfferInput(
        base_salary=Decimal("200000.00"),
        signon_bonus=Decimal("80000.00"),
        equity_rsus_4yr=1000,
        share_price_estimate=Decimal("100.00"),
    )
    res_with_buyout = NegotiationService.simulate_counter_offer(
        offer_with_buyout, comp_with_forfeit
    )
    assert res_with_buyout.forfeiture_coverage_pct >= Decimal("80.0")
    assert res_with_buyout.predicted_win_rate_pct > res_no_buyout.predicted_win_rate_pct


def test_back_loaded_competitor_comparison():
    """Verifies massive Year 1 outperformance against 5/15/40/40 back-loaded competitor schedules."""
    our_offer = OurOfferInput(
        base_salary=Decimal("240000.00"),
        signon_bonus=Decimal("25000.00"),
        equity_rsus_4yr=2000,
        share_price_estimate=Decimal("100.00"),  # $200k equity
        vesting_schedule=VestingScheduleType.ENTERPRISE_FRONT_LOADED_33_33_22_12,
    )
    backloaded_comp = CompetingOfferInput(
        competitor_name="Enterprise Cloud Co",
        base_salary=Decimal("240000.00"),
        signon_bonus=Decimal("25000.00"),
        equity_rsus_4yr=2000,
        share_price_estimate=Decimal("100.00"),  # $200k equity (only 5% in Yr 1 = $10,000)
        vesting_schedule=VestingScheduleType.BACK_LOADED_5_15_40_40,
    )

    res = NegotiationService.simulate_counter_offer(our_offer, backloaded_comp)
    # Our Yr 1 equity = $66,000 vs Comp Yr 1 equity = $10,000
    assert res.year_by_year[0].our_equity_value == Decimal("66000.00")
    assert res.year_by_year[0].comp_equity_value == Decimal("10000.00")
    assert res.first_year_tdc_delta >= Decimal("56000.00")
    assert res.predicted_win_rate_pct >= Decimal("78.0")
    assert res.win_rate_tier in (WinRateTier.HIGHLY_COMPETITIVE, WinRateTier.COMPETITIVE)


@pytest.mark.asyncio
async def test_counter_offer_api_endpoint(async_client: AsyncClient):
    """Verifies REST API endpoint /api/v1/offers/negotiation/simulate."""
    payload = {
        "our_offer": {
            "base_salary": "230000.00",
            "target_bonus_pct": "15.00",
            "signon_bonus": "40000.00",
            "equity_rsus_4yr": 1500,
            "share_price_estimate": "100.00",
            "vesting_schedule": "ENTERPRISE_FRONT_LOADED_33_33_22_12",
        },
        "competing_offer": {
            "competitor_name": "Snowflake",
            "base_salary": "225000.00",
            "target_bonus_pct": "15.00",
            "signon_bonus": "20000.00",
            "equity_rsus_4yr": 1400,
            "share_price_estimate": "100.00",
            "vesting_schedule": "STANDARD_FOUR_YEAR_EQUAL_25",
            "forfeited_unvested_equity": "30000.00",
        },
    }

    res = await async_client.post("/api/v1/offers/negotiation/simulate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "first_year_our_tdc" in data
    assert "predicted_win_rate_pct" in data
    assert len(data["year_by_year"]) == 4
    assert len(data["recruiter_talking_points"]) >= 1
    assert data["win_rate_tier"] in ("HIGHLY_COMPETITIVE", "COMPETITIVE")
