"""Command Line Interface for CompFlow Platform."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import uvicorn

from comp_flow.cli.seeder import seed_enterprise_data
from comp_flow.core.config import settings
from comp_flow.core.database import AsyncSessionLocal, init_db
from comp_flow.etl.pipeline import BenchmarkETLPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("comp-flow-cli")


def serve_command(args: argparse.Namespace) -> None:
    """Runs the FastAPI server with Uvicorn."""
    host = args.host or settings.HOST
    port = args.port or settings.PORT
    reload = args.reload or settings.DEBUG

    logger.info(
        f"Starting {settings.APP_NAME} v{settings.APP_VERSION} on {host}:{port} (reload={reload})..."
    )
    uvicorn.run("comp_flow.api.app:app", host=host, port=port, reload=reload)


def seed_command(_args: argparse.Namespace) -> None:
    """Seeds database with enterprise demo dataset."""
    logger.info("Seeding enterprise demo data...")
    asyncio.run(seed_enterprise_data())
    logger.info("✅ Database seeding complete.")


def benchmark_seed_command(_args: argparse.Namespace) -> None:
    """Seeds database with 2026 market benchmarks."""

    async def _run() -> None:
        async with AsyncSessionLocal() as session:
            pipeline = BenchmarkETLPipeline(session)
            benchmarks = await pipeline.seed_market_benchmarks()
            logger.info(
                f"✅ Seeded {len(benchmarks)} market benchmarks across all families and levels."
            )

    asyncio.run(_run())


def benchmark_ingest_command(args: argparse.Namespace) -> None:
    """Ingests raw DOL LCA CSV dataset."""

    async def _run() -> None:
        with open(args.file, encoding="utf-8") as f:
            csv_text = f.read()
        async with AsyncSessionLocal() as session:
            pipeline = BenchmarkETLPipeline(session)
            benchmarks = await pipeline.ingest_dol_lca_csv(csv_text)
            logger.info(f"✅ Ingested and computed {len(benchmarks)} benchmarks from {args.file}.")

    asyncio.run(_run())


def ingest_live_dol_command(args: argparse.Namespace) -> None:
    """Streams and ingests public US DOL OFLC disclosure data with Tukey IQR cleansing."""

    async def _run() -> None:
        async with AsyncSessionLocal() as session:
            pipeline = BenchmarkETLPipeline(session)
            logger.info(
                f"Starting live DOL OFLC ingestion (url={args.url or 'bundled'}, limit={args.limit}, dry_run={args.dry_run})..."
            )
            benchmarks, report = await pipeline.ingest_live_dol_dataset(
                source_url=args.url,
                fiscal_year=args.year,
                max_records=args.limit,
                annual_aging_rate=args.aging_rate,
                dry_run=args.dry_run,
            )
            logger.info("==================================================")
            logger.info(f"✅ Live DOL ETL Ingestion Complete: {report.job_id}")
            logger.info(f"   Status:            {report.status}")
            logger.info(f"   Source:            {report.source_url}")
            logger.info(f"   Records Streamed:  {report.records_streamed:,}")
            logger.info(f"   Valid Tech Rows:   {report.valid_observations:,}")
            logger.info(f"   IQR Outliers Cut:  {report.outliers_pruned_iqr:,}")
            logger.info(f"   Cohorts Created:   {report.cohorts_aggregated}")
            logger.info(f"   Benchmarks Stored: {report.benchmarks_upserted}")
            logger.info(f"   Safe Harbor Skips: {report.antitrust_safe_harbor_discarded}")
            logger.info(f"   Execution Time:    {report.execution_time_seconds:.3f}s")
            logger.info("==================================================")

    asyncio.run(_run())


def init_db_command(_args: argparse.Namespace) -> None:
    """Initializes database tables."""
    logger.info(f"Initializing database schema at {settings.DATABASE_URL}...")
    asyncio.run(init_db())
    logger.info("✅ Database schema initialized successfully.")


def build_parser() -> argparse.ArgumentParser:
    """Builds CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="comp-flow",
        description="CompFlow Platform: Distributed Total Rewards & Offer Orchestration Microservice",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # serve
    serve_p = subparsers.add_parser("serve", help="Run the FastAPI microservice server")
    serve_p.add_argument("--host", type=str, default=settings.HOST, help="Bind host")
    serve_p.add_argument("--port", type=int, default=settings.PORT, help="Bind port")
    serve_p.add_argument("--reload", action="store_true", help="Enable live auto-reload")

    # seed
    subparsers.add_parser(
        "seed", help="Seed database with realistic enterprise total rewards fixtures"
    )

    # benchmark-seed
    subparsers.add_parser(
        "benchmark-seed", help="Seed database with 2026 market compensation benchmark percentiles"
    )

    # benchmark-ingest
    bench_ingest_p = subparsers.add_parser(
        "benchmark-ingest", help="Ingest raw DOL LCA / BLS wage disclosure CSV"
    )
    bench_ingest_p.add_argument("--file", type=str, required=True, help="Path to CSV file")

    # ingest-live-dol
    live_dol_p = subparsers.add_parser(
        "ingest-live-dol", help="Stream and ingest public US DOL OFLC H-1B disclosure dataset"
    )
    live_dol_p.add_argument(
        "--url", type=str, default=None, help="Remote URL or mirror to stream from"
    )
    live_dol_p.add_argument(
        "--limit", type=int, default=None, help="Maximum number of records to ingest"
    )
    live_dol_p.add_argument(
        "--year", type=int, default=2026, help="Target fiscal year for benchmark aging"
    )
    live_dol_p.add_argument(
        "--aging-rate", type=float, default=0.040, help="Annual wage movement rate (e.g. 0.04)"
    )
    live_dol_p.add_argument(
        "--dry-run", action="store_true", help="Execute calculations without writing to database"
    )

    # init-db
    subparsers.add_parser("init-db", help="Create database schema tables")

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve":
        serve_command(args)
    elif args.command == "seed":
        seed_command(args)
    elif args.command == "benchmark-seed":
        benchmark_seed_command(args)
    elif args.command == "benchmark-ingest":
        benchmark_ingest_command(args)
    elif args.command == "ingest-live-dol":
        ingest_live_dol_command(args)
    elif args.command == "init-db":
        init_db_command(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
