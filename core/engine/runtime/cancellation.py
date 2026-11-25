from __future__ import annotations


class PipelineCancelled(RuntimeError):
    """Raised when a running pipeline observes an external cancellation request."""

