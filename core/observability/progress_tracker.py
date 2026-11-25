from __future__ import annotations

from core.observability.llm_usage_aggregation import UsageReducer
from copy import deepcopy
import threading
import time
from dataclasses import dataclass
from datetime import datetime


def get_current_time():
    return datetime.now().strftime("%y.%m.%d %H:%M:%S")


def make_stage_key(file_id: str, stage_name: str) -> str:
    return f"{file_id}:{stage_name}"


class _ProgressTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs = {}

    def _new_job_state(
        self, files: dict | None = None, *, status: str = "pending"
    ) -> dict:
        now = time.time()
        files = files or {}
        return {
            "status": status,
            "files": files,
            "stages": {},
            "llm_usage": self._new_llm_usage_state(),
            "_usage_reducer": UsageReducer(),
            "pdf_page_dict": self._build_pdf_pages(files),
            "started_at_epoch": now,
            "finished_at_epoch": None,
        }

    def _new_llm_usage_state(self) -> dict:
        return UsageReducer().summary()

    def _elapsed_seconds(self, job: dict) -> float:
        started_at = job.get("started_at_epoch")
        if not isinstance(started_at, (int, float)):
            return 0.0
        finished_at = job.get("finished_at_epoch")
        end_at = finished_at if isinstance(finished_at, (int, float)) else time.time()
        return round(max(end_at - started_at, 0.0), 2)

    def _calc_stage_done(self, stage: dict) -> float:
        if not stage["scopes"]:
            return 0.0
        stage_done = sum(scope["done"] for scope in stage["scopes"].values())
        return min(stage_done, stage["total"])

    def _build_pdf_pages(self, files: dict) -> dict:
        return {
            file_id: int((meta or {}).get("page_count", 0))
            for file_id, meta in (files or {}).items()
        }

    def init_job(self, job_id: str, files: dict[str, dict]) -> None:
        with self._lock:
            self._jobs[job_id] = self._new_job_state(files)

    def ensure_job_file(self, job_id: str, file_id: str, page_count: int = 0) -> None:
        with self._lock:
            if job_id not in self._jobs:
                self._jobs[job_id] = self._new_job_state()
            job = self._jobs[job_id]
            job["files"].setdefault(file_id, {"page_count": int(max(page_count, 0))})
            job["pdf_page_dict"].setdefault(file_id, int(max(page_count, 0)))

    def register_stage(
        self,
        job_id: str,
        file_id: str,
        stage_name: str,
        total: float,
        meta: dict | None = None,
    ) -> str:
        with self._lock:
            if job_id not in self._jobs:
                self._jobs[job_id] = self._new_job_state()
            job = self._jobs[job_id]
            stage_key = make_stage_key(file_id, stage_name)
            if stage_key not in job["stages"]:
                job["stages"][stage_key] = {
                    "file_id": file_id,
                    "name": stage_name,
                    "total": float(max(total, 0)),
                    "done": 0.0,
                    "status": "pending",
                    "started_at": None,
                    "finished_at": None,
                    "started_at_epoch": None,
                    "finished_at_epoch": None,
                    "meta": meta or {},
                    "scopes": {},
                    "error": None,
                }
            return stage_key

    def register_stages_from_plan(self, job_id: str, plan: list[dict]) -> None:
        for stage in plan:
            self.register_stage(
                job_id=job_id,
                file_id=stage["file_id"],
                stage_name=stage["stage_name"],
                total=stage["total"],
                meta=stage.get("meta", {}),
            )

    def start_stage(self, job_id: str, stage_key: str) -> None:
        with self._lock:
            stage = self._jobs.get(job_id, {}).get("stages", {}).get(stage_key)
            if not stage:
                return
            if stage["status"] == "pending":
                stage["status"] = "running"
                stage["started_at"] = get_current_time()
                stage["started_at_epoch"] = time.time()

    def update_stage(self, job_id: str, stage_key: str, delta: float = 1.0) -> None:
        with self._lock:
            stage = self._jobs.get(job_id, {}).get("stages", {}).get(stage_key)
            if not stage:
                return
            scope_key = "all"
            scope_total = stage["total"]
            scope = stage["scopes"].setdefault(
                scope_key, {"total": float(scope_total), "done": 0.0}
            )
            scope["total"] = float(scope_total)
            scope["done"] = min(scope["done"] + max(float(delta), 0.0), scope["total"])
            stage["done"] = self._calc_stage_done(stage)
            if stage["status"] == "pending":
                stage["status"] = "running"
                stage["started_at"] = get_current_time()
                stage["started_at_epoch"] = time.time()
            if stage["done"] >= stage["total"]:
                stage["status"] = "done"
                stage["finished_at"] = get_current_time()
                stage["finished_at_epoch"] = time.time()

    def update_stage_scope(
        self,
        job_id: str,
        stage_key: str,
        scope_key: str,
        scope_total: float,
        delta: float = 1.0,
    ) -> None:
        with self._lock:
            stage = self._jobs.get(job_id, {}).get("stages", {}).get(stage_key)
            if not stage:
                return
            scope_total = float(max(scope_total, 0))
            delta = max(float(delta), 0.0)
            scope = stage["scopes"].setdefault(
                scope_key, {"total": scope_total, "done": 0.0}
            )
            scope["total"] = scope_total
            scope["done"] = min(scope["done"] + delta, scope["total"])

            stage["done"] = self._calc_stage_done(stage)
            if stage["status"] == "pending":
                stage["status"] = "running"
                stage["started_at"] = get_current_time()
                stage["started_at_epoch"] = time.time()
            if stage["done"] >= stage["total"]:
                stage["status"] = "done"
                stage["finished_at"] = get_current_time()
                stage["finished_at_epoch"] = time.time()

    def finish_stage_scope(
        self,
        job_id: str,
        stage_key: str,
        scope_key: str,
        scope_total: float,
    ) -> None:
        with self._lock:
            stage = self._jobs.get(job_id, {}).get("stages", {}).get(stage_key)
            if not stage:
                return
            scope_total = float(max(scope_total, 0))
            scope = stage["scopes"].setdefault(
                scope_key, {"total": scope_total, "done": 0.0}
            )
            scope["total"] = scope_total
            scope["done"] = scope_total

            stage["done"] = self._calc_stage_done(stage)
            if stage["status"] == "pending":
                stage["status"] = "running"
                stage["started_at"] = get_current_time()
                stage["started_at_epoch"] = time.time()
            if stage["done"] >= stage["total"]:
                stage["status"] = "done"
                stage["finished_at"] = get_current_time()
                stage["finished_at_epoch"] = time.time()

    def finish_stage(
        self, job_id: str, stage_key: str, fill_remaining: bool = False
    ) -> None:
        with self._lock:
            stage = self._jobs.get(job_id, {}).get("stages", {}).get(stage_key)
            if not stage:
                return
            if fill_remaining:
                stage["done"] = stage["total"]
                if not stage["scopes"]:
                    stage["scopes"]["all"] = {
                        "total": stage["total"],
                        "done": stage["total"],
                    }
                else:
                    remaining = stage["total"] - self._calc_stage_done(stage)
                    if remaining > 0:
                        all_scope = stage["scopes"].setdefault(
                            "all", {"total": 0.0, "done": 0.0}
                        )
                        all_scope["total"] = max(all_scope["total"], stage["total"])
                        all_scope["done"] = min(
                            all_scope["done"] + remaining, all_scope["total"]
                        )
            stage["status"] = "done"
            stage["finished_at"] = get_current_time()
            stage["finished_at_epoch"] = time.time()

    def fail_stage(self, job_id: str, stage_key: str, error: str | None = None) -> None:
        with self._lock:
            stage = self._jobs.get(job_id, {}).get("stages", {}).get(stage_key)
            if not stage:
                return
            stage["status"] = "failed"
            stage["error"] = error
            stage["finished_at"] = get_current_time()
            stage["finished_at_epoch"] = time.time()

    def skip_stage(
        self, job_id: str, stage_key: str, reason: str | None = None
    ) -> None:
        with self._lock:
            stage = self._jobs.get(job_id, {}).get("stages", {}).get(stage_key)
            if not stage:
                return
            stage["status"] = "skipped"
            stage["meta"]["skip_reason"] = reason
            stage["finished_at"] = get_current_time()
            stage["finished_at_epoch"] = time.time()

    def mark_job_done(
        self,
        job_id: str,
        fill_remaining: bool = False,
        mark_unfinished_as_done: bool = False,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if fill_remaining or mark_unfinished_as_done:
                for stage in job["stages"].values():
                    if stage["done"] < stage["total"]:
                        stage["done"] = stage["total"]
                        stage["status"] = "done"
                        stage["finished_at"] = get_current_time()
                        stage["finished_at_epoch"] = time.time()
            job["status"] = "done"
            job["finished_at_epoch"] = time.time()

    def mark_job_failed(self, job_id: str, error: str | None = None) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = "failed"
            job["finished_at_epoch"] = time.time()
            if error:
                job["error"] = error

    def mark_job_killed(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = "killed"
            job["finished_at_epoch"] = time.time()

    def add_llm_usage(self, job_id: str, record: dict[str, object]) -> None:
        with self._lock:
            if job_id not in self._jobs:
                self._jobs[job_id] = self._new_job_state()
            job = self._jobs[job_id]
            reducer = job.setdefault("_usage_reducer", UsageReducer())
            reducer.add(record)
            errors = job.get("llm_usage", {}).get("export_errors", [])
            job["llm_usage"] = reducer.summary(
                page_count=sum(job.get("pdf_page_dict", {}).values())
            )
            job["llm_usage"]["export_errors"] = errors

    def get_llm_records(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return job["_usage_reducer"].records() if job else []

    def add_llm_usage_export_error(self, job_id: str, error: str) -> None:
        with self._lock:
            if job_id not in self._jobs:
                self._jobs[job_id] = self._new_job_state()
            aggregate = self._jobs[job_id].setdefault(
                "llm_usage", self._new_llm_usage_state()
            )
            errors = aggregate.setdefault("export_errors", [])
            if len(errors) < 10:
                errors.append(error)

    def get_progress(self, job_id: str, detail: bool = False) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                return {
                    "total_steps": 0,
                    "completed_steps": 0,
                    "percent": 0.0,
                    "elapsed_seconds": 0.0,
                }

            job = self._jobs[job_id]
            stages = job["stages"]
            total = sum(stage["total"] for stage in stages.values())
            completed = sum(stage["done"] for stage in stages.values())

            status = job.get("status")
            if status == "done":
                percent = 100.0
            else:
                percent = round(completed / total * 100, 2) if total > 0 else 0.0

            result = {
                "status": job.get("status"),
                "total_steps": total,
                "completed_steps": completed,
                "percent": percent,
                "elapsed_seconds": self._elapsed_seconds(job),
                "llm_usage": deepcopy(
                    job.get("llm_usage", self._new_llm_usage_state())
                ),
            }
            if not detail:
                return result

            file_detail = {}
            for file_id, file_meta in job["files"].items():
                file_stages = {
                    stage_key: stage
                    for stage_key, stage in stages.items()
                    if stage["file_id"] == file_id
                }
                f_total = sum(s["total"] for s in file_stages.values())
                f_done = sum(s["done"] for s in file_stages.values())
                f_percent = round(f_done / f_total * 100, 2) if f_total > 0 else 0.0
                file_detail[file_id] = {
                    "page_count": file_meta.get("page_count", 0),
                    "total_steps": f_total,
                    "completed_steps": f_done,
                    "percent": f_percent,
                    "pages": self._build_page_progress(
                        file_stages=file_stages,
                        page_count=int(file_meta.get("page_count", 0) or 0),
                        job_done=(status == "done"),
                    ),
                    "stages": {
                        stage_key: {
                            "name": stage["name"],
                            "total": stage["total"],
                            "done": stage["done"],
                            "percent": round(stage["done"] / stage["total"] * 100, 2)
                            if stage["total"] > 0
                            else 0.0,
                            "status": stage["status"],
                            "error": stage.get("error"),
                            "elapsed_seconds": _stage_elapsed_seconds(stage),
                            "scopes": stage.get("scopes", {}),
                            "meta": stage.get("meta", {}),
                        }
                        for stage_key, stage in file_stages.items()
                    },
                }
            result["files"] = file_detail
            return result

    def _build_page_progress(
        self,
        *,
        file_stages: dict,
        page_count: int,
        job_done: bool,
    ) -> list[dict]:
        """Per-page progress from page-scoped node stages, weighted by node weight.

        A stage is page-scoped iff it has ``page:{n}`` scopes (populated by the runner's
        per-page completion events). A page's percent is the node-weight it has cleared
        over the total page-scoped weight; ``current_node`` is the first page-scoped node
        (in start order) that page has not yet cleared. Document-level nodes (savers,
        combine, upload) have no page scopes and do not count toward per-page progress.
        """
        if page_count <= 0:
            return []
        # Page-scoped stages are marked upfront (meta.page_scoped) so weight_total is the
        # FULL page-node weight from the start. Selecting by "has a page: scope" instead
        # would make the first pages read as 100% (they clear the only stage seen so far).
        page_stages = [
            stage
            for stage in file_stages.values()
            if (stage.get("meta") or {}).get("page_scoped")
        ]
        if not page_stages:
            # No scope metadata (e.g. non-native path) -> let the frontend approximate.
            return []
        page_stages.sort(
            key=lambda s: (
                (s.get("meta") or {}).get("order", float("inf")),
                s.get("started_at_epoch") or float("inf"),
                s["name"],
            )
        )
        weight_total = sum(stage["total"] for stage in page_stages)

        pages: list[dict] = []
        for page_index in range(page_count):
            accrued = 0.0
            current_node = None
            for stage in page_stages:
                scope = stage.get("scopes", {}).get(f"page:{page_index}")
                cleared = (
                    scope is not None
                    and scope["total"] > 0
                    and scope["done"] >= scope["total"] - 1e-9
                )
                if cleared:
                    accrued += stage["total"]
                elif current_node is None:
                    current_node = (stage.get("meta") or {}).get("node_name") or stage[
                        "name"
                    ]
            percent = (
                round(accrued / weight_total * 100, 2) if weight_total > 0 else 0.0
            )
            if job_done or (weight_total > 0 and percent >= 100.0):
                status = "done"
                percent = 100.0
                current_node = None
            elif accrued > 0:
                status = "running"
            else:
                status = "pending"
            pages.append(
                {
                    "index": page_index,
                    "percent": percent,
                    "current_node": current_node,
                    "status": status,
                }
            )
        return pages

    def get_current_page_count(self, job_id, basename):
        with self._lock:
            if job_id not in self._jobs:
                return 0
            job = self._jobs[job_id]
            return job.get("pdf_page_dict", {}).get(basename, 1)


@dataclass(frozen=True)
class ProgressContext:
    job_id: str
    file_id: str
    scope_key: str = "all"
    scope_total: float | None = None

    def stage_key(self, stage_name: str) -> str:
        return make_stage_key(self.file_id, stage_name)


progress_tracker = _ProgressTracker()


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _str_value(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _stage_elapsed_seconds(stage: dict) -> float:
    started_at = stage.get("started_at_epoch")
    if not isinstance(started_at, (int, float)):
        return 0.0
    finished_at = stage.get("finished_at_epoch")
    end_at = finished_at if isinstance(finished_at, (int, float)) else time.time()
    return round(max(end_at - started_at, 0.0), 2)
