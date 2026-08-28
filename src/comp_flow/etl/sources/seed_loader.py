"""High-fidelity seed data generator for Enterprise Compensation Benchmarks."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from comp_flow.domain.benchmarks import BenchmarkSourceType, MarketBenchmark, RadfordLevel
from comp_flow.domain.models import JobFamily, JobLevel, LocationTier
from comp_flow.etl.normalizer import BenchmarkNormalizer


class BenchmarkSeedLoader:
    """Generates comprehensive market benchmarks spanning all engineering families and levels."""

    # Baseline Zone 1 (SF Bay Area / NYC) P50 Base Salaried Ranges (2026 Tech Market)
    BASELINE_ZONE_1: dict[tuple[JobFamily, JobLevel], dict[str, Any]] = {
        # Software Engineering
        (JobFamily.SOFTWARE_ENGINEERING, JobLevel.L3): {
            "p10": 135000, "p25": 150000, "p50": 165000, "p75": 180000, "p90": 195000,
            "target_bonus": Decimal("10.00"), "p50_equity": 400, "p75_equity": 600, "sample_size": 420,
        },
        (JobFamily.SOFTWARE_ENGINEERING, JobLevel.L4): {
            "p10": 165000, "p25": 185000, "p50": 205000, "p75": 225000, "p90": 245000,
            "target_bonus": Decimal("15.00"), "p50_equity": 650, "p75_equity": 950, "sample_size": 680,
        },
        (JobFamily.SOFTWARE_ENGINEERING, JobLevel.L5): {
            "p10": 205000, "p25": 230000, "p50": 255000, "p75": 280000, "p90": 305000,
            "target_bonus": Decimal("15.00"), "p50_equity": 900, "p75_equity": 1350, "sample_size": 940,
        },
        (JobFamily.SOFTWARE_ENGINEERING, JobLevel.L6): {
            "p10": 255000, "p25": 285000, "p50": 315000, "p75": 350000, "p90": 385000,
            "target_bonus": Decimal("20.00"), "p50_equity": 1400, "p75_equity": 2100, "sample_size": 510,
        },
        (JobFamily.SOFTWARE_ENGINEERING, JobLevel.L7): {
            "p10": 315000, "p25": 355000, "p50": 395000, "p75": 440000, "p90": 490000,
            "target_bonus": Decimal("25.00"), "p50_equity": 2200, "p75_equity": 3300, "sample_size": 260,
        },
        (JobFamily.SOFTWARE_ENGINEERING, JobLevel.L8): {
            "p10": 395000, "p25": 445000, "p50": 500000, "p75": 560000, "p90": 630000,
            "target_bonus": Decimal("30.00"), "p50_equity": 3500, "p75_equity": 5200, "sample_size": 110,
        },

        # Systems & Infrastructure Engineering (+5% premium)
        (JobFamily.SYSTEMS_INFRASTRUCTURE, JobLevel.L3): {
            "p10": 140000, "p25": 155000, "p50": 172000, "p75": 188000, "p90": 205000,
            "target_bonus": Decimal("10.00"), "p50_equity": 420, "p75_equity": 630, "sample_size": 310,
        },
        (JobFamily.SYSTEMS_INFRASTRUCTURE, JobLevel.L4): {
            "p10": 172000, "p25": 192000, "p50": 215000, "p75": 236000, "p90": 258000,
            "target_bonus": Decimal("15.00"), "p50_equity": 700, "p75_equity": 1000, "sample_size": 480,
        },
        (JobFamily.SYSTEMS_INFRASTRUCTURE, JobLevel.L5): {
            "p10": 215000, "p25": 240000, "p50": 268000, "p75": 295000, "p90": 320000,
            "target_bonus": Decimal("15.00"), "p50_equity": 950, "p75_equity": 1400, "sample_size": 650,
        },
        (JobFamily.SYSTEMS_INFRASTRUCTURE, JobLevel.L6): {
            "p10": 268000, "p25": 298000, "p50": 330000, "p75": 365000, "p90": 405000,
            "target_bonus": Decimal("20.00"), "p50_equity": 1500, "p75_equity": 2250, "sample_size": 390,
        },
        (JobFamily.SYSTEMS_INFRASTRUCTURE, JobLevel.L7): {
            "p10": 330000, "p25": 370000, "p50": 415000, "p75": 460000, "p90": 515000,
            "target_bonus": Decimal("25.00"), "p50_equity": 2400, "p75_equity": 3600, "sample_size": 180,
        },
        (JobFamily.SYSTEMS_INFRASTRUCTURE, JobLevel.L8): {
            "p10": 415000, "p25": 465000, "p50": 525000, "p75": 590000, "p90": 660000,
            "target_bonus": Decimal("30.00"), "p50_equity": 3800, "p75_equity": 5700, "sample_size": 75,
        },

        # Machine Learning / AI Platform (+10% premium)
        (JobFamily.MACHINE_LEARNING, JobLevel.L3): {
            "p10": 145000, "p25": 162000, "p50": 180000, "p75": 198000, "p90": 215000,
            "target_bonus": Decimal("10.00"), "p50_equity": 500, "p75_equity": 750, "sample_size": 280,
        },
        (JobFamily.MACHINE_LEARNING, JobLevel.L4): {
            "p10": 180000, "p25": 202000, "p50": 226000, "p75": 250000, "p90": 272000,
            "target_bonus": Decimal("15.00"), "p50_equity": 800, "p75_equity": 1200, "sample_size": 420,
        },
        (JobFamily.MACHINE_LEARNING, JobLevel.L5): {
            "p10": 225000, "p25": 252000, "p50": 280000, "p75": 310000, "p90": 340000,
            "target_bonus": Decimal("15.00"), "p50_equity": 1100, "p75_equity": 1650, "sample_size": 590,
        },
        (JobFamily.MACHINE_LEARNING, JobLevel.L6): {
            "p10": 280000, "p25": 315000, "p50": 350000, "p75": 390000, "p90": 430000,
            "target_bonus": Decimal("20.00"), "p50_equity": 1750, "p75_equity": 2600, "sample_size": 330,
        },
        (JobFamily.MACHINE_LEARNING, JobLevel.L7): {
            "p10": 350000, "p25": 395000, "p50": 445000, "p75": 495000, "p90": 555000,
            "target_bonus": Decimal("25.00"), "p50_equity": 2700, "p75_equity": 4050, "sample_size": 150,
        },
        (JobFamily.MACHINE_LEARNING, JobLevel.L8): {
            "p10": 445000, "p25": 500000, "p50": 565000, "p75": 635000, "p90": 715000,
            "target_bonus": Decimal("30.00"), "p50_equity": 4200, "p75_equity": 6300, "sample_size": 60,
        },

        # Data Science
        (JobFamily.DATA_SCIENCE, JobLevel.L3): {
            "p10": 130000, "p25": 145000, "p50": 160000, "p75": 175000, "p90": 190000,
            "target_bonus": Decimal("10.00"), "p50_equity": 380, "p75_equity": 570, "sample_size": 240,
        },
        (JobFamily.DATA_SCIENCE, JobLevel.L4): {
            "p10": 160000, "p25": 180000, "p50": 200000, "p75": 220000, "p90": 240000,
            "target_bonus": Decimal("15.00"), "p50_equity": 600, "p75_equity": 900, "sample_size": 390,
        },
        (JobFamily.DATA_SCIENCE, JobLevel.L5): {
            "p10": 200000, "p25": 225000, "p50": 250000, "p75": 275000, "p90": 300000,
            "target_bonus": Decimal("15.00"), "p50_equity": 850, "p75_equity": 1250, "sample_size": 470,
        },
        (JobFamily.DATA_SCIENCE, JobLevel.L6): {
            "p10": 250000, "p25": 280000, "p50": 310000, "p75": 345000, "p90": 375000,
            "target_bonus": Decimal("20.00"), "p50_equity": 1350, "p75_equity": 2000, "sample_size": 280,
        },
        (JobFamily.DATA_SCIENCE, JobLevel.L7): {
            "p10": 310000, "p25": 350000, "p50": 390000, "p75": 435000, "p90": 480000,
            "target_bonus": Decimal("25.00"), "p50_equity": 2100, "p75_equity": 3150, "sample_size": 130,
        },
        (JobFamily.DATA_SCIENCE, JobLevel.L8): {
            "p10": 390000, "p25": 440000, "p50": 490000, "p75": 550000, "p90": 615000,
            "target_bonus": Decimal("30.00"), "p50_equity": 3300, "p75_equity": 4950, "sample_size": 50,
        },

        # Product Management
        (JobFamily.PRODUCT_MANAGEMENT, JobLevel.L3): {
            "p10": 135000, "p25": 150000, "p50": 165000, "p75": 180000, "p90": 195000,
            "target_bonus": Decimal("10.00"), "p50_equity": 350, "p75_equity": 525, "sample_size": 190,
        },
        (JobFamily.PRODUCT_MANAGEMENT, JobLevel.L4): {
            "p10": 165000, "p25": 185000, "p50": 205000, "p75": 225000, "p90": 245000,
            "target_bonus": Decimal("15.00"), "p50_equity": 550, "p75_equity": 825, "sample_size": 310,
        },
        (JobFamily.PRODUCT_MANAGEMENT, JobLevel.L5): {
            "p10": 205000, "p25": 230000, "p50": 255000, "p75": 280000, "p90": 305000,
            "target_bonus": Decimal("15.00"), "p50_equity": 800, "p75_equity": 1200, "sample_size": 420,
        },
        (JobFamily.PRODUCT_MANAGEMENT, JobLevel.L6): {
            "p10": 255000, "p25": 285000, "p50": 315000, "p75": 350000, "p90": 385000,
            "target_bonus": Decimal("20.00"), "p50_equity": 1250, "p75_equity": 1875, "sample_size": 250,
        },
        (JobFamily.PRODUCT_MANAGEMENT, JobLevel.L7): {
            "p10": 315000, "p25": 355000, "p50": 395000, "p75": 440000, "p90": 490000,
            "target_bonus": Decimal("25.00"), "p50_equity": 1950, "p75_equity": 2925, "sample_size": 120,
        },
        (JobFamily.PRODUCT_MANAGEMENT, JobLevel.L8): {
            "p10": 395000, "p25": 445000, "p50": 500000, "p75": 560000, "p90": 630000,
            "target_bonus": Decimal("30.00"), "p50_equity": 3100, "p75_equity": 4650, "sample_size": 45,
        },
    }

    # Geo Tier Multipliers
    GEO_MULTIPLIERS = {
        LocationTier.US_ZONE_1: Decimal("1.00"),  # SF / NYC
        LocationTier.US_ZONE_2: Decimal("0.90"),  # Seattle / Austin / Boston
        LocationTier.US_ZONE_3: Decimal("0.80"),  # National / Remote
    }

    @classmethod
    def generate_seed_benchmarks(cls, effective_date: date | None = None) -> list[MarketBenchmark]:
        """Generates complete matrix of benchmarks for all families, levels, and geo tiers."""
        eff_date = effective_date or date(2026, 1, 1)
        today = date.today()
        benchmarks: list[MarketBenchmark] = []

        for (family, level), data in cls.BASELINE_ZONE_1.items():
            radford = BenchmarkNormalizer.RADFORD_LEVEL_MAP.get(level, RadfordLevel.P3)
            soc = BenchmarkNormalizer.SOC_MAPPINGS.get(family, "15-1252.00")

            for geo, factor in cls.GEO_MULTIPLIERS.items():
                benchmarks.append(
                    MarketBenchmark(
                        id=uuid.uuid4(),
                        soc_code=soc,
                        job_family=family,
                        job_level=level,
                        radford_level=radford,
                        geo_tier=geo,
                        currency="USD",
                        p10_base=(Decimal(str(data["p10"])) * factor).quantize(Decimal("0.01")),
                        p25_base=(Decimal(str(data["p25"])) * factor).quantize(Decimal("0.01")),
                        p50_base=(Decimal(str(data["p50"])) * factor).quantize(Decimal("0.01")),
                        p75_base=(Decimal(str(data["p75"])) * factor).quantize(Decimal("0.01")),
                        p90_base=(Decimal(str(data["p90"])) * factor).quantize(Decimal("0.01")),
                        target_bonus_pct=data["target_bonus"],
                        p50_equity_gsus=int(data["p50_equity"]),
                        p75_equity_gsus=int(data["p75_equity"]),
                        sample_size=int(data["sample_size"]),
                        source_type=BenchmarkSourceType.SYNTHETIC,
                        effective_date=eff_date,
                        aged_to_date=today,
                        annual_aging_rate=Decimal("0.0400"),
                        is_active=True,
                    )
                )

        return benchmarks
