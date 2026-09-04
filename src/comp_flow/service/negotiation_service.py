"""Service for Candidate Counter-Offer Evaluation, Elasticity Modeling, and Negotiation Intelligence."""

from __future__ import annotations

import math
from decimal import Decimal

from comp_flow.domain.negotiation import (
    CompetingOfferInput,
    CounterOfferSimulationResult,
    OurOfferInput,
    RecommendedCounter,
    VestingScheduleType,
    WinRateTier,
    YearByYearTDC,
)


class NegotiationService:
    """Calculates multi-year compensation comparisons, unvested equity buyouts, and acceptance elasticity."""

    VESTING_SCHEDULE_MAP: dict[VestingScheduleType, tuple[Decimal, Decimal, Decimal, Decimal]] = {
        VestingScheduleType.ENTERPRISE_FRONT_LOADED_33_33_22_12: (
            Decimal("0.33"),
            Decimal("0.33"),
            Decimal("0.22"),
            Decimal("0.12"),
        ),
        VestingScheduleType.STANDARD_FOUR_YEAR_EQUAL_25: (
            Decimal("0.25"),
            Decimal("0.25"),
            Decimal("0.25"),
            Decimal("0.25"),
        ),
        VestingScheduleType.BACK_LOADED_5_15_40_40: (
            Decimal("0.05"),
            Decimal("0.15"),
            Decimal("0.40"),
            Decimal("0.40"),
        ),
        VestingScheduleType.SEMI_ANNUAL_EQUAL: (
            Decimal("0.25"),
            Decimal("0.25"),
            Decimal("0.25"),
            Decimal("0.25"),
        ),
    }

    @classmethod
    def simulate_counter_offer(
        cls,
        our_offer: OurOfferInput,
        competing_offer: CompetingOfferInput,
    ) -> CounterOfferSimulationResult:
        """Simulates candidate counter-offer dynamics across 4 years with win-rate elasticity."""
        our_sched = cls.VESTING_SCHEDULE_MAP.get(
            our_offer.vesting_schedule,
            cls.VESTING_SCHEDULE_MAP[VestingScheduleType.ENTERPRISE_FRONT_LOADED_33_33_22_12],
        )
        comp_sched = cls.VESTING_SCHEDULE_MAP.get(
            competing_offer.vesting_schedule,
            cls.VESTING_SCHEDULE_MAP[VestingScheduleType.STANDARD_FOUR_YEAR_EQUAL_25],
        )

        our_total_equity = Decimal(our_offer.equity_rsus_4yr) * our_offer.share_price_estimate
        comp_total_equity = (
            Decimal(competing_offer.equity_rsus_4yr) * competing_offer.share_price_estimate
        )

        our_base = our_offer.base_salary
        our_annual_bonus = (our_base * our_offer.target_bonus_pct / Decimal("100.0")).quantize(
            Decimal("0.01")
        )

        comp_base = competing_offer.base_salary
        comp_annual_bonus = (
            comp_base * competing_offer.target_bonus_pct / Decimal("100.0")
        ).quantize(Decimal("0.01"))

        year_by_year: list[YearByYearTDC] = []
        our_tdc_sum = Decimal("0.00")
        comp_tdc_sum = Decimal("0.00")

        for yr_idx in range(4):
            year_num = yr_idx + 1

            # Cash comp
            our_cash = (
                our_base
                + our_annual_bonus
                + (our_offer.signon_bonus if yr_idx == 0 else Decimal("0.00"))
            )
            comp_cash = (
                comp_base
                + comp_annual_bonus
                + (competing_offer.signon_bonus if yr_idx == 0 else Decimal("0.00"))
            )

            # Equity value
            our_eq_val = (our_total_equity * our_sched[yr_idx]).quantize(Decimal("0.01"))
            comp_eq_val = (comp_total_equity * comp_sched[yr_idx]).quantize(Decimal("0.01"))

            our_tdc = our_cash + our_eq_val
            comp_tdc = comp_cash + comp_eq_val
            delta = our_tdc - comp_tdc

            our_tdc_sum += our_tdc
            comp_tdc_sum += comp_tdc

            year_by_year.append(
                YearByYearTDC(
                    year=year_num,
                    our_cash=our_cash.quantize(Decimal("0.01")),
                    our_equity_value=our_eq_val,
                    our_tdc=our_tdc.quantize(Decimal("0.01")),
                    comp_cash=comp_cash.quantize(Decimal("0.01")),
                    comp_equity_value=comp_eq_val,
                    comp_tdc=comp_tdc.quantize(Decimal("0.01")),
                    delta_tdc=delta.quantize(Decimal("0.01")),
                )
            )

        yr1_our_tdc = year_by_year[0].our_tdc
        yr1_comp_tdc = year_by_year[0].comp_tdc
        yr1_delta = yr1_our_tdc - yr1_comp_tdc

        four_yr_delta = our_tdc_sum - comp_tdc_sum

        # Forfeiture buyout coverage
        if competing_offer.forfeited_unvested_equity > Decimal("0.00"):
            equity_premium = max(
                Decimal("0.00"),
                year_by_year[0].our_equity_value - year_by_year[0].comp_equity_value,
            )
            buyout_value = our_offer.signon_bonus + equity_premium
            forfeiture_pct = min(
                Decimal("200.00"),
                (
                    buyout_value / competing_offer.forfeited_unvested_equity * Decimal("100.0")
                ).quantize(Decimal("0.01")),
            )
        else:
            forfeiture_pct = Decimal("100.00")

        # Win-rate probability elasticity
        win_rate = cls._calculate_win_rate(
            yr1_our=yr1_our_tdc,
            yr1_comp=yr1_comp_tdc,
            four_yr_our=our_tdc_sum,
            four_yr_comp=comp_tdc_sum,
            forfeiture_pct=forfeiture_pct,
            our_sched=our_offer.vesting_schedule,
            comp_sched=competing_offer.vesting_schedule,
        )

        tier = (
            WinRateTier.HIGHLY_COMPETITIVE
            if win_rate >= Decimal("80.0")
            else (
                WinRateTier.COMPETITIVE
                if win_rate >= Decimal("65.0")
                else (WinRateTier.MARGINAL if win_rate >= Decimal("50.0") else WinRateTier.AT_RISK)
            )
        )

        # Counter recommendations
        rec_counter = cls._generate_recommended_counter(
            our_offer=our_offer,
            competing_offer=competing_offer,
            yr1_delta=yr1_delta,
            four_yr_delta=four_yr_delta,
            current_win_rate=win_rate,
        )

        # Recruiter talking points
        talking_points = cls._generate_talking_points(
            our_offer=our_offer,
            competing_offer=competing_offer,
            yr1_delta=yr1_delta,
            four_yr_delta=four_yr_delta,
            forfeiture_pct=forfeiture_pct,
        )

        return CounterOfferSimulationResult(
            first_year_our_tdc=yr1_our_tdc,
            first_year_comp_tdc=yr1_comp_tdc,
            first_year_tdc_delta=yr1_delta,
            four_year_our_tdc=our_tdc_sum,
            four_year_comp_tdc=comp_tdc_sum,
            four_year_tdc_delta=four_yr_delta,
            forfeiture_coverage_pct=forfeiture_pct,
            predicted_win_rate_pct=win_rate,
            win_rate_tier=tier,
            year_by_year=year_by_year,
            recommended_counter=rec_counter,
            recruiter_talking_points=talking_points,
        )

    @classmethod
    def _calculate_win_rate(
        cls,
        yr1_our: Decimal,
        yr1_comp: Decimal,
        four_yr_our: Decimal,
        four_yr_comp: Decimal,
        forfeiture_pct: Decimal,
        our_sched: VestingScheduleType,
        comp_sched: VestingScheduleType,
    ) -> Decimal:
        """Calculates candidate acceptance probability using logistic utility regression."""
        if yr1_comp <= Decimal("0.0") or four_yr_comp <= Decimal("0.0"):
            return Decimal("95.00")

        r_yr1 = float(yr1_our / yr1_comp)
        r_4yr = float(four_yr_our / four_yr_comp)
        r_forfeit = min(1.0, float(forfeiture_pct) / 100.0)

        # Log-odds sensitivity scoring
        z_yr1 = 5.5 * (r_yr1 - 1.0)
        z_4yr = 3.5 * (r_4yr - 1.0)
        z_forfeit = 1.5 * (r_forfeit - 1.0)

        # Front-loaded vesting bonus
        z_schedule = 0.0
        if our_sched == VestingScheduleType.ENTERPRISE_FRONT_LOADED_33_33_22_12:
            if comp_sched in (
                VestingScheduleType.STANDARD_FOUR_YEAR_EQUAL_25,
                VestingScheduleType.BACK_LOADED_5_15_40_40,
            ):
                z_schedule = 0.35

        z_total = z_yr1 + z_4yr + z_forfeit + z_schedule

        # Logistic sigmoid: 1 / (1 + e^-z)
        try:
            prob = 1.0 / (1.0 + math.exp(-z_total))
        except OverflowError:
            prob = 1.0 if z_total > 0 else 0.0

        pct = Decimal(str(round(prob * 100.0, 1)))
        return max(Decimal("5.0"), min(Decimal("98.0"), pct))

    @classmethod
    def _generate_recommended_counter(
        cls,
        our_offer: OurOfferInput,
        competing_offer: CompetingOfferInput,
        yr1_delta: Decimal,
        four_yr_delta: Decimal,
        current_win_rate: Decimal,
    ) -> RecommendedCounter:
        """Determines optimal adjustments to base, sign-on, and equity to achieve high competitiveness."""
        rec_base = our_offer.base_salary
        rec_signon = our_offer.signon_bonus
        rec_rsus = our_offer.equity_rsus_4yr

        if current_win_rate >= Decimal("80.0"):
            return RecommendedCounter(
                recommended_base=rec_base,
                recommended_signon=rec_signon,
                recommended_equity_rsus=rec_rsus,
                target_win_rate_pct=current_win_rate,
                rationale="Offer is currently highly competitive. No compensation enhancement required.",
            )

        # If Year 1 cash is lagging, boost sign-on bonus (cost-effective one-time lever)
        if yr1_delta < Decimal("0.00"):
            deficit = abs(yr1_delta)
            # Add 110% of Year 1 deficit as sign-on bridge
            rec_signon = (our_offer.signon_bonus + deficit + Decimal("10000.00")).quantize(
                Decimal("1000.00")
            )

        # If 4-Year TDC is lagging, add equity grant RSUs
        if four_yr_delta < Decimal("0.00"):
            four_yr_deficit = abs(four_yr_delta)
            added_rsus = math.ceil(float(four_yr_deficit / our_offer.share_price_estimate) * 1.15)
            # Round up to nearest 50 RSUs
            rec_rsus += int(math.ceil(added_rsus / 50.0) * 50)

        # In case base salary is noticeably below competitor base
        if competing_offer.base_salary > our_offer.base_salary:
            base_diff = competing_offer.base_salary - our_offer.base_salary
            if base_diff <= Decimal("25000.00"):
                rec_base = competing_offer.base_salary

        return RecommendedCounter(
            recommended_base=rec_base,
            recommended_signon=rec_signon,
            recommended_equity_rsus=rec_rsus,
            target_win_rate_pct=Decimal("85.00"),
            rationale=(
                f"Elevate sign-on bonus to ${rec_signon:,.0f} to neutralize near-term cash deficit, "
                f"and expand equity grant to {rec_rsus:,} RSUs to ensure long-term TDC superiority."
            ),
        )

    @classmethod
    def _generate_talking_points(
        cls,
        our_offer: OurOfferInput,
        competing_offer: CompetingOfferInput,
        yr1_delta: Decimal,
        four_yr_delta: Decimal,
        forfeiture_pct: Decimal,
    ) -> list[str]:
        """Generates targeted recruiter negotiation talking points."""
        points: list[str] = []

        # Vesting schedule advantage
        if our_offer.vesting_schedule == VestingScheduleType.ENTERPRISE_FRONT_LOADED_33_33_22_12:
            points.append(
                "Front-Loaded Equity Advantage: Our enterprise 33/33/22/12 schedule vests 66% of your grant "
                "within the first 24 months, accelerating your liquidity and derisking market volatility "
                f"compared to {competing_offer.competitor_name}'s standard linear schedule."
            )

        # 4-Year Total Wealth Creation
        if four_yr_delta > Decimal("0.00"):
            points.append(
                f"Superior 4-Year Cumulative TDC: Our package delivers ${four_yr_delta:,.0f} more in total direct "
                f"compensation over 4 years compared to {competing_offer.competitor_name}."
            )
        else:
            points.append(
                "Near-Term Cash Flow Priority: While 4-year cumulative figures are competitive, our Year 1 cash flow "
                "guarantees immediate financial upside with less reliance on backend vesting."
            )

        # Year 1 Cash / Liquidity
        if yr1_delta > Decimal("0.00"):
            points.append(
                f"Immediate Year 1 Outperformance: You realize ${yr1_delta:,.0f} higher take-home compensation "
                "in your first 12 months between base, target bonus, and initial vesting tranches."
            )

        # Forfeiture Coverage
        if competing_offer.forfeited_unvested_equity > Decimal("0.00"):
            if forfeiture_pct >= Decimal("100.00"):
                points.append(
                    f"Full Equity Forfeiture Protection: Our upfront buyout package fully covers (100%+) "
                    f"the ${competing_offer.forfeited_unvested_equity:,.0f} of unvested equity you leave behind."
                )
            else:
                points.append(
                    f"Substantial Equity Forfeiture Offset: Our Year 1 package bridges {forfeiture_pct:.0f}% of your "
                    f"forfeited unvested equity immediately, eliminating transition risk."
                )

        return points
