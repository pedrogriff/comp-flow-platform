"""Unit and Integration Tests for Compensation Benchmarking ETL and Analytics Engine."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from comp_flow.domain.benchmarks import (
    BenchmarkPercentiles,
    BenchmarkSourceType,
    MarketBenchmark,
    RadfordLevel,
)
from comp_flow.domain.entities import Base
from comp_flow.domain.models import JobFamily, JobLevel, LocationTier
from comp_flow.etl.normalizer import BenchmarkNormalizer
from comp_flow.etl.pipeline import BenchmarkETLPipeline
from comp_flow.etl.sources.dol_lca_parser import DOLLCAParser
from comp_flow.etl.sources.seed_loader import BenchmarkSeedLoader
from comp_flow.etl.statistical_engine import BenchmarkStatisticalEngine
from comp_flow.service.benchmark_service import BenchmarkService

# --- Normalization Tests ---

def test_wage_unit_normalization():
    """Verifies hourly, monthly, weekly, and annual wage conversions."""
    hourly = BenchmarkNormalizer.normalize_wage(Decimal("100.00"), "HOUR")
    assert hourly == Decimal("208000.00")

    monthly = BenchmarkNormalizer.normalize_wage(Decimal("20000.00"), "MONTH")
    assert monthly == Decimal("240000.00")

    biweekly = BenchmarkNormalizer.normalize_wage(Decimal("10000.00"), "BI-WEEKLY")
    assert biweekly == Decimal("260000.00")

    annual = BenchmarkNormalizer.normalize_wage(Decimal("320000.00"), "YEAR")
    assert annual == Decimal("320000.00")


def test_geo_tier_normalization():
    """Verifies city and state mapping to US_ZONE_1, US_ZONE_2, US_ZONE_3."""
    assert BenchmarkNormalizer.normalize_geo_tier("San Francisco", "CA") == LocationTier.US_ZONE_1
    assert BenchmarkNormalizer.normalize_geo_tier("New York", "NY") == LocationTier.US_ZONE_1
    assert BenchmarkNormalizer.normalize_geo_tier("Sunnyvale", "CA") == LocationTier.US_ZONE_1
    assert BenchmarkNormalizer.normalize_geo_tier("Seattle", "WA") == LocationTier.US_ZONE_2
    assert BenchmarkNormalizer.normalize_geo_tier("Austin", "TX") == LocationTier.US_ZONE_2
    assert BenchmarkNormalizer.normalize_geo_tier("Chicago", "IL") == LocationTier.US_ZONE_2
    assert BenchmarkNormalizer.normalize_geo_tier("Miami", "FL") == LocationTier.US_ZONE_3
    assert BenchmarkNormalizer.normalize_geo_tier("Remote", "US") == LocationTier.US_ZONE_3


def test_role_classification_and_radford_mapping():
    """Verifies title keyword parsing to JobFamily, JobLevel, and Radford level."""
    # Senior Infrastructure Engineer
    r1 = BenchmarkNormalizer.normalize_role("Senior Systems Infrastructure Engineer")
    assert r1.job_family == JobFamily.SYSTEMS_INFRASTRUCTURE
    assert r1.job_level == JobLevel.L5
    assert r1.radford_level == RadfordLevel.P3

    # Staff Machine Learning Engineer
    r2 = BenchmarkNormalizer.normalize_role("Staff Machine Learning Platform Engineer")
    assert r2.job_family == JobFamily.MACHINE_LEARNING
    assert r2.job_level == JobLevel.L6
    assert r2.radford_level == RadfordLevel.P4

    # Principal Software Engineer
    r3 = BenchmarkNormalizer.normalize_role("Principal Software Architect")
    assert r3.job_family == JobFamily.SOFTWARE_ENGINEERING
    assert r3.job_level == JobLevel.L8
    assert r3.radford_level == RadfordLevel.P6

    # Associate Product Manager
    r4 = BenchmarkNormalizer.normalize_role("Associate Product Manager")
    assert r4.job_family == JobFamily.PRODUCT_MANAGEMENT
    assert r4.job_level == JobLevel.L3
    assert r4.radford_level == RadfordLevel.P1


# --- Statistical Engine Tests ---

def test_iqr_outlier_filtering():
    """Verifies Tukey's IQR rule strips extreme anomalous salary entries."""
    wages = [
        Decimal("10000"),   # Extreme low outlier
        Decimal("180000"),
        Decimal("190000"),
        Decimal("200000"),
        Decimal("210000"),
        Decimal("220000"),
        Decimal("230000"),
        Decimal("240000"),
        Decimal("2000000"), # Extreme high outlier
    ]
    cleaned = BenchmarkStatisticalEngine.filter_outliers_iqr(wages)
    assert Decimal("10000") not in cleaned
    assert Decimal("2000000") not in cleaned
    assert len(cleaned) == 7


