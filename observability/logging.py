"""Fixed-schema JSON formatting for operational events."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping

from django.utils.crypto import salted_hmac


EVENT_FIELDS = (
    "event",
    "correlation_id",
    "route",
    "method",
    "status",
    "duration_ms",
    "workspace_ref",
    "failure_category",
    "book_id",
    "scope_id",
    "run_id",
    "import_id",
    "job_id",
    "stage",
)

_WORKSPACE_REF_SALT = "reconciliation-workbench.workspace-log.v1"


def hash_workspace_ref(workspace_id: object) -> str:
    """The same salted, truncated reference used by request-side logging."""
    return salted_hmac(
        _WORKSPACE_REF_SALT, str(workspace_id), algorithm="sha256"
    ).hexdigest()[:16]


def safe_event(values: Mapping[str, object]) -> dict[str, object]:
    """Copy only reviewed scalar fields into a loggable event."""
    event: dict[str, object] = {}
    for field_name in EVENT_FIELDS:
        value = values.get(field_name)
        if value is None or isinstance(value, (str, int, float, bool)):
            event[field_name] = value
        else:
            event[field_name] = "[invalid]"
    return event


class PrivacySafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        values = getattr(record, "structured_event", {})
        if not isinstance(values, Mapping):
            values = {}
        return json.dumps(
            safe_event(values),
            separators=(",", ":"),
            sort_keys=True,
        )
