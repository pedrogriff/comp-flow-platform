"""Analytics and Distribution Reporting Service for Compensation Metrics."""

from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from comp_flow.domain.entities import EmployeeReview
from comp_flow.domain.models import ReviewStatus


class AnalyticsService:
    """Provides high-level analytics on compa-ratios, budget burn, and merit distributions."""

    @classmethod
    async def get_cycle_analytics(cls, db: AsyncSession, cycle_id: uuid.UUID) -> dict[str, Any]:
        """Calculates comprehensive cycle analytics including distributions and budget health."""
        # 1. Fetch Cycle Proposals
        stmt = (
            select(EmployeeReview)
            .where(EmployeeReview.cycle_id == cycle_id)
            .options(selectinload(EmployeeReview.employee))
        )
        res = await db.execute(stmt)
        proposals = res.scalars().all()

        total_proposals = len(proposals)
        if total_proposals == 0:
            return {
                "cycle_id": str(cycle_id),
                "total_proposals": 0,
                "status_breakdown": {},
                "compa_ratio_distribution": {},
                "merit_by_rating": {},
                "total_merit_spend": "0.00",
                "total_bonus_spend": "0.00",
                "total_equity_gsus": 0,
            }

        # Status Breakdown
        status_counts: dict[str, int] = defaultdict(int)
        for p in proposals:
            status_counts[p.status.value] += 1

        # Compa-Ratio Distribution Buckets
        compa_buckets = {
            "<0.85 (Below Band Target)": 0,
            "0.85 - 0.95 (Approaching Midpoint)": 0,
            "0.95 - 1.05 (Parity / Midpoint)": 0,
            "1.05 - 1.15 (Above Midpoint)": 0,
            ">1.15 (Top of Band / Premium)": 0,
        }

        for p in proposals:
            cr = p.proposed_compa_ratio
            if cr < Decimal("0.850"):
                compa_buckets["<0.85 (Below Band Target)"] += 1
            elif cr <= Decimal("0.950"):
                compa_buckets["0.85 - 0.95 (Approaching Midpoint)"] += 1
            elif cr <= Decimal("1.050"):
                compa_buckets["0.95 - 1.05 (Parity / Midpoint)"] += 1
            elif cr <= Decimal("1.150"):
                compa_buckets["1.05 - 1.15 (Above Midpoint)"] += 1
            else:
                compa_buckets[">1.15 (Top of Band / Premium)"] += 1

        # Merit % by Performance Rating
        rating_merit_sums: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        rating_counts: dict[str, int] = defaultdict(int)

        total_merit_spend = Decimal("0.00")
        total_bonus_spend = Decimal("0.00")
        total_equity_gsus = 0

        for p in proposals:
            r_val = p.performance_rating.value
            rating_merit_sums[r_val] += p.merit_increase_pct
            rating_counts[r_val] += 1

            if p.status != ReviewStatus.REJECTED:
                increase = max(Decimal("0.00"), p.proposed_base - p.current_base)
                total_merit_spend += increase
                total_bonus_spend += p.proposed_bonus_amount
                total_equity_gsus += p.proposed_equity_gsus

        merit_by_rating = {
            r: str((rating_merit_sums[r] / Decimal(rating_counts[r])).quantize(Decimal("0.01")))
            + "%"
            for r in rating_counts
        }

        return {
            "cycle_id": str(cycle_id),
            "total_proposals": total_proposals,
            "status_breakdown": dict(status_counts),
            "compa_ratio_distribution": compa_buckets,
            "merit_by_rating": merit_by_rating,
            "total_merit_spend": str(total_merit_spend),
            "total_bonus_spend": str(total_bonus_spend),
            "total_equity_gsus": total_equity_gsus,
        }
