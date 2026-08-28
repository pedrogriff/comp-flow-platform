"""End-to-End ETL Pipeline for Compensation Market Benchmarks."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.domain.benchmarks import (
    BenchmarkSourceType,
    MarketBenchmark,
)
from comp_flow.domain.entities import MarketBenchmark as MarketBenchmarkEntity
from comp_flow.domain.models import JobFamily, JobLevel, LocationTier
from comp_flow.etl.normalizer import BenchmarkNormalizer
from comp_flow.etl.sources.dol_lca_parser import DOLLCAParser
from comp_flow.etl.sources.seed_loader import BenchmarkSeedLoader
from comp_flow.etl.statistical_engine import BenchmarkStatisticalEngine

logger = logging.getLogger(__name__)


class BenchmarkETLPipeline:
    """Orchestrates ingestion, normalization, statistical cleaning, aging, and database persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest_dol_lca_csv(
        self,
        csv_content: str,
        source_type: BenchmarkSourceType = BenchmarkSourceType.DOL_OFLC,
        annual_aging_rate: Decimal = Decimal("0.0400"),
    ) -> list[MarketBenchmark]:
        """Ingests raw DOL LCA CSV data, computes statistical percentiles with aging, and persists to DB."""
        observations = DOLLCAParser.parse_csv_stream(csv_content)
        if not observations:
            logger.warning("No valid wage observations parsed from CSV.")
            return []

        # Group observations by (JobFamily, JobLevel, LocationTier)
        cohorts: dict[tuple[JobFamily, JobLevel, LocationTier], list[Decimal]] = defaultdict(list)
        eff_dates: dict[tuple[JobFamily, JobLevel, LocationTier], date] = {}

        for obs in observations:
            role = BenchmarkNormalizer.normalize_role(obs.job_title, obs.soc_code)
            geo = BenchmarkNormalizer.normalize_geo_tier(obs.city, obs.state, obs.metro_area)
            key = (role.job_family, role.job_level, geo)

            cohorts[key].append(obs.wage_rate)
            if key not in eff_dates or obs.effective_date < eff_dates[key]:
                eff_dates[key] = obs.effective_date

        benchmarks: list[MarketBenchmark] = []
        today = date.today()

        for (family, level, geo), wages in cohorts.items():
            if len(wages) < BenchmarkStatisticalEngine.MIN_SAFE_HARBOR_COUNT:
                # Do not emit benchmark if sample size violates Safe Harbor antitrust limits
                logger.info(
                    f"Skipping cohort ({family}, {level}, {geo}): sample size {len(wages)} < 5"
                )
                continue

            raw_percentiles = BenchmarkStatisticalEngine.calculate_percentiles(wages)
            eff_date = eff_dates.get((family, level, geo), date(2025, 1, 1))

            # Age percentiles forward to current date
            aged_percentiles = BenchmarkStatisticalEngine.age_wage_dataset(
                raw_percentiles,
                effective_date=eff_date,
                target_date=today,
                annual_rate=annual_aging_rate,
            )

            radford = BenchmarkNormalizer.RADFORD_LEVEL_MAP.get(
                level, BenchmarkNormalizer.RADFORD_LEVEL_MAP[JobLevel.L5]
            )
            soc = BenchmarkNormalizer.SOC_MAPPINGS.get(family, "15-1252.00")

            # Default bonus & equity guideline targets based on level
            target_bonus = (
                Decimal("10.00")
                if level == JobLevel.L3
                else (Decimal("15.00") if level in (JobLevel.L4, JobLevel.L5) else Decimal("20.00"))
            )
            p50_eq = 400 if level == JobLevel.L3 else (900 if level == JobLevel.L5 else 1400)

            bench = MarketBenchmark(
                soc_code=soc,
                job_family=family,
                job_level=level,
                radford_level=radford,
                geo_tier=geo,
                currency="USD",
                p10_base=aged_percentiles.p10_base,
                p25_base=aged_percentiles.p25_base,
                p50_base=aged_percentiles.p50_base,
                p75_base=aged_percentiles.p75_base,
                p90_base=aged_percentiles.p90_base,
                target_bonus_pct=target_bonus,
                p50_equity_gsus=p50_eq,
                p75_equity_gsus=int(p50_eq * 1.5),
                sample_size=aged_percentiles.sample_size,
                source_type=source_type,
                effective_date=eff_date,
                aged_to_date=today,
                annual_aging_rate=annual_aging_rate,
                is_active=True,
            )
            benchmarks.append(bench)

        await self._persist_benchmarks(benchmarks)
        return benchmarks

    async def seed_market_benchmarks(self) -> list[MarketBenchmark]:
        """Seeds the complete statistically verified 2026 market benchmarks."""
        benchmarks = BenchmarkSeedLoader.generate_seed_benchmarks()
        await self._persist_benchmarks(benchmarks)
        return benchmarks

    async def _persist_benchmarks(self, benchmarks: Sequence[MarketBenchmark]) -> None:
        """Batch upserts market benchmark domain records into PostgreSQL."""
        for b in benchmarks:
            stmt = select(MarketBenchmarkEntity).where(
                MarketBenchmarkEntity.job_family == b.job_family,
                MarketBenchmarkEntity.job_level == b.job_level,
                MarketBenchmarkEntity.geo_tier == b.geo_tier,
                MarketBenchmarkEntity.source_type == b.source_type,
                MarketBenchmarkEntity.effective_date == b.effective_date,
            )
            res = await self.session.execute(stmt)
            existing = res.scalar_one_or_none()

            if existing:
                existing.p10_base = b.p10_base
                existing.p25_base = b.p25_base
                existing.p50_base = b.p50_base
                existing.p75_base = b.p75_base
                existing.p90_base = b.p90_base
                existing.target_bonus_pct = b.target_bonus_pct
                existing.p50_equity_gsus = b.p50_equity_gsus
                existing.p75_equity_gsus = b.p75_equity_gsus
                existing.sample_size = b.sample_size
                existing.aged_to_date = b.aged_to_date
                existing.annual_aging_rate = b.annual_aging_rate
                existing.is_active = b.is_active
            else:
                entity = MarketBenchmarkEntity(
                    id=b.id,
                    soc_code=b.soc_code,
                    job_family=b.job_family,
                    job_level=b.job_level,
                    radford_level=b.radford_level,
                    geo_tier=b.geo_tier,
                    metro_area=b.metro_area,
                    currency=b.currency,
                    p10_base=b.p10_base,
                    p25_base=b.p25_base,
                    p50_base=b.p50_base,
                    p75_base=b.p75_base,
                    p90_base=b.p90_base,
                    target_bonus_pct=b.target_bonus_pct,
                    p50_equity_gsus=b.p50_equity_gsus,
                    p75_equity_gsus=b.p75_equity_gsus,
                    sample_size=b.sample_size,
                    source_type=b.source_type,
                    effective_date=b.effective_date,
                    aged_to_date=b.aged_to_date,
                    annual_aging_rate=b.annual_aging_rate,
                    is_active=b.is_active,
                )
                self.session.add(entity)

        await self.session.commit()
        logger.info(f"Successfully persisted {len(benchmarks)} market benchmarks to database.")