def test_percentile_calculations():
    """Verifies P10, P25, P50, P75, P90 percentile calculations."""
    wages = [Decimal(str(w)) for w in [150000, 175000, 200000, 225000, 250000, 275000, 300000]]
    res = BenchmarkStatisticalEngine.calculate_percentiles(wages)
    assert res.p50_base == Decimal("225000.00")
    assert res.p10_base < res.p25_base < res.p50_base < res.p75_base < res.p90_base
    assert res.sample_size == 7


def test_survey_aging_compound_formula():
    """Verifies that aged percentiles strictly grow by (1 + r)^(days / 365.25)."""
    base_percentiles = BenchmarkPercentiles(
        p10_base=Decimal("100000.00"),
        p25_base=Decimal("150000.00"),
        p50_base=Decimal("200000.00"),
        p75_base=Decimal("250000.00"),
        p90_base=Decimal("300000.00"),
    )
    eff_date = date(2025, 1, 1)
    target_date = date(2026, 1, 1)  # exactly 365 days (~1.0 year)
    aged = BenchmarkStatisticalEngine.age_wage_dataset(
        base_percentiles,
        effective_date=eff_date,
        target_date=target_date,
        annual_rate=Decimal("0.0400"),  # 4.0%
    )

    # 200,000 * 1.04 ~= 208,000
    assert aged.p50_base > Decimal("207500.00")
    assert aged.p50_base < Decimal("208500.00")


def test_monotonic_smoothing():
    """Verifies monotonic correction when higher levels have noisy sample data."""
    level_data = {
        "L3": BenchmarkPercentiles(p10_base=Decimal("120000"), p25_base=Decimal("140000"), p50_base=Decimal("160000"), p75_base=Decimal("180000"), p90_base=Decimal("200000")),
        "L4": BenchmarkPercentiles(p10_base=Decimal("110000"), p25_base=Decimal("130000"), p50_base=Decimal("150000"), p75_base=Decimal("170000"), p90_base=Decimal("190000")), # Inverted!
        "L5": BenchmarkPercentiles(p10_base=Decimal("180000"), p25_base=Decimal("210000"), p50_base=Decimal("240000"), p75_base=Decimal("270000"), p90_base=Decimal("300000")),
    }
    smoothed = BenchmarkStatisticalEngine.smooth_level_monotonicity(level_data)
    assert smoothed["L4"].p50_base >= smoothed["L3"].p50_base
    assert smoothed["L5"].p50_base >= smoothed["L4"].p50_base


# --- DOL Parser Tests ---

def test_dol_lca_csv_parser():
    """Verifies extraction and normalization of DOL OFLC CSV rows."""
    sample_csv = """CASE_NUMBER,EMPLOYER_NAME,JOB_TITLE,SOC_CODE,WAGE_RATE_OF_PAY_FROM,WAGE_UNIT_OF_PAY,WORKSITE_CITY,WORKSITE_STATE,DECISION_DATE
I-200-24001-001,GOOGLE LLC,Staff Software Engineer,15-1252.00,310000,Year,Mountain View,CA,2025-04-15
I-200-24001-002,META PLATFORMS INC,Senior Infrastructure Engineer,15-1244.00,265000,Year,Seattle,WA,2025-05-10
I-200-24001-003,AMAZON.COM SERVICES LLC,Software Development Engineer II,15-1252.00,95.50,Hour,Austin,TX,2025-06-01
"""
    records = DOLLCAParser.parse_csv_stream(sample_csv)
    assert len(records) == 3

    # Google Record
    assert records[0].employer_name == "GOOGLE LLC"
    assert records[0].wage_rate == Decimal("310000.00")

    # Amazon Record (Hourly $95.50 * 2080 = $198,640)
    assert records[2].employer_name == "AMAZON.COM SERVICES LLC"
    assert records[2].wage_rate == Decimal("198640.00")


# --- Seed Loader Tests ---

def test_benchmark_seed_loader_matrix():
    """Verifies matrix generation across all 5 job families * 6 levels * 3 geo zones = 90 rows."""
    seeds = BenchmarkSeedLoader.generate_seed_benchmarks()
    assert len(seeds) == 5 * 6 * 3
    for b in seeds:
        assert b.p10_base < b.p25_base < b.p50_base < b.p75_base < b.p90_base
        assert b.p50_base > Decimal("100000.00")


