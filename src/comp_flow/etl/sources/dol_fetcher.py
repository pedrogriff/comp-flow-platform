"""Streaming Downloader and Ingestion Fetcher for US Department of Labor OFLC Disclosures."""

from __future__ import annotations

import csv
import logging
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CURATED_DATASET_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "lca_tech_disclosures_2025_2026.csv"
)

# Known public DOL OFLC disclosure endpoints
DOL_OFLC_ANNUAL_DISCLOSURE_URL = (
    "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q4.csv"
)


class DOLLiveFetcher:
    """Streams certified wage disclosures with chunked streaming and local fallback."""

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def stream_lines(self, url: str | None = None) -> AsyncIterator[str]:
        """Streams lines of CSV data asynchronously chunk by chunk.

        If url is provided, attempts an HTTP chunked streaming download.
        If url is None or network request fails, falls back gracefully to the
        bundled authentic 2025-2026 tech disclosure dataset.
        """
        if url and url.lower() not in ("default", "local", "bundled"):
            try:
                logger.info(f"Connecting to live DOL OFLC data stream at {url}...")
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds, follow_redirects=True
                ) as client:
                    async with client.stream("GET", url) as response:
                        response.raise_for_status()
                        buffer = ""
                        async for chunk in response.aiter_text():
                            buffer += chunk
                            lines = buffer.splitlines(keepends=True)
                            buffer = lines.pop() if lines and not lines[-1].endswith("\n") else ""
                            for line in lines:
                                yield line
                        if buffer:
                            yield buffer
                return
            except Exception as exc:
                logger.warning(
                    f"Unable to stream directly from remote URL {url} ({exc}). "
                    f"Falling back to curated 2025-2026 certified LCA tech disclosure dataset."
                )

        # Fallback to local verified dataset
        for line in self.stream_lines_from_file(CURATED_DATASET_PATH):
            yield line

    @staticmethod
    def stream_lines_from_file(file_path: Path | str) -> Iterator[str]:
        """Streams lines from a local file with constant memory footprint."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"LCA disclosure dataset not found at {path}")
        with open(path, encoding="utf-8") as f:
            yield from f

    @classmethod
    def parse_rows_from_stream(
        cls, line_iterator: Iterator[str] | AsyncIterator[str]
    ) -> Iterator[dict[str, Any]]:
        """Wraps line iterator with csv.DictReader for streaming dictionary rows."""
        # For synchronous iteration
        if hasattr(line_iterator, "__next__"):
            reader = csv.DictReader(line_iterator)  # type: ignore[arg-type]
            yield from reader
