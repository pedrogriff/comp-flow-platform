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


def tse_triage_command(args: argparse.Namespace) -> None:
    """TSE Customer Incident Triage Cockpit & SOX Ledger Inspector."""
    import uuid

    from comp_flow.core.ledger import SoxLedgerService
    from comp_flow.service.tse_triage import TseIncidentTriageService

    async def _run() -> None:
        async with AsyncSessionLocal() as session:
            if (
                args.verify_ledger
                and not args.review_id
                and not args.offer_id
                and not args.trace_id
            ):
                res = await SoxLedgerService.verify_chain(session)
                if args.json:
                    print(res.model_dump_json(indent=2))
                    return
                print("\n" + "=" * 60)
                print(" 🛡️  SOX SECTION 404 AUDIT LEDGER INTEGRITY REPORT")
                print("=" * 60)
                status_color = "\033[92m" if res.is_valid else "\033[91m"
                reset = "\033[0m"
                print(f" Status:          {status_color}{res.status}{reset}")
                print(f" Total Blocks:    {res.total_entries}")
                print(f" Genesis Hash:    {res.genesis_hash or 'N/A'}")
                print(f" Head Hash:       {res.head_hash or 'N/A'}")
                if not res.is_valid:
                    print(f" Tampered Block:  Sequence #{res.tampered_sequence_id}")
                    print(f" Error Reason:    {res.error_reason}")
                print("=" * 60 + "\n")
                return

            review_uuid = uuid.UUID(args.review_id) if args.review_id else None
            offer_uuid = uuid.UUID(args.offer_id) if args.offer_id else None

            report = await TseIncidentTriageService.diagnose(
                db=session,
                trace_id=args.trace_id,
                review_id=review_uuid,
                offer_id=offer_uuid,
            )

            if args.json:
                print(report.model_dump_json(indent=2))
                return

            cyan = "\033[96m"
            green = "\033[92m"
            yellow = "\033[93m"
            red = "\033[91m"
            bold = "\033[1m"
            reset = "\033[0m"

            print("\n" + f"{bold}{cyan}" + "=" * 70)
            print(" 🔍 TSE INCIDENT TRIAGE COCKPIT — ROOT CAUSE DOSSIER")
            print("=" * 70 + f"{reset}")
            print(f" Incident ID:     {report.incident_id}")
            print(f" Timestamp:       {report.timestamp.isoformat()}")
            print(f" Trace Context:   {report.trace_id or 'No active W3C span'}")
            print(f" Entity:          {report.entity_type} ({report.entity_id or 'N/A'})")
            print(
                f" Target Profile:  {bold}{report.target_name or 'N/A'}{reset} | Status: {yellow}{report.current_status}{reset}"
            )

            if report.job_level:
                print(
                    f" Classification:  Level {report.job_level} | Family: {report.job_family} | Geo: {report.location_tier}"
                )
            if report.proposed_base is not None:
                curr = f"${report.current_base:,.2f}" if report.current_base else "N/A"
                print(
                    f" Compensation:    Current: {curr} -> Proposed: {bold}${report.proposed_base:,.2f}{reset}"
                )
            if report.compa_ratio is not None:
                mid = f"${report.salary_band_mid:,.2f}" if report.salary_band_mid else "N/A"
                from decimal import Decimal

                compa_color = (
                    green if Decimal("0.80") <= report.compa_ratio <= Decimal("1.20") else red
                )
                print(
                    f" Band Alignment:  Compa-Ratio: {compa_color}{report.compa_ratio:.3f}{reset} (Band Mid: {mid})"
                )

            ledger_color = green if report.ledger_integrity.is_valid else red
            print("-" * 70)
            print(
                f" Cryptographic SOX Ledger: {ledger_color}[{report.ledger_integrity.status}]{reset} "
                f"({report.ledger_integrity.total_entries} blocks verified)"
            )

            if report.policy_findings:
                print("-" * 70)
                print(f"{bold} Policy Compliance Audit Findings:{reset}")
                for f in report.policy_findings:
                    f_color = green if f.passed else red
                    icon = "✅" if f.passed else "❌"
                    print(
                        f"   {icon} {bold}{f.rule_name}{reset}: {f_color}[{f.severity}]{reset} - {f.details}"
                    )

            print("-" * 70)
            rc_color = green if "HEALTHY" in report.root_cause_category else red
            print(
                f"{bold} Root Cause Classification:{reset} {rc_color}{report.root_cause_category}{reset}"
            )
            print(f"   {bold}Customer Impact:{reset} {report.customer_summary}")
            print(f"   {bold}Technical Diagnosis:{reset} {report.technical_analysis}")

            print("-" * 70)
            print(f"{bold} Actionable TSE Remediation Plan:{reset}")
            for i, act in enumerate(report.recommended_actions, 1):
                print(f"   {bold}{i}.{reset} {act}")

            print("=" * 70)
            print(f" Execution Time: {report.execution_time_ms:.2f}ms\n")

    asyncio.run(_run())


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

    # tse-triage
    tse_p = subparsers.add_parser(
        "tse-triage", help="TSE Incident Triage Cockpit & SOX Cryptographic Ledger Inspector"
    )
    tse_p.add_argument(
        "--trace-id", type=str, default=None, help="Correlate by W3C distributed trace ID"
    )
    tse_p.add_argument(
        "--review-id", type=str, default=None, help="Triage an employee review proposal UUID"
    )
    tse_p.add_argument(
        "--offer-id", type=str, default=None, help="Triage a candidate offer proposal UUID"
    )
    tse_p.add_argument(
        "--verify-ledger",
        action="store_true",
        help="Execute complete cryptographic SOX ledger audit",
    )
    tse_p.add_argument("--json", action="store_true", help="Output raw JSON diagnostic report")

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
    elif args.command == "tse-triage":
        tse_triage_command(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
