"""Data Normalization Engine for Benchmarking ETL."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import NamedTuple

from comp_flow.domain.benchmarks import RadfordLevel
from comp_flow.domain.models import JobFamily, JobLevel, LocationTier


class NormalizedRole(NamedTuple):
    """Normalized role classification tuple."""

    job_family: JobFamily
    job_level: JobLevel
    radford_level: RadfordLevel
    soc_code: str


class BenchmarkNormalizer:
    """Normalizes titles, SOC codes, geographic locations, and wage units."""

    # Standard Occupational Classification (SOC) Mappings
    SOC_MAPPINGS: dict[JobFamily, str] = {
        JobFamily.SOFTWARE_ENGINEERING: "15-1252.00",  # Software Developers
        JobFamily.SYSTEMS_INFRASTRUCTURE: "15-1244.00",  # Network and Computer Systems Architects
        JobFamily.MACHINE_LEARNING: "15-2051.00",  # Data Scientists / ML Engineers
        JobFamily.DATA_SCIENCE: "15-2051.01",  # Data Scientists
        JobFamily.PRODUCT_MANAGEMENT: "11-3021.00",  # Computer and Information Systems Managers
    }

    # Radford to Internal Level Bi-directional Mapping
    RADFORD_LEVEL_MAP: dict[JobLevel, RadfordLevel] = {
        JobLevel.L3: RadfordLevel.P1,
        JobLevel.L4: RadfordLevel.P2,
        JobLevel.L5: RadfordLevel.P3,
        JobLevel.L6: RadfordLevel.P4,
        JobLevel.L7: RadfordLevel.P5,
        JobLevel.L8: RadfordLevel.P6,
    }

    # Metro / City to Geo Tier Mapping
    ZONE_1_LOCATIONS = {
        "SAN FRANCISCO",
        "SAN JOSE",
        "SUNNYVALE",
        "PALO ALTO",
        "MOUNTAIN VIEW",
        "SAN MATEO",
        "REDWOOD CITY",
        "SANTA CLARA",
        "OAKLAND",
        "BERKELEY",
        "MENLO PARK",
        "NEW YORK",
        "MANHATTAN",
        "BROOKLYN",
        "JERSEY CITY",
    }

    ZONE_2_LOCATIONS = {
        "SEATTLE",
        "BELLEVUE",
        "REDMOND",
        "KIRKLAND",
        "AUSTIN",
        "BOSTON",
        "CAMBRIDGE",
        "CHICAGO",
        "LOS ANGELES",
        "SAN DIEGO",
        "DENVER",
        "BOULDER",
        "WASHINGTON",
        "MCLEAN",
        "ARLINGTON",
        "ATLANTA",
    }

    @classmethod
    def normalize_wage(cls, raw_wage: Decimal | float | str, wage_unit: str) -> Decimal:
        """Converts any wage unit (hourly, monthly, bi-weekly) to annualized USD."""
        val = Decimal(str(raw_wage))
        unit = wage_unit.upper().strip()

        if unit in ("HR", "HOUR", "HOURLY"):
            return (val * Decimal("2080")).quantize(Decimal("0.01"))
        elif unit in ("WK", "WEEK", "WEEKLY"):
            return (val * Decimal("52")).quantize(Decimal("0.01"))
        elif unit in ("BI", "BI-WEEKLY", "BIWEEKLY", "BI_WEEKLY", "BW"):
            return (val * Decimal("26")).quantize(Decimal("0.01"))
        elif unit in ("MTH", "MONTH", "MONTHLY", "MO"):
            return (val * Decimal("12")).quantize(Decimal("0.01"))
        elif unit in ("YR", "YEAR", "ANNUAL", "YEARLY"):
            return val.quantize(Decimal("0.01"))
        return val.quantize(Decimal("0.01"))

    @classmethod
    def normalize_geo_tier(cls, city: str | None, state: str | None, metro: str | None = None) -> LocationTier:
        """Classifies city/state/metro into US_ZONE_1, US_ZONE_2, or US_ZONE_3."""
        text_tokens = " ".join(filter(None, [city, state, metro])).upper()

        for loc in cls.ZONE_1_LOCATIONS:
            if loc in text_tokens:
                return LocationTier.US_ZONE_1

        for loc in cls.ZONE_2_LOCATIONS:
            if loc in text_tokens:
                return LocationTier.US_ZONE_2

        return LocationTier.US_ZONE_3

    @classmethod
    def normalize_role(cls, title: str, soc_code: str | None = None) -> NormalizedRole:
        """Infers JobFamily, JobLevel, RadfordLevel, and SOC Code from a title string."""
        clean_title = title.upper().strip()

        # 1. Infer Job Family with high-specificity precedence
        family = JobFamily.SOFTWARE_ENGINEERING
        if any(w in clean_title for w in ["MACHINE LEARNING", "ML ", "AI ", "DEEP LEARNING", "NLP", "COMPUTER VISION", "LLM"]):
            family = JobFamily.MACHINE_LEARNING
        elif any(w in clean_title for w in ["DATA SCIENTIST", "DATA SCIENCE", "ANALYTICS", "RESEARCH SCIENTIST"]):
            family = JobFamily.DATA_SCIENCE
        elif any(w in clean_title for w in ["PRODUCT MANAGER", "PRODUCT MANAGEMENT", "TECHNICAL PROGRAM"]):
            family = JobFamily.PRODUCT_MANAGEMENT
        elif any(w in clean_title for w in ["INFRA", "SYSTEMS", "DEVOPS", "SRE", "RELIABILITY", "KERNEL", "PLATFORM", "NETWORK", "SECURITY"]):
            family = JobFamily.SYSTEMS_INFRASTRUCTURE

        # 2. Infer Job Level
        level = JobLevel.L5  # Default baseline is Senior / Proficient
        if any(w in clean_title for w in ["PRINCIPAL", "DISTINGUISHED", "FELLOW", "DIRECTOR", "L8"]):
            level = JobLevel.L8
        elif any(w in clean_title for w in ["SR. STAFF", "SENIOR STAFF", "STAFF ARCHITECT", "PRINCIPAL ARCHITECT", "L7"]):
            level = JobLevel.L7
        elif any(w in clean_title for w in ["STAFF", "LEAD", "ARCHITECT", "L6"]):
            level = JobLevel.L6
        elif any(w in clean_title for w in ["SENIOR", "SR.", "SR ", "III", "L5"]):
            level = JobLevel.L5
        elif any(w in clean_title for w in ["MID", "II", "INTERMEDIATE", "L4"]):
            level = JobLevel.L4
        elif any(w in clean_title for w in ["JUNIOR", "JR.", "JR ", "ASSOCIATE", "ENTRY", "I", "L3"]):
            level = JobLevel.L3

        # Match specific level regex e.g. "SWE L6" or "Software Engineer 4"
        lvl_match = re.search(r"\bL([3-8])\b", clean_title)
        if lvl_match:
            level = JobLevel(f"L{lvl_match.group(1)}")

        radford = cls.RADFORD_LEVEL_MAP.get(level, RadfordLevel.P3)
        soc = soc_code or cls.SOC_MAPPINGS.get(family, "15-1252.00")

        return NormalizedRole(
            job_family=family,
            job_level=level,
            radford_level=radford,
            soc_code=soc,
        )
