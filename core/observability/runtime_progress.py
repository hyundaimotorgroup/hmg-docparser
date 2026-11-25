from __future__ import annotations

from collections.abc import MutableMapping
from collections.abc import Mapping

from core.interfaces.observability import Observer
from core.observability.progress_tracker import progress_tracker


class RuntimeNodeProgressObserver(Observer):
    def __init__(
        self,
        *,
        file_id: str,
        stage_prefix: str = "runtime",
        page_count: int = 0,
        node_weights: Mapping[str, float] | None = None,
        job_state: MutableMapping[str, MutableMapping[str, object]] | None = None,
    ) -> None:
        self._file_id = file_id
        self._stage_prefix = stage_prefix
        self._page_count = int(max(page_count, 0))
        self._node_weights = dict(node_weights or {})
        self._job_state = job_state

    def on_node_start(self, *, job_id: str, node_id: str, node_name: str) -> None:
        progress_tracker.ensure_job_file(job_id, self._file_id, page_count=self._page_count)
        stage_key = progress_tracker.register_stage(
            job_id=job_id,
            file_id=self._file_id,
            stage_name=self._stage_name(node_id),
            total=self._node_weight(node_id),
            meta={"node_name": node_name, "layer": "runtime"},
        )
        progress_tracker.start_stage(job_id, stage_key)
        self._update_job_state(job_id=job_id, current_step=node_id)

    def on_node_complete(self, *, job_id: str, node_id: str, node_name: str) -> None:
        progress_tracker.ensure_job_file(job_id, self._file_id, page_count=self._page_count)
        stage_key = progress_tracker.register_stage(
            job_id=job_id,
            file_id=self._file_id,
            stage_name=self._stage_name(node_id),
            total=self._node_weight(node_id),
            meta={"node_name": node_name, "layer": "runtime"},
        )
        progress_tracker.finish_stage(job_id, stage_key, fill_remaining=True)
        self._update_job_state(job_id=job_id, current_step=node_id)

    def on_node_page_complete(
        self,
        *,
        job_id: str,
        node_id: str,
        node_name: str,
        page_index: int,
        page_count: int,
    ) -> None:
        # One page finished a page-scoped node: fill that node-stage's per-page scope so
        # progress advances incrementally as pages stream through (not all-at-once).
        effective_pages = self._page_count if self._page_count > 0 else max(page_count, 1)
        progress_tracker.ensure_job_file(job_id, self._file_id, page_count=effective_pages)
        stage_key = progress_tracker.register_stage(
            job_id=job_id,
            file_id=self._file_id,
            stage_name=self._stage_name(node_id),
            total=self._node_weight(node_id),
            meta={"node_name": node_name, "layer": "runtime"},
        )
        per_page_share = self._node_weight(node_id) / max(effective_pages, 1)
        progress_tracker.finish_stage_scope(
            job_id,
            stage_key,
            scope_key=f"page:{page_index}",
            scope_total=per_page_share,
        )
        self._update_job_state(job_id=job_id, current_step=node_id)

    def on_node_failed(self, *, job_id: str, node_id: str, node_name: str, error: str) -> None:
        progress_tracker.ensure_job_file(job_id, self._file_id, page_count=self._page_count)
        stage_key = progress_tracker.register_stage(
            job_id=job_id,
            file_id=self._file_id,
            stage_name=self._stage_name(node_id),
            total=self._node_weight(node_id),
            meta={"node_name": node_name, "layer": "runtime"},
        )
        progress_tracker.fail_stage(job_id, stage_key, error=error)
        self._update_job_state(job_id=job_id, current_step=node_id, error=error)

    def _stage_name(self, node_id: str) -> str:
        return f"{self._stage_prefix}:{node_id}"

    def _node_weight(self, node_id: str) -> float:
        return float(max(self._node_weights.get(node_id, 1.0), 0.0)) or 1.0

    def _update_job_state(self, *, job_id: str, current_step: str, error: str | None = None) -> None:
        if self._job_state is None or job_id not in self._job_state:
            return
        self._job_state[job_id]["current_step"] = current_step
        self._job_state[job_id]["current_file"] = self._file_id
        if error:
            self._job_state[job_id]["error"] = error
