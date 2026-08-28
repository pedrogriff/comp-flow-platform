"""Parser for US Department of Labor (DOL) OFLC Disclosure Files (LCA / H-1B / PERM)."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal

from comp_flow.domain.benchmarks import RawWageObservation
from comp_flow.etl.normalizer import BenchmarkNormalizer


class DOLLCAParser:
    """Extracts certified compensation observations from DOL OFLC performance datasets."""

    # Field aliases to handle multi-year OFLC record layout variations
    CASE_NO_FIELDS = ["CASE_NUMBER", "CASE_NO", "LCA_CASE_NUMBER"]
    EMPLOYER_FIELDS = ["EMPLOYER_NAME", "LCA_CASE_EMPLOYER_NAME", "EMPLOYER"]
    TITLE_FIELDS = ["JOB_TITLE", "LCA_CASE_JOB_TITLE", "TITLE"]
    SOC_FIELDS = ["SOC_CODE", "SOC_NAME", "LCA_CASE_SOC_CODE"]
    WAGE_FIELDS = ["WAGE_RATE_OF_PAY_FROM", "PREVAILING_WAGE", "WAGE_RATE_1"]
    UNIT_FIELDS = ["WAGE_UNIT_OF_PAY", "PW_UNIT_OF_PAY", "WAGE_UNIT_1"]
    CITY_FIELDS = ["WORKSITE_CITY", "LCA_CASE_WORKLOC1_CITY", "EMPLOYER_CITY"]
    STATE_FIELDS = ["WORKSITE_STATE", "LCA_CASE_WORKLOC1_STATE", "EMPLOYER_STATE"]
    DATE_FIELDS = ["DECISION_DATE", "CASE_SUBMITTED", "RECEIVED_DATE", "BEGIN_DATE"]

    @classmethod
    def parse_csv_stream(cls, csv_content: str | io.StringIO) -> list[RawWageObservation]:
        """Parses a CSV string or stream into standardized RawWageObservation instances."""
        if isinstance(csv_content, str):
            stream = io.StringIO(csv_content)
        else:
            stream = csv_content

        reader = csv.DictReader(stream)
        observations: list[RawWageObservation] = []

        for row in reader:
            obs = cls._parse_single_row(row)
            if obs:
                observations.append(obs)

        return observations

    @classmethod
    def _parse_single_row(cls, row: dict[str, str]) -> RawWageObservation | None:
        """Extracts and normalizes a single row from a DOL OFLC CSV record."""
        # Find matching keys
        case_id = cls._get_first_val(row, cls.CASE_NO_FIELDS) or "UNKNOWN_CASE"
        employer = cls._get_first_val(row, cls.EMPLOYER_FIELDS) or "ANONYMOUS_EMPLOYER"
        title = cls._get_first_val(row, cls.TITLE_FIELDS)
        soc_code = cls._get_first_val(row, cls.SOC_FIELDS) or "15-1252.00"
        raw_wage = cls._get_first_val(row, cls.WAGE_FIELDS)
        unit = cls._get_first_val(row, cls.UNIT_FIELDS) or "YEAR"
        city = cls._get_first_val(row, cls.CITY_FIELDS)
        state = cls._get_first_val(row, cls.STATE_FIELDS)
        raw_date = cls._get_first_val(row, cls.DATE_FIELDS)

        if not title or not raw_wage:
            return None

        # Clean wage string (remove commas, dollar signs)
        clean_wage_str = raw_wage.replace("$", "").replace(",", "").strip()
        try:
            raw_wage_val = Decimal(clean_wage_str)
            if raw_wage_val <= Decimal("0"):
                return None
        except Exception:
            return None

        annualized_wage = BenchmarkNormalizer.normalize_wage(raw_wage_val, unit)

        # Parse date
        eff_date = date.today()
        if raw_date:
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    eff_date = datetime.strptime(raw_date.strip(), fmt).date()
                    break
                except ValueError:
                    continue

        return RawWageObservation(
            source_id=case_id,
            employer_name=employer.strip(),
            job_title=title.strip(),
            soc_code=soc_code.strip(),
            wage_rate=annualized_wage,
            wage_unit="YEAR",
            city=city.strip() if city else None,
            state=state.strip() if state else None,
            effective_date=eff_date,
        )

    @classmethod
    def _get_first_val(cls, row: dict[str, str], candidate_keys: list[str]) -> str | None:
        """Returns the first non-empty value matching any candidate key."""
        for key in candidate_keys:
            if key in row and row[key] and row[key].strip():
                return row[key].strip()
            # Also check case-insensitive match
            for r_key, r_val in row.items():
                if r_key.upper().strip() == key and r_val and r_val.strip():
                    return r_val.strip()
        return None
