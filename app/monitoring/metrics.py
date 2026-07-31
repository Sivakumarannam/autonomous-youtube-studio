"""Prometheus metrics (Phase 5, item 4).

Exposes a local /metrics endpoint via prometheus_client — no external
Prometheus server or push-gateway is required to run this app. Scraping
and visualization (Grafana, etc.) are the operator's own infrastructure.
"""
from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

PIPELINE_RUNS_TOTAL = Counter(
    "pipeline_runs_total",
    "Number of pipeline run status transitions, by resulting status.",
    ["status"],
)

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

SCHEDULER_TICKS_TOTAL = Counter(
    "scheduler_ticks_total",
    "Number of scheduler ticks executed.",
)

SCHEDULER_UPLOAD_RESULTS_TOTAL = Counter(
    "scheduler_upload_results_total",
    "Per-upload outcome of scheduler ticks.",
    ["result"],  # "succeeded" | "failed"
)

# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

UPLOAD_RETRIES_TOTAL = Counter(
    "upload_retries_total",
    "Number of upload retry attempts scheduled after a transient failure.",
)

# ---------------------------------------------------------------------------
# HTTP request latency (wired via middleware in app.main)
# ---------------------------------------------------------------------------

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path", "status_code"],
)


def render_latest() -> tuple[bytes, str]:
    """Return (body, content_type) for the /metrics endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST