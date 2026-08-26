"""Command Line Interface for CompFlow Platform."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import uvicorn

from comp_flow.cli.seeder import seed_enterprise_data
from comp_flow.core.config import settings
from comp_flow.core.database import init_db

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
    elif args.command == "init-db":
        init_db_command(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
