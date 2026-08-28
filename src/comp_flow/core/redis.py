"""Redis Cache Client and Atomic Counter Manager with In-Memory Fallback."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import redis.asyncio as aioredis

from comp_flow.core.config import settings

logger = logging.getLogger(__name__)


class RedisManager:
    """Manages Redis connection lifecycle, caching, and atomic counters."""

    def __init__(self, redis_url: str = settings.REDIS_URL) -> None:
        self.redis_url = redis_url
        self._client: aioredis.Redis | None = None
        self._in_memory_fallback: dict[str, str] = {}
        self._fallback_mode: bool = False

    async def get_client(self) -> aioredis.Redis | None:
        """Returns active redis client or sets fallback mode if unreachable."""
        if self._client is None and not self._fallback_mode:
            try:
                self._client = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0,
                )
                await self._client.ping()
            except Exception as exc:
                logger.warning(f"Redis unreachable ({exc}), falling back to in-memory cache.")
                self._fallback_mode = True
                self._client = None
        return self._client

    async def close(self) -> None:
        """Closes Redis client connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, key: str) -> str | None:
        """Gets string value for a key."""
        client = await self.get_client()
        if client is not None:
            try:
                val = await client.get(key)
                return str(val) if val is not None else None
            except Exception as exc:
                logger.warning(f"Redis get error: {exc}")
        return self._in_memory_fallback.get(key)

    async def set(self, key: str, value: str, expire_seconds: int | None = None) -> None:
        """Sets string value with optional expiration."""
        client = await self.get_client()
        if client is not None:
            try:
                if expire_seconds:
                    await client.setex(key, expire_seconds, value)
                else:
                    await client.set(key, value)
                return
            except Exception as exc:
                logger.warning(f"Redis set error: {exc}")
        self._in_memory_fallback[key] = value

    async def delete(self, *keys: str) -> None:
        """Deletes one or more keys."""
        client = await self.get_client()
        if client is not None:
            try:
                await client.delete(*keys)
            except Exception as exc:
                logger.warning(f"Redis delete error: {exc}")
        for k in keys:
            self._in_memory_fallback.pop(k, None)

    async def incrbyfloat(self, key: str, amount: float) -> float:
        """Atomically increments a float value in cache."""
        client = await self.get_client()
        if client is not None:
            try:
                res = await client.incrbyfloat(key, amount)
                return float(res)
            except Exception as exc:
                logger.warning(f"Redis incrbyfloat error: {exc}")
        curr = float(self._in_memory_fallback.get(key, 0.0))
        new_val = curr + amount
        self._in_memory_fallback[key] = str(new_val)
        return new_val

    # --- Domain-Specific Helpers ---

    @staticmethod
    def band_cache_key(job_level: str, job_family: str, location_tier: str) -> str:
        """Generates key for salary band caching."""
        return f"compflow:band:{job_level}:{job_family}:{location_tier}"

    async def get_cached_band(
        self, job_level: str, job_family: str, location_tier: str
    ) -> dict[str, Any] | None:
        """Retrieves cached salary band data."""
        key = self.band_cache_key(job_level, job_family, location_tier)
        val = await self.get(key)
        if val:
            try:
                return json.loads(val)  # type: ignore[no-any-return]
            except Exception:
                return None
        return None

    async def cache_band(
        self, job_level: str, job_family: str, location_tier: str, band_data: dict[str, Any]
    ) -> None:
        """Caches salary band data."""
        key = self.band_cache_key(job_level, job_family, location_tier)
        await self.set(
            key, json.dumps(band_data), expire_seconds=settings.REDIS_BAND_CACHE_TTL_SECONDS
        )

    @staticmethod
    def budget_depletion_key(cycle_id: uuid.UUID, department_id: uuid.UUID) -> str:
        """Key for tracking real-time budget depletion."""
        return f"compflow:budget:depleted:{cycle_id}:{department_id}"


redis_client = RedisManager()


def get_redis() -> RedisManager:
    """Dependency provider for RedisManager."""
    return redis_client


__all__ = ["RedisManager", "redis_client", "get_redis"]
