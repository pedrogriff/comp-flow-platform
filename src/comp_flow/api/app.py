"""FastAPI Application Factory for CompFlow Platform."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from comp_flow.api.v1 import api_v1_router
from comp_flow.core.config import settings
from comp_flow.core.database import AsyncSessionLocal, init_db
from comp_flow.core.redis import redis_client


@asynccontextmanager
async def lifespan(_app: FastAPI) -> Any:
    """Application lifespan manager initializing storage and closing clients."""
    # Ensure database schema is initialized on startup if in dev/sqlite
    if "sqlite" in settings.DATABASE_URL:
        await init_db()
    yield
    await redis_client.close()


def create_app() -> FastAPI:
    """Constructs and configures the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Distributed Total Rewards Calibration & Offer Orchestration Microservice",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # System Probes & Observability
    @app.get("/healthz", status_code=status.HTTP_200_OK, tags=["System"])
    async def health_check() -> dict[str, str]:
        """Liveness probe."""
        return {
            "status": "HEALTHY",
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }

    @app.get("/readyz", status_code=status.HTTP_200_OK, tags=["System"])
    async def readiness_check() -> dict[str, Any]:
        """Readiness probe verifying DB and Cache reachability."""
        db_healthy = False
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
                db_healthy = True
        except Exception:
            db_healthy = False

        redis_healthy = False
        try:
            client = await redis_client.get_client()
            redis_healthy = client is not None
        except Exception:
            redis_healthy = False

        overall = db_healthy
        return {
            "status": "READY" if overall else "DEGRADED",
            "database": "CONNECTED" if db_healthy else "DISCONNECTED",
            "redis": "CONNECTED" if redis_healthy else "FALLBACK_IN_MEMORY",
        }

    @app.get("/metrics", tags=["System"])
    async def metrics_exporter() -> Response:
        """Prometheus metrics scrape endpoint."""
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # Mount API v1
    app.include_router(api_v1_router)

    return app


app = create_app()
