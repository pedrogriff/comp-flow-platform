"""Benchmark: Agentic Compensation Audit Throughput.

Measures evaluation speed across thousands of compensation review proposals.
"""

from __future__ import annotations

import random
import time
from decimal import Decimal

from comp_flow.domain.models import JobLevel, PerformanceRating
from comp_flow.service.workflow_engine import CompensationWorkflowEngine, InMemProposal


def generate_synthetic_reviews(n: int) -> list[InMemProposal]:
    """Generates a batch of synthetic compensation proposals."""
    levels = list(JobLevel)
    ratings = list(PerformanceRating)
    proposals: list[InMemProposal] = []

    for i in range(n):
        lvl = random.choice(levels)
        rating = random.choice(ratings)
        curr_base = Decimal(random.randint(140_000, 450_000))
        increase = Decimal(random.randint(0, 40_000))
        proposed_base = curr_base + increase
        equity = random.randint(300, 3500)

        proposals.append(
            InMemProposal(
                review_id=f"REV-{i:06d}",
                employee_id=f"EMP-{i:06d}",
                job_level=lvl,
                current_base=curr_base,
                proposed_base=proposed_base,
                proposed_equity_rsus=equity,
                performance_rating=rating,
            )
        )
    return proposals


def run_benchmark() -> None:
    n = 5_000
    print("=" * 75)
    print(f"CompFlow: Agentic Audit Throughput Benchmark (N = {n:,d} Proposals)")
    print("=" * 75)

    proposals = generate_synthetic_reviews(n)
    engine = CompensationWorkflowEngine()

    for p in proposals:
        engine.register_draft(p)

    t0 = time.perf_counter()
    decisions: dict[str, int] = {}

    for p in proposals:
        audited = engine.submit_and_audit(p.review_id)
        dec = audited.status.value
        decisions[dec] = decisions.get(dec, 0) + 1

    elapsed = time.perf_counter() - t0
    throughput = n / elapsed if elapsed > 0 else 0

    print(f"Total Proposals Audited: {n:,d}")
    print(f"Total Execution Time:    {elapsed:.4f} seconds")
    print(f"Audit Throughput:        {throughput:,.1f} proposals / second")
    print("-" * 75)
    print("Agent Decision Breakdown:")
    for status, count in decisions.items():
        pct = (count / n) * 100
        print(f"  • {status:<25}: {count:,d} ({pct:.1f}%)")
    print("=" * 75)


if __name__ == "__main__":
    run_benchmark()
