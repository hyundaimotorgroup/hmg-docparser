"""A shared absolute budget for all restoration workers and retries on one page."""
from __future__ import annotations
import math
import time

from core.engine.runtime.cancellation import PipelineCancelled


class BlockContextDeadlineExceeded(RuntimeError):
    pass


class BlockContextBudget:
    def __init__(self, timeout_seconds=None, cancellation_check=None, deadline_monotonic=None):
        self.cancellation_check = cancellation_check
        self.deadline_monotonic = deadline_monotonic
        if timeout_seconds is not None:
            if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
                raise BlockContextDeadlineExceeded('block context deadline exceeded')
            deadline = time.monotonic() + timeout_seconds
            self.deadline_monotonic = min(deadline, deadline_monotonic) if deadline_monotonic is not None else deadline

    def checkpoint(self):
        if self.cancellation_check and self.cancellation_check():
            raise PipelineCancelled('block context cancelled')
        if self.deadline_monotonic is not None and time.monotonic() >= self.deadline_monotonic:
            raise BlockContextDeadlineExceeded('block context deadline exceeded')

    def remaining_seconds(self):
        self.checkpoint()
        return None if self.deadline_monotonic is None else self.deadline_monotonic - time.monotonic()
