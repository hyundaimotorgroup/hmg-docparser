from __future__ import annotations

from collections.abc import Mapping
import time


def remaining_timeout_seconds(
    runtime_config: Mapping[str, object] | None,
    *,
    reserve_seconds: float = 0.0,
    minimum_seconds: float = 1.0,
) -> float | None:
    if not runtime_config:
        return None
    deadline = _float_value(runtime_config.get("mlapi_deadline_monotonic"))
    if deadline is None:
        return None

    remaining = deadline - time.monotonic() - max(reserve_seconds, 0.0)
    if remaining <= 0:
        return max(minimum_seconds, 0.0)
    return max(remaining, minimum_seconds)


def remaining_timeout_microseconds(
    runtime_config: Mapping[str, object] | None,
    *,
    reserve_seconds: float = 0.0,
    minimum_seconds: float = 1.0,
) -> int | None:
    remaining = remaining_timeout_seconds(
        runtime_config,
        reserve_seconds=reserve_seconds,
        minimum_seconds=minimum_seconds,
    )
    if remaining is None:
        return None
    return max(int(remaining * 1_000_000), 1)


def _float_value(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
