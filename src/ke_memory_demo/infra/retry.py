from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC
from email.utils import parsedate_to_datetime
import math
from typing import cast

import httpx
from openai import APITimeoutError


MAX_TRANSPORT_ATTEMPTS = 4
BACKOFF_SECONDS = (1.0, 2.0, 4.0)


def is_transient_transport_error(error: BaseException) -> bool:
    if isinstance(error, TimeoutError | httpx.TimeoutException | APITimeoutError):
        return True
    status_code = error_status_code(error)
    return status_code == 429 or (status_code is not None and 500 <= status_code <= 599)


def retry_delay_seconds(
    error: BaseException,
    retry_ordinal: int,
    *,
    clock: Callable[[], float],
) -> float:
    if retry_ordinal < 1 or retry_ordinal > len(BACKOFF_SECONDS):
        raise ValueError("retry ordinal must be 1, 2, or 3")

    retry_after = _retry_after(error, clock=clock)
    return retry_after if retry_after is not None else BACKOFF_SECONDS[retry_ordinal - 1]


def error_status_code(error: BaseException) -> int | None:
    status_code = getattr(error, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def _retry_after(error: BaseException, *, clock: Callable[[], float]) -> float | None:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if not isinstance(headers, Mapping):
        headers = getattr(error, "headers", None)
    if not isinstance(headers, Mapping):
        return None
    header_mapping = cast(Mapping[object, object], headers)

    raw_value = next(
        (
            str(value)
            for name, value in header_mapping.items()
            if str(name).lower() == "retry-after"
        ),
        None,
    )
    if raw_value is None:
        return None

    try:
        seconds = float(raw_value)
    except ValueError:
        seconds = None
    if seconds is not None:
        return seconds if math.isfinite(seconds) and seconds >= 0 else None

    try:
        retry_at = parsedate_to_datetime(raw_value)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    delay = retry_at.timestamp() - clock()
    return max(0.0, delay) if math.isfinite(delay) else None
