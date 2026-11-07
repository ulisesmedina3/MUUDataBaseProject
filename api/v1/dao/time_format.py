from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def format_timestamp(value: Any) -> str:
    """Return a timestamp in RFC 3339 UTC format."""
    if not isinstance(value, datetime):
        raise TypeError("timestamp value must be a datetime")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")