"""Salary Band Service with Redis Caching and Database Persistence."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.core.redis import redis_client
from comp_flow.domain.entities import SalaryBand
from comp_flow.domain.models import (
    JobFamily,
    JobLevel,
    LocationTier,
    SalaryBandBase,
    SalaryBandCreate,
)
from comp_flow.tools.registry import get_default_salary_band


class BandService:
    """Manages salary bands with Redis caching."""

    @classmethod
    async def get_band(
        cls,
        db: AsyncSession,
        job_level: JobLevel,
        job_family: JobFamily = JobFamily.SOFTWARE_ENGINEERING,
        location_tier: LocationTier = LocationTier.US_ZONE_1,
    ) -> SalaryBandBase:
        """Retrieves salary band with Redis cache check, falling back to DB or default benchmark."""
        # 1. Check Redis Cache
        cached = await redis_client.get_cached_band(
            job_level.value, job_family.value, location_tier.value
        )
        if cached:
            return SalaryBandBase(
                job_level=JobLevel(cached["job_level"]),
                job_family=JobFamily(cached["job_family"]),
                location_tier=LocationTier(cached["location_tier"]),
                min_base=Decimal(str(cached["min_base"])),
                mid_base=Decimal(str(cached["mid_base"])),
                max_base=Decimal(str(cached["max_base"])),
                target_equity_gsus=int(cached["target_equity_gsus"]),
                target_bonus_pct=Decimal(str(cached["target_bonus_pct"])),
            )

        # 2. Query PostgreSQL
        stmt = select(SalaryBand).where(
            SalaryBand.job_level == job_level,
            SalaryBand.job_family == job_family,
            SalaryBand.location_tier == location_tier,
        )
        res = await db.execute(stmt)
        band_record = res.scalar_one_or_none()

        if band_record:
            band_schema = SalaryBandBase(
                job_level=band_record.job_level,
                job_family=band_record.job_family,
                location_tier=band_record.location_tier,
                min_base=band_record.min_base,
                mid_base=band_record.mid_base,
                max_base=band_record.max_base,
                target_equity_gsus=band_record.target_equity_gsus,
                target_bonus_pct=band_record.target_bonus_pct,
            )
        else:
            # 3. Create default benchmark band and persist
            band_schema = get_default_salary_band(job_level, job_family, location_tier)
            new_band = SalaryBand(
                id=uuid.uuid4(),
                job_level=band_schema.job_level,
                job_family=band_schema.job_family,
                location_tier=band_schema.location_tier,
                min_base=band_schema.min_base,
                mid_base=band_schema.mid_base,
                max_base=band_schema.max_base,
                target_equity_gsus=band_schema.target_equity_gsus,
                target_bonus_pct=band_schema.target_bonus_pct,
            )
            db.add(new_band)
            await db.flush()

        # Cache in Redis
        cache_data: dict[str, Any] = {
            "job_level": band_schema.job_level.value,
            "job_family": band_schema.job_family.value,
            "location_tier": band_schema.location_tier.value,
            "min_base": str(band_schema.min_base),
            "mid_base": str(band_schema.mid_base),
            "max_base": str(band_schema.max_base),
            "target_equity_gsus": band_schema.target_equity_gsus,
            "target_bonus_pct": str(band_schema.target_bonus_pct),
        }
        await redis_client.cache_band(
            job_level.value, job_family.value, location_tier.value, cache_data
        )

        return band_schema

    @classmethod
    async def list_bands(cls, db: AsyncSession) -> list[SalaryBand]:
        """Lists all persisted salary bands."""
        stmt = select(SalaryBand).order_by(SalaryBand.job_level, SalaryBand.location_tier)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @classmethod
    async def upsert_band(cls, db: AsyncSession, band_in: SalaryBandCreate) -> SalaryBand:
        """Upserts a salary band in DB and refreshes Redis cache."""
        stmt = select(SalaryBand).where(
            SalaryBand.job_level == band_in.job_level,
            SalaryBand.job_family == band_in.job_family,
            SalaryBand.location_tier == band_in.location_tier,
        )
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.min_base = band_in.min_base
            existing.mid_base = band_in.mid_base
            existing.max_base = band_in.max_base
            existing.target_equity_gsus = band_in.target_equity_gsus
            existing.target_bonus_pct = band_in.target_bonus_pct
            record = existing
        else:
            record = SalaryBand(
                id=uuid.uuid4(),
                job_level=band_in.job_level,
                job_family=band_in.job_family,
                location_tier=band_in.location_tier,
                min_base=band_in.min_base,
                mid_base=band_in.mid_base,
                max_base=band_in.max_base,
                target_equity_gsus=band_in.target_equity_gsus,
                target_bonus_pct=band_in.target_bonus_pct,
            )
            db.add(record)

        await db.flush()

        # Refresh Redis
        cache_data: dict[str, Any] = {
            "job_level": band_in.job_level.value,
            "job_family": band_in.job_family.value,
            "location_tier": band_in.location_tier.value,
            "min_base": str(band_in.min_base),
            "mid_base": str(band_in.mid_base),
            "max_base": str(band_in.max_base),
            "target_equity_gsus": band_in.target_equity_gsus,
            "target_bonus_pct": str(band_in.target_bonus_pct),
        }
        await redis_client.cache_band(
            band_in.job_level.value,
            band_in.job_family.value,
            band_in.location_tier.value,
            cache_data,
        )

        return record
