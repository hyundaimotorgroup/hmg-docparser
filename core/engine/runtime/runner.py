from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from collections.abc import Callable

from core.engine.config.compiler import START_NODE_ID, CompiledPipeline
from core.engine.config.models import NodeSpec
from core.engine.runtime.cancellation import PipelineCancelled
from core.engine.runtime.models import PipelineRunResult
from core.engine.runtime.page_expand import (
    FANOUT,
    PAGE,
    expand_graph,
    page_id,
    resolve_input_value,
)
from core.interfaces.node import Node, NodeContext, NodeResult
from core.interfaces.observability import Observer
from core.interfaces.registry import NodeRegistry

# Fallback global cap on concurrently-running expanded nodes in the streaming path
# when runtime_config does not specify one. Per-node max_concurrency is still enforced
# on top of this, so a single stage never exceeds its own declared limit.
DEFAULT_STREAM_MAX_WORKERS = 64
DEFAULT_SCHEDULER_MAX_WORKERS = 8


class PipelineRunner:
    def __init__(
        self,
        *,
        registry: NodeRegistry,
        observers: list[Observer] | None = None,
    ) -> None:
        self._registry = registry
        self._observers = observers or []

    def run(
        self,
        compiled: CompiledPipeline,
        *,
        initial_value: object,
        job_id: str = "local",
        runtime_config: dict[str, object] | None = None,
        cancellation_check: Callable[[], bool] | None = None,
    ) -> PipelineRunResult:
        result = PipelineRunResult()
        node_instances = self._build_node_instances(compiled)
        runtime_config = dict(runtime_config or {})
        from core.services.model_routing import validate_model_routes

        validate_model_routes(
            compiled.graph.nodes, registry=runtime_config.get("_capability_registry")
        )
        from core.services.prompt_policy import PromptPolicy, prepare_node_prompts

        prepare_node_prompts(
            compiled.graph.nodes,
            runtime_config.get("node_overrides"),
            PromptPolicy.from_mapping(runtime_config.get("_host_prompt_policy")),
        )
        cancellation_check = cancellation_check or _never_cancelled
        specs_by_id = {node.id: node for node in compiled.graph.nodes}
        scope_by_id = {node.id: node.execution_scope for node in compiled.graph.nodes}

        has_page_nodes = any(scope == PAGE for scope in scope_by_id.values())
        if not has_page_nodes:
            self._run_flat(
                compiled=compiled,
                specs_by_id=specs_by_id,
                node_instances=node_instances,
                initial_value=initial_value,
                job_id=job_id,
                runtime_config=runtime_config,
                cancellation_check=cancellation_check,
                result=result,
            )
            return result

        self._run_page_streaming(
            compiled=compiled,
            specs_by_id=specs_by_id,
            node_instances=node_instances,
            scope_by_id=scope_by_id,
            initial_value=initial_value,
            job_id=job_id,
            runtime_config=runtime_config,
            cancellation_check=cancellation_check,
            result=result,
        )
        return result

    # ------------------------------------------------------------------ #
    # Flat (document-level) scheduling — used for non-page pipelines and  #
    # the fan-out prelude of the streaming path.                          #
    # ------------------------------------------------------------------ #
    def _run_flat(
        self,
        *,
        compiled: CompiledPipeline,
        specs_by_id: dict[str, NodeSpec],
        node_instances: dict[str, Node],
        initial_value: object,
        job_id: str,
        runtime_config: dict[str, object],
        cancellation_check: Callable[[], bool],
        result: PipelineRunResult,
    ) -> None:
        node_ids = list(compiled.topological_order)
        max_workers = self._resolve_scheduler_workers(
            compiled=compiled, runtime_config=runtime_config
        )
        self._schedule_flat(
            node_ids=node_ids,
            upstream=compiled.upstream_by_node,
            downstream=compiled.downstream_by_node,
            specs_by_id=specs_by_id,
            node_instances=node_instances,
            outputs={},
            initial_value=initial_value,
            job_id=job_id,
            runtime_config=runtime_config,
            cancellation_check=cancellation_check,
            result=result,
            max_workers=max_workers,
        )

    def _schedule_flat(
        self,
        *,
        node_ids: list[str],
        upstream: dict[str, list[str]],
        downstream: dict[str, list[str]],
        specs_by_id: dict[str, NodeSpec],
        node_instances: dict[str, Node],
        outputs: dict[str, object],
        initial_value: object,
        job_id: str,
        runtime_config: dict[str, object],
        cancellation_check: Callable[[], bool],
        result: PipelineRunResult,
        max_workers: int,
    ) -> None:
        scheduled = set(node_ids)
        remaining = {
            nid: sum(1 for dep in upstream.get(nid, []) if dep in scheduled)
            for nid in node_ids
        }
        ready = sorted(nid for nid in node_ids if remaining[nid] == 0)
        running: dict[Future[NodeResult], str] = {}

        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
            while ready or running:
                _raise_if_cancelled(cancellation_check)
                while ready and len(running) < max_workers:
                    _raise_if_cancelled(cancellation_check)
                    node_id = ready.pop(0)
                    node_spec = specs_by_id[node_id]
                    value = self._resolve_flat_value(
                        node_spec=node_spec,
                        outputs=outputs,
                        initial_value=initial_value,
                    )
                    context = self._make_context(
                        job_id=job_id,
                        node_id=node_id,
                        node_spec=node_spec,
                        runtime_config=runtime_config,
                        cancellation_check=cancellation_check,
                    )
                    self._notify_start(
                        job_id=job_id, node_id=node_id, node_name=node_spec.node
                    )
                    future = executor.submit(
                        node_instances[node_id].run, context, value
                    )
                    running[future] = node_id
                    result.execution_order.append(node_id)

                if not running:
                    break

                done, _ = wait(set(running), return_when=FIRST_COMPLETED)
                if cancellation_check():
                    for pending in running:
                        pending.cancel()
                    raise PipelineCancelled("pipeline cancelled")
                for future in done:
                    node_id = running.pop(future)
                    node_spec = specs_by_id[node_id]
                    try:
                        node_result = future.result()
                    except PipelineCancelled:
                        for pending in running:
                            pending.cancel()
                        raise
                    except Exception as exc:
                        self._notify_failed(
                            job_id=job_id,
                            node_id=node_id,
                            node_name=node_spec.node,
                            error=str(exc),
                        )
                        for pending in running:
                            pending.cancel()
                        raise
                    self._notify_complete(
                        job_id=job_id, node_id=node_id, node_name=node_spec.node
                    )
                    outputs[node_id] = node_result.value
                    result.values_by_node[node_id] = node_result.value
                    result.metadata_by_node[node_id] = node_result.metadata
                    for child_id in downstream.get(node_id, []):
                        if child_id in remaining:
                            remaining[child_id] -= 1
                            if remaining[child_id] == 0:
                                ready.append(child_id)
                ready.sort()

    # ------------------------------------------------------------------ #
    # Page-streaming scheduling.                                          #
    # ------------------------------------------------------------------ #
    def _run_page_streaming(
        self,
        *,
        compiled: CompiledPipeline,
        specs_by_id: dict[str, NodeSpec],
        node_instances: dict[str, Node],
        scope_by_id: dict[str, str],
        initial_value: object,
        job_id: str,
        runtime_config: dict[str, object],
        cancellation_check: Callable[[], bool],
        result: PipelineRunResult,
    ) -> None:
        upstream_all = compiled.upstream_by_node
        downstream_all = compiled.downstream_by_node

        # Phase B = page nodes + everything transitively downstream of them.
        page_ids = {nid for nid, scope in scope_by_id.items() if scope == PAGE}
        phase_b: set[str] = set(page_ids)
        stack = list(page_ids)
        while stack:
            current = stack.pop()
            for child in downstream_all.get(current, []):
                if child not in phase_b:
                    phase_b.add(child)
                    stack.append(child)
        phase_a = [nid for nid in compiled.topological_order if nid not in phase_b]

        outputs: dict[str, object] = {}

        # Phase A: document-level prelude (fan-out/split and any pre-page doc nodes).
        if phase_a:
            self._schedule_flat(
                node_ids=phase_a,
                upstream=upstream_all,
                downstream=downstream_all,
                specs_by_id=specs_by_id,
                node_instances=node_instances,
                outputs=outputs,
                initial_value=initial_value,
                job_id=job_id,
                runtime_config=runtime_config,
                cancellation_check=cancellation_check,
                result=result,
                max_workers=self._resolve_scheduler_workers(
                    compiled=compiled, runtime_config=runtime_config
                ),
            )

        page_count = self._infer_page_count(
            page_ids=page_ids,
            upstream=upstream_all,
            scope_by_id=scope_by_id,
            outputs=outputs,
        )

        scheduled_ids = [nid for nid in compiled.topological_order if nid in phase_b]
        expanded = expand_graph(
            scheduled_ids=scheduled_ids,
            deps=upstream_all,
            scope=scope_by_id,
            page_count=page_count,
            prerun_ids=frozenset(phase_a),
        )
        self._schedule_pages(
            expanded=expanded,
            specs_by_id=specs_by_id,
            node_instances=node_instances,
            outputs=outputs,
            initial_value=initial_value,
            job_id=job_id,
            runtime_config=runtime_config,
            cancellation_check=cancellation_check,
            result=result,
            page_count=page_count,
        )

    def _schedule_pages(
        self,
        *,
        expanded,
        specs_by_id: dict[str, NodeSpec],
        node_instances: dict[str, Node],
        outputs: dict[str, object],
        initial_value: object,
        job_id: str,
        runtime_config: dict[str, object],
        cancellation_check: Callable[[], bool],
        result: PipelineRunResult,
        page_count: int,
    ) -> None:
        by_id = expanded.by_id()
        upstream = expanded.upstream
        downstream = expanded.downstream
        node_ids = [node.id for node in expanded.nodes]
        if not node_ids:
            return

        metas: dict[str, dict[str, object]] = {}
        origin_remaining: dict[str, int] = {}
        for node in expanded.nodes:
            origin_remaining[node.origin] = origin_remaining.get(node.origin, 0) + 1
        origin_started: set[str] = set()
        inflight_by_origin: dict[str, int] = {}

        remaining = {nid: len(upstream.get(nid, [])) for nid in node_ids}
        ready = sorted(nid for nid in node_ids if remaining[nid] == 0)
        running: dict[Future[NodeResult], str] = {}
        global_max = self._resolve_stream_workers(
            runtime_config=runtime_config, expanded_count=len(node_ids)
        )

        with ThreadPoolExecutor(max_workers=global_max) as executor:
            while ready or running:
                _raise_if_cancelled(cancellation_check)
                # Admit ready nodes while respecting the global cap and each origin's
                # own max_concurrency (so e.g. the layout server never sees more than
                # its declared 8 concurrent calls even though other stages run too).
                while len(running) < global_max:
                    _raise_if_cancelled(cancellation_check)
                    pick_index = self._pick_admittable(
                        ready=ready,
                        by_id=by_id,
                        specs_by_id=specs_by_id,
                        inflight_by_origin=inflight_by_origin,
                    )
                    if pick_index is None:
                        break
                    xid = ready.pop(pick_index)
                    xnode = by_id[xid]
                    origin = xnode.origin
                    node_spec = specs_by_id[origin]
                    value = resolve_input_value(xnode.sources, outputs, initial_value)
                    context = self._make_context(
                        job_id=job_id,
                        node_id=origin,
                        node_spec=node_spec,
                        runtime_config=runtime_config,
                        cancellation_check=cancellation_check,
                        page_index=xnode.page_index,
                    )
                    if origin not in origin_started:
                        origin_started.add(origin)
                        self._notify_start(
                            job_id=job_id, node_id=origin, node_name=node_spec.node
                        )
                    if xnode.page_index is not None:
                        self._notify_page_start(
                            job_id=job_id,
                            node_id=origin,
                            node_name=node_spec.node,
                            page_index=xnode.page_index,
                            page_count=page_count,
                        )
                    inflight_by_origin[origin] = inflight_by_origin.get(origin, 0) + 1
                    future = executor.submit(node_instances[origin].run, context, value)
                    running[future] = xid

                if not running:
                    break

                done, _ = wait(set(running), return_when=FIRST_COMPLETED)
                if cancellation_check():
                    for pending in running:
                        pending.cancel()
                    raise PipelineCancelled("pipeline cancelled")
                for future in done:
                    xid = running.pop(future)
                    xnode = by_id[xid]
                    origin = xnode.origin
                    node_spec = specs_by_id[origin]
                    inflight_by_origin[origin] -= 1
                    try:
                        node_result = future.result()
                    except PipelineCancelled:
                        for pending in running:
                            pending.cancel()
                        raise
                    except Exception as exc:
                        self._notify_failed(
                            job_id=job_id,
                            node_id=origin,
                            node_name=node_spec.node,
                            error=str(exc),
                        )
                        for pending in running:
                            pending.cancel()
                        raise

                    outputs[xid] = node_result.value
                    metas[xid] = node_result.metadata
                    if xnode.page_index is not None:
                        self._notify_page_complete(
                            job_id=job_id,
                            node_id=origin,
                            node_name=node_spec.node,
                            page_index=xnode.page_index,
                            page_count=page_count,
                        )

                    origin_remaining[origin] -= 1
                    if origin_remaining[origin] == 0:
                        self._notify_complete(
                            job_id=job_id, node_id=origin, node_name=node_spec.node
                        )
                        self._store_origin_result(
                            result=result,
                            origin=origin,
                            scope=xnode.scope,
                            page_count=page_count,
                            outputs=outputs,
                            metas=metas,
                        )

                    for child_id in downstream.get(xid, []):
                        remaining[child_id] -= 1
                        if remaining[child_id] == 0:
                            ready.append(child_id)
                ready.sort()

    @staticmethod
    def _pick_admittable(
        *,
        ready: list[str],
        by_id: dict,
        specs_by_id: dict[str, NodeSpec],
        inflight_by_origin: dict[str, int],
    ) -> int | None:
        """Index into `ready` of the first node whose origin is below its concurrency cap."""
        for index, xid in enumerate(ready):
            origin = by_id[xid].origin
            cap = specs_by_id[origin].max_concurrency
            if inflight_by_origin.get(origin, 0) < max(1, cap):
                return index
        return None

    def _store_origin_result(
        self,
        *,
        result: PipelineRunResult,
        origin: str,
        scope: str,
        page_count: int,
        outputs: dict[str, object],
        metas: dict[str, dict[str, object]],
    ) -> None:
        if scope == PAGE:
            page_values = [outputs[page_id(origin, p)] for p in range(page_count)]
            result.values_by_node[origin] = page_values
            outputs[origin] = page_values
            result.metadata_by_node[origin] = {
                "mode": "page_parallel",
                "item_count": page_count,
                "items": [metas.get(page_id(origin, p), {}) for p in range(page_count)],
            }
        else:
            result.values_by_node[origin] = outputs.get(origin)
            result.metadata_by_node[origin] = metas.get(origin, {})
        result.execution_order.append(origin)

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #
    def _infer_page_count(
        self,
        *,
        page_ids: set[str],
        upstream: dict[str, list[str]],
        scope_by_id: dict[str, str],
        outputs: dict[str, object],
    ) -> int:
        counts: set[int] = set()
        for node_id in page_ids:
            for dep in upstream.get(node_id, []):
                if scope_by_id.get(dep) == FANOUT:
                    value = outputs.get(dep)
                    if isinstance(value, list):
                        counts.add(len(value))
        if not counts:
            for node_id, scope in scope_by_id.items():
                if scope == FANOUT and isinstance(outputs.get(node_id), list):
                    counts.add(len(outputs[node_id]))  # type: ignore[arg-type]
        if not counts:
            return 0
        if len(counts) > 1:
            raise ValueError(
                f"inconsistent page counts from fan-out nodes: {sorted(counts)}"
            )
        return next(iter(counts))

    def _make_context(
        self,
        *,
        job_id: str,
        node_id: str,
        node_spec: NodeSpec,
        runtime_config: dict[str, object],
        cancellation_check: Callable[[], bool] | None = None,
        page_index: int | None = None,
    ) -> NodeContext:
        metadata: dict[str, object] = {
            "depends_on": [dep for dep in node_spec.depends_on if dep != START_NODE_ID],
            "runtime_config": runtime_config,
            "cancellation_check": cancellation_check,
        }
        if page_index is not None:
            metadata["page_index"] = page_index
        return NodeContext(
            job_id=job_id,
            node_id=node_id,
            node_name=node_spec.node,
            config=dict(node_spec.node_config),
            metadata=metadata,
        )

    def _build_node_instances(self, compiled: CompiledPipeline) -> dict[str, Node]:
        instances: dict[str, Node] = {}
        for node_spec in compiled.graph.nodes:
            node_cls = self._registry.get(node_spec.node)
            instances[node_spec.id] = node_cls()
        return instances

    def _resolve_scheduler_workers(
        self,
        *,
        compiled: CompiledPipeline,
        runtime_config: dict[str, object],
    ) -> int:
        configured = runtime_config.get("scheduler_max_workers")
        if isinstance(configured, int) and configured >= 1:
            return configured
        return max(1, min(len(compiled.graph.nodes), DEFAULT_SCHEDULER_MAX_WORKERS))

    def _resolve_stream_workers(
        self,
        *,
        runtime_config: dict[str, object],
        expanded_count: int,
    ) -> int:
        configured = runtime_config.get("scheduler_max_workers")
        if isinstance(configured, int) and configured >= 1:
            return max(1, min(expanded_count, configured))
        return max(1, min(expanded_count, DEFAULT_STREAM_MAX_WORKERS))

    def _resolve_flat_value(
        self,
        *,
        node_spec: NodeSpec,
        outputs: dict[str, object],
        initial_value: object,
    ) -> object:
        actual_dependencies = [
            dep for dep in node_spec.depends_on if dep != START_NODE_ID
        ]
        if not actual_dependencies:
            return initial_value
        if len(actual_dependencies) == 1:
            return outputs[actual_dependencies[0]]
        return [outputs[dep] for dep in actual_dependencies]

    def _notify_start(self, *, job_id: str, node_id: str, node_name: str) -> None:
        for observer in self._observers:
            observer.on_node_start(job_id=job_id, node_id=node_id, node_name=node_name)

    def _notify_complete(self, *, job_id: str, node_id: str, node_name: str) -> None:
        for observer in self._observers:
            observer.on_node_complete(
                job_id=job_id, node_id=node_id, node_name=node_name
            )

    def _notify_failed(
        self, *, job_id: str, node_id: str, node_name: str, error: str
    ) -> None:
        for observer in self._observers:
            observer.on_node_failed(
                job_id=job_id, node_id=node_id, node_name=node_name, error=error
            )

    def _notify_page_complete(
        self,
        *,
        job_id: str,
        node_id: str,
        node_name: str,
        page_index: int,
        page_count: int,
    ) -> None:
        for observer in self._observers:
            try:
                observer.on_node_page_complete(
                    job_id=job_id,
                    node_id=node_id,
                    node_name=node_name,
                    page_index=page_index,
                    page_count=page_count,
                )
            except Exception:  # noqa: BLE001 - progress must never break the pipeline
                pass

    def _notify_page_start(
        self,
        *,
        job_id: str,
        node_id: str,
        node_name: str,
        page_index: int,
        page_count: int,
    ) -> None:
        for observer in self._observers:
            try:
                observer.on_node_page_start(
                    job_id=job_id,
                    node_id=node_id,
                    node_name=node_name,
                    page_index=page_index,
                    page_count=page_count,
                )
            except Exception:  # noqa: BLE001 - observability must never break the pipeline
                pass


def _never_cancelled() -> bool:
    return False


def _raise_if_cancelled(cancellation_check: Callable[[], bool]) -> None:
    if cancellation_check():
        raise PipelineCancelled("pipeline cancelled")
