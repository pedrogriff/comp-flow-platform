"""SRE-grade Prometheus Metrics Middleware for CompFlow API."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from comp_flow.core.metrics import (
    HTTP_ACTIVE_REQUESTS,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
)
from comp_flow.core.tracing import get_current_trace_id


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Observability middleware tracking request throughput, latency SLIs, and active in-flight calls.

    Normalizes route paths to prevent high-cardinality label explosion in Prometheus
    and excludes internal health probes (/healthz, /readyz, /metrics) from skewing SLO metrics.
    """

    EXCLUDED_PATHS = frozenset({"/healthz", "/readyz", "/metrics", "/favicon.ico"})

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if path in self.EXCLUDED_PATHS:
            return await call_next(request)

        method = request.method
        HTTP_ACTIVE_REQUESTS.inc()
        start_time = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            trace_id = get_current_trace_id()
            if trace_id:
                response.headers["X-Trace-ID"] = trace_id
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            duration = max(time.perf_counter() - start_time, 0.0)
            HTTP_ACTIVE_REQUESTS.dec()

            # Retrieve Starlette route pattern (e.g. /api/v1/offers/{offer_id}) to prevent high cardinality
            route = request.scope.get("route")
            handler = route.path if route is not None and hasattr(route, "path") else "unmatched"

            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                handler=handler,
            ).observe(duration)

            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                handler=handler,
                status_code=str(status_code),
            ).inc()
