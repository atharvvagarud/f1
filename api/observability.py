"""Lightweight request/runtime observability (P10-3).

Stdlib logging plus one small middleware. Per completed request exactly one
single-line JSON record::

    {"event": "request_complete", "method": "GET", "path": "/v2/races",
     "status": 200, "duration_ms": 12.4}

``duration_ms`` is server-side REQUEST DURATION (monotonic timer), never
model inference latency unless the span isolates inference (it does not).
No query strings, bodies, headers, cookies, or secrets are logged. 4xx
completes at INFO; unexpected 5xx logs at ERROR (uvicorn still owns the
traceback — it is not duplicated here).
"""

from __future__ import annotations

import json
import logging
import sys
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

LOGGER_NAME = "f1.serving"


def configure_logging(level_name: str) -> logging.Logger:
    """Set the serving logger level; attach one stderr handler if none."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level_name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


def _route_path(request: Request) -> str:
    """Low-cardinality path: matched route template when known.

    Falls back to the exact path (which never carries a query string —
    ``request.url.path`` excludes it by construction).
    """
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return request.url.path


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """One structured record per completed request (no bodies, no query)."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000.0
            logging.getLogger(LOGGER_NAME).error(json.dumps({
                "event": "request_error",
                "method": request.method,
                "path": _route_path(request),
                "status": 500,
                "duration_ms": round(duration_ms, 1),
            }))
            raise
        duration_ms = (time.perf_counter() - start) * 1000.0
        record = {
            "event": "request_complete",
            "method": request.method,
            "path": _route_path(request),
            "status": response.status_code,
            "duration_ms": round(duration_ms, 1),
        }
        logger = logging.getLogger(LOGGER_NAME)
        if response.status_code >= 500:
            logger.error(json.dumps(record))
        else:
            logger.info(json.dumps(record))
        return response
