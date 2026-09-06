"""Correlation and privacy-safe request logging middleware."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from time import perf_counter
from uuid import uuid4

from django.http import HttpRequest, HttpResponse
from django.utils.crypto import salted_hmac

from reconciliation.domain import WorkspaceAccess

from .logging import safe_event


CORRELATION_HEADER = "X-Correlation-ID"
CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
logger = logging.getLogger("reconciliation.requests")


def correlation_id(request: HttpRequest) -> str:
    candidate = request.headers.get(CORRELATION_HEADER, "")
    if CORRELATION_PATTERN.fullmatch(candidate):
        return candidate
    return uuid4().hex


def workspace_reference(request: HttpRequest) -> str | None:
    access = getattr(request, "workspace_access", None)
    if not isinstance(access, WorkspaceAccess):
        return None
    return salted_hmac(
        "reconciliation-workbench.workspace-log.v1",
        str(access.workspace_id),
        algorithm="sha256",
    ).hexdigest()[:16]


def failure_category(status: int) -> str | None:
    if status >= 500:
        return "server_error"
    if status >= 400:
        return "client_error"
    return None


class CorrelationLoggingMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.correlation_id = correlation_id(request)  # type: ignore[attr-defined]
        started = perf_counter()
        response = self.get_response(request)
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        response[CORRELATION_HEADER] = request.correlation_id  # type: ignore[attr-defined]
        match = getattr(request, "resolver_match", None)
        route = match.view_name if match and match.view_name else "unmatched"
        event = safe_event(
            {
                "event": "http_request_completed",
                "correlation_id": request.correlation_id,  # type: ignore[attr-defined]
                "route": route,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": elapsed_ms,
                "workspace_ref": workspace_reference(request),
                "failure_category": failure_category(response.status_code),
            }
        )
        logger.info("http_request_completed", extra={"structured_event": event})
        return response
