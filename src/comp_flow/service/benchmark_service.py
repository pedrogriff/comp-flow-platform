"""Market Benchmarking Service and Comparative Analysis Engine."""

from __future__ import annotations

import json
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.core.redis import RedisManager
from comp_flow.domain.benchmarks import (
    BenchmarkComparisonResult,
    BenchmarkSourceType,
    MarketBenchmark,
)
from comp_flow.domain.entities import MarketBenchmark as MarketBenchmarkEntity
from comp_flow.domain.models import JobFamily, JobLevel, LocationTier

logger = logging.getLogger(__name__)


class BenchmarkService:
    """Service managing benchmark lookups, comparative analytics, and win-rate estimations."""

    CACHE_TTL_SECONDS = 86400  # 24 hours

    def __init__(self, session: AsyncSession, redis: RedisManager | None = None) -> None:
        self.session = session
        self.redis = redis

    async def get_benchmark(
        self,
        job_family: JobFamily,
        job_level: JobLevel,
        geo_tier: LocationTier,
        source_type: BenchmarkSourceType | None = None,
    ) -> MarketBenchmark | None:
        """Retrieves market benchmark record, checking Redis cache first."""
        cache_key = f"benchmark:{job_family.value}:{job_level.value}:{geo_tier.value}:{source_type.value if source_type else 'DEFAULT'}"

        if self.redis:
            try:
                cached = await self.redis.get(cache_key)
                if cached:
                    data = json.loads(cached)
                    return MarketBenchmark(**data)
            except Exception as e:
                logger.warning(f"Redis cache read error: {e}")

        stmt = select(MarketBenchmarkEntity).where(
            MarketBenchmarkEntity.job_family == job_family,
            MarketBenchmarkEntity.job_level == job_level,
            MarketBenchmarkEntity.geo_tier == geo_tier,
            MarketBenchmarkEntity.is_active == True,  # noqa: E712
        )
        if source_type:
            stmt = stmt.where(MarketBenchmarkEntity.source_type == source_type)

        stmt = stmt.order_by(MarketBenchmarkEntity.effective_date.desc())
        res = await self.session.execute(stmt)
        entity = res.scalars().first()

        if not entity:
            return None

        benchmark = MarketBenchmark.model_validate(entity)

        if self.redis:
            try:
                dump_data = benchmark.model_dump(mode="json")
                await self.redis.set(
                    cache_key, json.dumps(dump_data), expire_seconds=self.CACHE_TTL_SECONDS
                )
            except Exception as e:
                logger.warning(f"Redis cache write error: {e}")

        return benchmark

    async def list_benchmarks(
        self,
        job_family: JobFamily | None = None,
        geo_tier: LocationTier | None = None,
    ) -> list[MarketBenchmark]:
        """Lists active benchmarks with optional filters."""
        stmt = select(MarketBenchmarkEntity).where(MarketBenchmarkEntity.is_active == True)  # noqa: E712

        if job_family:
            stmt = stmt.where(MarketBenchmarkEntity.job_family == job_family)
        if geo_tier:
            stmt = stmt.where(MarketBenchmarkEntity.geo_tier == geo_tier)

        stmt = stmt.order_by(
            MarketBenchmarkEntity.job_family,
            MarketBenchmarkEntity.job_level,
            MarketBenchmarkEntity.geo_tier,
        )
        res = await self.session.execute(stmt)
        entities = res.scalars().all()
        return [MarketBenchmark.model_validate(e) for e in entities]

    def compare_to_market(
        self,
        proposed_base: Decimal | float,
        benchmark: MarketBenchmark,
        signon_bonus: Decimal | float = Decimal("0.00"),
    ) -> BenchmarkComparisonResult:
        """Computes compa-ratio, range penetration, estimated market percentile, and win-rate."""
        base = Decimal(str(proposed_base))
        signon = Decimal(str(signon_bonus))

        p10 = benchmark.p10_base
        p50 = benchmark.p50_base
        p90 = benchmark.p90_base

        # 1. Compa-Ratio (Base / P50)
        compa_ratio = (base / p50).quantize(Decimal("0.001"))

        # 2. Range Penetration: (Base - P10) / (P90 - P10) * 100
        spread = p90 - p10
        if spread > Decimal("0"):
            range_penetration = (((base - p10) / spread) * Decimal("100.0")).quantize(
                Decimal("0.1")
            )
        else:
            range_penetration = Decimal("50.0")

        # 3. Market Percentile Estimation (Linear Piecewise)
        percentile_est = self._estimate_market_percentile(base, benchmark)

        # 4. Total Target Cash
        target_bonus = (base * (benchmark.target_bonus_pct / Decimal("100.0"))).quantize(
            Decimal("0.01")
        )
        ttc = base + target_bonus
        y1tc = ttc + signon

        # 5. Offer Win-Rate Probability Estimation (Logistic elasticity curve)
        # Median (P50) ~ 55% win rate, P75 ~ 82% win rate, P90 ~ 94% win rate
        win_rate = self._estimate_offer_win_rate(percentile_est)

        within_band = p10 <= base <= p90

        return BenchmarkComparisonResult(
            proposed_base=base,
            benchmark=benchmark,
            compa_ratio=compa_ratio,
            range_penetration_pct=range_penetration,
            market_percentile_estimate=percentile_est,
            total_target_cash=ttc,
            first_year_direct_comp=y1tc,
            predicted_offer_win_rate=win_rate,
            within_market_band=within_band,
        )

    def _estimate_market_percentile(self, base: Decimal, benchmark: MarketBenchmark) -> Decimal:
        """Estimates market percentile [0.0 to 100.0] via piecewise linear interpolation."""
        p10 = benchmark.p10_base
        p25 = benchmark.p25_base
        p50 = benchmark.p50_base
        p75 = benchmark.p75_base
        p90 = benchmark.p90_base

        if base <= p10:
            pct = max(Decimal("1.0"), (base / p10) * Decimal("10.0"))
        elif base <= p25:
            pct = Decimal("10.0") + ((base - p10) / (p25 - p10)) * Decimal("15.0")
        elif base <= p50:
            pct = Decimal("25.0") + ((base - p25) / (p50 - p25)) * Decimal("25.0")
        elif base <= p75:
            pct = Decimal("50.0") + ((base - p50) / (p75 - p50)) * Decimal("25.0")
        elif base <= p90:
            pct = Decimal("75.0") + ((base - p75) / (p90 - p75)) * Decimal("15.0")
        else:
            pct = min(Decimal("99.0"), Decimal("90.0") + ((base - p90) / p90) * Decimal("10.0"))

        return pct.quantize(Decimal("0.1"))

    def _estimate_offer_win_rate(self, percentile: Decimal) -> Decimal:
        """Logistic regression estimate of candidate offer acceptance probability."""
        p = float(percentile)
        # Sigmoid curve centered around 50th percentile with 60% baseline win rate
        k = 0.05
        midpoint = 45.0
        val = 1.0 / (1.0 + 2.71828 ** (-k * (p - midpoint)))
        win_rate_pct = min(max(val * 100.0, 10.0), 98.0)
        return Decimal(str(win_rate_pct)).quantize(Decimal("0.1"))
