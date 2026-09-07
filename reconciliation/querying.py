"""Framework-independent keyset pagination contracts for review projections."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Generic, TypeVar
from uuid import UUID


DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
_CURSOR_VERSION = 1


class ReviewQueryUnavailable(LookupError):
    """A requested review resource is unavailable in the authorized scope."""


class ReviewCursorError(ValueError):
    """A pagination cursor is malformed or belongs to another projection."""


class ReviewPageSizeError(ValueError):
    """A requested page size is outside the documented bounded range."""


ItemT = TypeVar("ItemT")


@dataclass(frozen=True, slots=True)
class ReviewPage(Generic[ItemT]):
    items: tuple[ItemT, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class ReviewCursor:
    created_at: datetime
    public_id: UUID


def bounded_page_size(page_size: int = DEFAULT_PAGE_SIZE) -> int:
    if isinstance(page_size, bool) or not isinstance(page_size, int):
        raise ReviewPageSizeError("page_size must be an integer")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise ReviewPageSizeError(
            f"page_size must be between 1 and {MAX_PAGE_SIZE}"
        )
    return page_size


def encode_review_cursor(
    namespace: str,
    *,
    created_at: datetime,
    public_id: UUID,
) -> str:
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ReviewCursorError("cursor timestamps must be timezone-aware")
    payload = {
        "v": _CURSOR_VERSION,
        "n": namespace,
        "t": created_at.astimezone(UTC).isoformat(),
        "i": str(public_id),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def decode_review_cursor(namespace: str, value: str | None) -> ReviewCursor | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ReviewCursorError("cursor must be nonblank text")
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(raw.decode("ascii"))
        if not isinstance(payload, dict) or set(payload) != {"v", "n", "t", "i"}:
            raise ValueError
        if payload["v"] != _CURSOR_VERSION or payload["n"] != namespace:
            raise ValueError
        created_at = datetime.fromisoformat(payload["t"])
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError
        public_id = UUID(payload["i"])
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise ReviewCursorError("cursor is invalid for this projection") from error
    return ReviewCursor(created_at.astimezone(UTC), public_id)
