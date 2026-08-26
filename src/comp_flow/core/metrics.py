"""Prometheus Metrics Instrumentation for CompFlow Microservice."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

AUDIT_REQUESTS_TOTAL = Counter(
    "compflow_audit_requests_total",
    "Total number of deterministic agent audits executed",
    labelnames=["workflow_type", "decision"],
)

AUDIT_DURATION_SECONDS = Histogram(
    "compflow_audit_duration_seconds",
    "Duration of agent audits in seconds",
    labelnames=["workflow_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

OFFERS_TOTAL = Counter(
    "compflow_candidate_offers_total",
    "Total candidate offers created or status transitioned",
    labelnames=["status"],
)

PROPOSALS_TOTAL = Counter(
    "compflow_employee_proposals_total",
    "Total employee review proposals created or transitioned",
    labelnames=["status"],
)

BUDGET_DEPLETION_RATIO = Gauge(
    "compflow_budget_depletion_ratio",
    "Real-time budget pool depletion ratio (0.00 - 1.00+)",
    labelnames=["cycle_id", "department_id", "budget_type"],
)
