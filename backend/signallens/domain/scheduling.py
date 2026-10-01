"""Adaptive check intervals.

Pages that never change are checked less often (up to 4× their base interval, max a
week); a change resets them to base. Failures back off exponentially. News queries are
streams and always run at their base interval.
"""

from __future__ import annotations

MAX_INTERVAL_MIN = 7 * 24 * 60
MAX_BACKOFF_MIN = 48 * 60


def next_interval_minutes(*, kind: str, base: int, current: int, outcome: str, failures: int) -> int:
    base = max(5, base)
    if kind != "page":
        return base
    if outcome in ("changed", "baseline"):
        return base
    if outcome in ("unchanged", "not_modified"):
        return min(int(max(current, base) * 1.5), base * 4, MAX_INTERVAL_MIN)
    # degenerate / blocked / error
    return min(base * 2 ** min(failures, 5), MAX_BACKOFF_MIN)
