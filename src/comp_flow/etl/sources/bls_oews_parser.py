"""Parser for US Bureau of Labor Statistics (BLS) OEWS Survey Percentile Data."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

from comp_flow.domain.benchmarks import BenchmarkPercentiles


class BLSOEWSParser:
    """Parses BLS OEWS percentile exports and API payload tables."""

    @classmethod
    def parse_oews_csv(cls, csv_content: str | io.StringIO) -> dict[str, BenchmarkPercentiles]:
        """Parses standard BLS OEWS CSV files containing A_PCT10, A_PCT25, A_MEDIAN, A_PCT75, A_PCT90."""
        if isinstance(csv_content, str):
            stream = io.StringIO(csv_content)
        else:
            stream = csv_content

        reader = csv.DictReader(stream)
        results: dict[str, BenchmarkPercentiles] = {}

        for row in reader:
            soc = row.get("OCC_CODE", "").strip()
            area = row.get("AREA_TITLE", "NATIONAL").strip()
            key = f"{soc}_{area}"

            p10 = cls._parse_clean_decimal(row.get("A_PCT10"))
            p25 = cls._parse_clean_decimal(row.get("A_PCT25"))
            p50 = cls._parse_clean_decimal(row.get("A_MEDIAN"))
            p75 = cls._parse_clean_decimal(row.get("A_PCT75"))
            p90 = cls._parse_clean_decimal(row.get("A_PCT90"))
            emp_total = cls._parse_clean_int(row.get("TOT_EMP"))

            if p50 and p50 > Decimal("0"):
                results[key] = BenchmarkPercentiles(
                    p10_base=p10 or (p50 * Decimal("0.75")).quantize(Decimal("0.01")),
                    p25_base=p25 or (p50 * Decimal("0.85")).quantize(Decimal("0.01")),
                    p50_base=p50,
                    p75_base=p75 or (p50 * Decimal("1.18")).quantize(Decimal("0.01")),
                    p90_base=p90 or (p50 * Decimal("1.35")).quantize(Decimal("0.01")),
                    sample_size=emp_total or 100,
                )

        return results

    @classmethod
    def _parse_clean_decimal(cls, val: str | None) -> Decimal | None:
        if not val or val.strip() in ("*", "**", "#", "-"):
            return None
        clean_str = val.replace("$", "").replace(",", "").strip()
        try:
            return Decimal(clean_str).quantize(Decimal("0.01"))
        except Exception:
            return None

    @classmethod
    def _parse_clean_int(cls, val: str | None) -> int | None:
        if not val or val.strip() in ("*", "**", "#", "-"):
            return None
        clean_str = val.replace(",", "").strip()
        try:
            return int(clean_str)
        except Exception:
            return None
