from __future__ import annotations

from core.interfaces.observability import Observer
from core.observability.progress_tracker import progress_tracker


class CliProgressObserver(Observer):
    def on_node_start(self, *, job_id: str, node_id: str, node_name: str) -> None:
        self._print("start", job_id=job_id, node_id=node_id, node_name=node_name)

    def on_node_complete(self, *, job_id: str, node_id: str, node_name: str) -> None:
        self._print("done", job_id=job_id, node_id=node_id, node_name=node_name)

    def on_node_failed(self, *, job_id: str, node_id: str, node_name: str, error: str) -> None:
        self._print("failed", job_id=job_id, node_id=node_id, node_name=node_name, error=error)

    def _print(
        self,
        status: str,
        *,
        job_id: str,
        node_id: str,
        node_name: str,
        error: str | None = None,
    ) -> None:
        progress = progress_tracker.get_progress(job_id)
        elapsed = float(progress.get("elapsed_seconds", 0.0))
        percent = float(progress.get("percent", 0.0))
        done = float(progress.get("completed_steps", 0.0))
        total = float(progress.get("total_steps", 0.0))
        message = (
            f"[progress] {status} node={node_id} ({node_name}) "
            f"percent={percent:.1f}% steps={done:.1f}/{total:.1f} elapsed={elapsed:.1f}s"
        )
        if error:
            message += f" error={error}"
        print(message, flush=True)