# --- Service & Analytics Tests ---

def test_benchmark_service_compare():
    """Verifies compa-ratio, percentile rank, and offer win-rate predictions."""
    sample_benchmark = MarketBenchmark(
        soc_code="15-1252.00",
        job_family=JobFamily.SOFTWARE_ENGINEERING,
        job_level=JobLevel.L5,
        radford_level=RadfordLevel.P3,
        geo_tier=LocationTier.US_ZONE_1,
        p10_base=Decimal("205000.00"),
        p25_base=Decimal("230000.00"),
        p50_base=Decimal("255000.00"),
        p75_base=Decimal("280000.00"),
        p90_base=Decimal("305000.00"),
        target_bonus_pct=Decimal("15.00"),
        p50_equity_gsus=900,
        p75_equity_gsus=1350,
        sample_size=940,
        source_type=BenchmarkSourceType.SYNTHETIC,
        effective_date=date(2026, 1, 1),
        aged_to_date=date(2026, 8, 27),
    )

    dummy_session = None
    service = BenchmarkService(dummy_session)

    # 1. Compare midpoint offer ($255,000)
    res_mid = service.compare_to_market(
        proposed_base=Decimal("255000.00"),
        benchmark=sample_benchmark,
        signon_bonus=Decimal("25000.00"),
    )
    assert res_mid.compa_ratio == Decimal("1.000")
    assert res_mid.range_penetration_pct == Decimal("50.0")
    assert res_mid.market_percentile_estimate == Decimal("50.0")
    assert res_mid.total_target_cash == Decimal("293250.00")  # 255k + 15%
    assert res_mid.first_year_direct_comp == Decimal("318250.00")  # TTC + 25k signon
    assert res_mid.predicted_offer_win_rate >= Decimal("55.0")
    assert res_mid.within_market_band is True

    # 2. Compare 75th percentile offer ($280,000)
    res_p75 = service.compare_to_market(
        proposed_base=Decimal("280000.00"),
        benchmark=sample_benchmark,
    )
    assert res_p75.compa_ratio > Decimal("1.09")
    assert res_p75.market_percentile_estimate == Decimal("75.0")
    assert res_p75.predicted_offer_win_rate > res_mid.predicted_offer_win_rate


# --- Async Integration Test with SQLite DB ---

@pytest.mark.asyncio
async def test_end_to_end_etl_pipeline_with_db():
    """Verifies end-to-end ETL ingestion and database persistence in an async session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        pipeline = BenchmarkETLPipeline(session)

        # 1. Seed complete benchmark matrix
        benchmarks = await pipeline.seed_market_benchmarks()
        assert len(benchmarks) == 90

        # 2. Query benchmark via BenchmarkService
        service = BenchmarkService(session)
        l6_bench = await service.get_benchmark(
            job_family=JobFamily.SYSTEMS_INFRASTRUCTURE,
            job_level=JobLevel.L6,
            geo_tier=LocationTier.US_ZONE_1,
        )
        assert l6_bench is not None
        assert l6_bench.radford_level == RadfordLevel.P4
        assert l6_bench.p50_base == Decimal("330000.00")

        # 3. Ingest raw DOL LCA CSV rows
        dol_sample = """CASE_NUMBER,EMPLOYER_NAME,JOB_TITLE,SOC_CODE,WAGE_RATE_OF_PAY_FROM,WAGE_UNIT_OF_PAY,WORKSITE_CITY,WORKSITE_STATE,DECISION_DATE
I-200-01,CLOUD CORP,Principal Systems Architect,15-1244.00,420000,Year,San Francisco,CA,2025-01-01
I-200-02,CLOUD CORP,Principal Systems Architect,15-1244.00,430000,Year,San Francisco,CA,2025-01-01
I-200-03,CLOUD CORP,Principal Systems Architect,15-1244.00,410000,Year,San Francisco,CA,2025-01-01
I-200-04,CLOUD CORP,Principal Systems Architect,15-1244.00,425000,Year,San Francisco,CA,2025-01-01
I-200-05,CLOUD CORP,Principal Systems Architect,15-1244.00,415000,Year,San Francisco,CA,2025-01-01
"""
        ingested = await pipeline.ingest_dol_lca_csv(dol_sample)
        assert len(ingested) == 1
        assert ingested[0].job_family == JobFamily.SYSTEMS_INFRASTRUCTURE
        assert ingested[0].job_level == JobLevel.L8
        assert ingested[0].sample_size == 5

    await engine.dispose()
