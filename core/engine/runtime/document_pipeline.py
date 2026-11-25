from __future__ import annotations

from collections.abc import Callable
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
import mimetypes
from pathlib import Path
import shutil
from typing import Any

from core.domain.document.models import DocumentDTO
from core.domain.mappers.legacy import document_dto_from_source
from core.engine.config.compiler import CompiledPipeline, compile_pipeline_graph
from core.engine.config.runtime_config import RuntimeConfig, load_yaml_with_env
from core.engine.config.translator import load_native_runtime_config
from core.engine.registry import (
    build_default_node_registry,
    build_node_registry_for_graph,
)
from core.engine.runtime.input_files import prepare_input_files
from core.engine.runtime.models import PipelineRunResult
from core.engine.runtime.page_expand import PAGE
from core.engine.runtime.runner import PipelineRunner
from core.interfaces.observability import Observer
from core.interfaces.registry import NodeRegistry
from core.observability import RuntimeNodeProgressObserver
from core.observability.llm_usage import (
    flush_langfuse_exporters,
    langfuse_config_from_raw,
    safe_accounting_diagnostic,
)
from core.observability.progress_tracker import progress_tracker
from core.services.prompt_policy import PromptPolicy, prepare_node_prompts
from core.observability.llm_pricing import PricingSnapshot
from core.observability.llm_usage_aggregation import (
    write_atomic_summary,
    format_usage_summary,
)
from core.services.document_limits import DocumentLimits
from core.services.pdf_warning_service import suppress_pdf_parser_warnings


@dataclass(slots=True)
class DocumentPipelineBatchResult:
    job_id: str
    mode: str
    results_by_file: dict[str, PipelineRunResult] = field(default_factory=dict)
    skipped_files: list[str] = field(default_factory=list)


def run_document_pipeline_from_config_path(
    config_path: str,
    *,
    input_path: str | None = None,
    output_path: str | None = None,
    job_id: str = "main",
    registry: NodeRegistry | None = None,
    observers: list[Observer] | None = None,
    progress_job_state: MutableMapping[str, MutableMapping[str, object]] | None = None,
    runtime_config: Mapping[str, Any] | None = None,
    cancellation_check: Callable[[], bool] | None = None,
) -> DocumentPipelineBatchResult:
    raw_config = _load_raw_config(config_path)
    native_config = load_native_runtime_config(raw_config)
    config = RuntimeConfig(
        inputs=native_config.input_dir,
        outputs=native_config.output_dir,
        job_id=job_id,
    )
    return run_document_pipeline(
        config,
        raw_config=raw_config,
        input_path=input_path,
        output_path=output_path,
        job_id=job_id,
        registry=registry,
        observers=observers,
        progress_job_state=progress_job_state,
        runtime_config=runtime_config,
        cancellation_check=cancellation_check,
    )


def run_document_pipeline(
    config: RuntimeConfig,
    *,
    raw_config: Mapping[str, Any] | None = None,
    config_dir: str | Path | None = None,
    input_path: str | None = None,
    output_path: str | None = None,
    job_id: str = "main",
    registry: NodeRegistry | None = None,
    observers: list[Observer] | None = None,
    progress_job_state: MutableMapping[str, MutableMapping[str, object]] | None = None,
    runtime_config: Mapping[str, Any] | None = None,
    cancellation_check: Callable[[], bool] | None = None,
) -> DocumentPipelineBatchResult:
    suppress_pdf_parser_warnings()

    if input_path is not None:
        config.inputs = input_path
    if output_path is not None:
        config.outputs = output_path
    config.job_id = job_id

    if raw_config is None:
        raise ValueError("native pipeline config with pipeline.nodes is required")

    config_dir = config_dir or getattr(raw_config, "config_dir", None)
    native_config = load_native_runtime_config(raw_config)
    raw_config = native_config.model_dump()
    graph = native_config.pipeline
    from core.services.model_routing import validate_model_routes

    validate_model_routes(
        graph.nodes, registry=(runtime_config or {}).get("_capability_registry")
    )
    host_policy = PromptPolicy.from_mapping(native_config.prompt_policy)
    prepare_node_prompts(
        graph.nodes, (runtime_config or {}).get("node_overrides"), host_policy
    )
    snapshot, pricing_error = _load_optional_pricing(
        native_config.pricing_file, runtime_config, config_dir
    )
    runtime_config = {
        **dict(runtime_config or {}),
        "_host_prompt_policy": native_config.prompt_policy,
        "_pricing_snapshot": snapshot,
        "_pricing_error": pricing_error,
    }
    runtime_registry = registry or build_node_registry_for_graph(graph)
    compiled = compile_pipeline_graph(graph, registry=runtime_registry)
    result_status = "failed"
    try:
        result = _run_native_graph_pipeline(
            config,
            raw_config=raw_config,
            compiled=compiled,
            job_id=job_id,
            registry=runtime_registry,
            observers=observers,
            progress_job_state=progress_job_state,
            runtime_config=runtime_config,
            cancellation_check=cancellation_check,
        )
        statuses = [run.metadata_by_node.get(compiled.graph.output_node, {}).get("result_status", "complete") for run in result.results_by_file.values()]
        result_status = "complete_with_errors" if any(s != "complete" for s in statuses) else "complete"
        if statuses and all(s == "failed" for s in statuses):
            result_status = "failed"
        progress_tracker.mark_job_done(job_id)
        return result
    except BaseException as exc:
        if cancellation_check and cancellation_check():
            progress_tracker.mark_job_killed(job_id)
        else:
            progress_tracker.mark_job_failed(
                job_id, "pipeline failed (" + type(exc).__name__ + ")"
            )
        raise
    finally:
        try:
            progress = progress_tracker.get_progress(job_id)
            summary = {
                **progress.get("llm_usage", {}),
                "job_status": progress.get("status", "unknown"),
                "result_status": result_status,
            }
            if pricing_error:
                summary.setdefault("export_errors", []).append(pricing_error)
            try:
                write_atomic_summary(
                    Path(config.outputs) / "_llm_usage_summary.json", summary
                )
            except Exception:
                safe_accounting_diagnostic(job_id, "accounting summary write failed")
            try:
                print(format_usage_summary(summary), flush=True)
            except Exception:
                safe_accounting_diagnostic(job_id, "accounting summary display failed")
        except Exception:
            safe_accounting_diagnostic(job_id, "accounting summary failed")
        finally:
            flush_langfuse_exporters()


def _load_optional_pricing(pricing_file, runtime_config=None, config_dir=None):
    runtime = runtime_config or {}
    host = runtime.get("_host_pricing_path")
    if pricing_file is None and host is None:
        return None, None
    try:

        def resolve(value):
            if not isinstance(value, (str, Path)) or not str(value).strip():
                raise ValueError("invalid pricing path")
            path = Path(value)
            if not path.is_absolute():
                if config_dir is None:
                    raise ValueError("pricing path requires config directory")
                path = Path(config_dir) / path
            return path.resolve()

        selected = resolve(pricing_file) if pricing_file is not None else None
        # Historic trusted host path uses cwd; new native paths never infer it.
        host_path = Path(host).resolve() if host is not None else None
        if selected is not None and host_path is not None and selected != host_path:
            return None, "pricing_path_conflict"
        return PricingSnapshot.from_path(selected or host_path), None
    except Exception:
        return None, "pricing_load_failed"


def _run_native_graph_pipeline(
    config: RuntimeConfig,
    *,
    raw_config: Mapping[str, Any],
    compiled: CompiledPipeline,
    job_id: str,
    registry: NodeRegistry | None,
    observers: list[Observer] | None,
    progress_job_state: MutableMapping[str, MutableMapping[str, object]] | None,
    runtime_config: Mapping[str, Any] | None,
    cancellation_check: Callable[[], bool] | None,
) -> DocumentPipelineBatchResult:
    raw_limits = raw_config.get("document_limits")
    if raw_limits is not None and not isinstance(raw_limits, Mapping):
        raise ValueError("document_limits must be a mapping")
    limits = DocumentLimits.from_mapping(raw_limits)
    file_list, pdf_page_dict = prepare_input_files(
        config.inputs, config.outputs, limits=limits
    )
    progress_tracker.init_job(
        job_id,
        {
            file_id: {"page_count": page_count}
            for file_id, page_count in pdf_page_dict.items()
        },
    )

    result = DocumentPipelineBatchResult(job_id=job_id, mode="native")
    runtime_registry = registry or build_default_node_registry()
    node_weights = _build_node_progress_weights(compiled)
    for source_path in file_list:
        basename = Path(source_path).stem
        _register_native_progress_stages(
            job_id=job_id,
            file_id=basename,
            page_count=pdf_page_dict.get(basename, 0),
            compiled=compiled,
            node_weights=node_weights,
        )

    for source_path in file_list:
        _raise_if_cancelled(cancellation_check)
        basename = Path(source_path).stem

        runtime_observers = [
            RuntimeNodeProgressObserver(
                file_id=basename,
                page_count=pdf_page_dict.get(basename, 0),
                node_weights=node_weights,
                job_state=progress_job_state,
            )
        ]
        runtime_observers.extend(observers or [])
        try:
            runner = PipelineRunner(
                registry=runtime_registry, observers=runtime_observers
            )
            run_result = runner.run(
                compiled,
                initial_value=document_dto_from_source(
                    source_path,
                    mime_type=_infer_mime_type(source_path),
                ),
                job_id=job_id,
                runtime_config={
                    "outputs": config.outputs,
                    "document_id": basename,
                    "langfuse": langfuse_config_from_raw(raw_config),
                    "scheduler_max_workers": raw_config["resource_budget"][
                        "scheduler_max_workers"
                    ],
                    **dict(runtime_config or {}),
                },
                cancellation_check=cancellation_check,
            )
            result.results_by_file[basename] = run_result
            _raise_if_cancelled(cancellation_check)
            _write_final_document_markdown(
                config, basename, run_result, compiled.graph.output_node
            )
        finally:
            _cleanup_temp_page_artifacts(compiled, config.outputs, basename)

    return result


def _build_node_progress_weights(compiled: CompiledPipeline) -> dict[str, float]:
    return {
        node.id: _node_progress_weight(node.node_config)
        for node in compiled.graph.nodes
    }


def _node_progress_weight(node_config: Mapping[str, Any]) -> float:
    raw_weight = node_config.get("progress_weight", 1.0)
    try:
        weight = float(raw_weight)
    except (TypeError, ValueError):
        weight = 1.0
    return weight if weight > 0 else 1.0


def _register_native_progress_stages(
    *,
    job_id: str,
    file_id: str,
    page_count: int,
    compiled: CompiledPipeline,
    node_weights: Mapping[str, float],
) -> None:
    progress_tracker.ensure_job_file(job_id, file_id, page_count=page_count)
    for order_index, node in enumerate(compiled.graph.nodes):
        page_scoped = node.execution_scope == PAGE
        progress_tracker.register_stage(
            job_id=job_id,
            file_id=file_id,
            stage_name=f"runtime:{node.id}",
            total=node_weights.get(node.id, 1.0),
            meta={
                "node_name": node.node,
                "layer": "runtime",
                "progress_weight": node_weights.get(node.id, 1.0),
                # Marked upfront so per-page progress uses the FULL page-node weight as
                # denominator from the start (otherwise early pages read as 100%).
                "page_scoped": page_scoped,
                # Config/topological position so "current node" is reported in pipeline
                # order even before a stage has started.
                "order": order_index,
            },
        )


def _raise_if_cancelled(cancellation_check: Callable[[], bool] | None) -> None:
    if cancellation_check is not None and cancellation_check():
        from core.engine.runtime.cancellation import PipelineCancelled

        raise PipelineCancelled("pipeline cancelled")


def _load_raw_config(config_path: str) -> Mapping[str, Any]:
    raw = load_yaml_with_env(config_path)
    if not isinstance(raw, Mapping):
        raise ValueError("config root must be a mapping")
    return raw


def _infer_mime_type(source_path: str) -> str:
    suffix = Path(source_path).suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    guessed, _ = mimetypes.guess_type(source_path)
    return guessed or "application/octet-stream"


def _cleanup_temp_page_artifacts(
    compiled: CompiledPipeline, output_root: str, document_id: str
) -> None:
    """Remove temporary split PDFs and layout crops unless explicitly retained."""
    for node in compiled.graph.nodes:
        if _keep_page_artifacts(node.node_config):
            continue
        if node.node == "pdf_page_split_loader":
            configured = node.node_config.get("output_dir")
            base_dir = (
                Path(configured)
                if isinstance(configured, str) and configured.strip()
                else Path(output_root) / "_page_split"
            )
            shutil.rmtree(base_dir / document_id, ignore_errors=True)
        elif node.node in {"dolphin_layout_parser", "dolphin_vllm_layout_parser"}:
            configured = node.node_config.get("crop_output_dir")
            base_dir = (
                Path(configured)
                if isinstance(configured, str) and configured.strip()
                else Path(output_root) / "_layout_crops"
            )
            shutil.rmtree(base_dir / document_id, ignore_errors=True)


def _keep_page_artifacts(node_config: Mapping[str, Any]) -> bool:
    raw_keep = node_config.get("keep_page_artifacts", False)
    return (
        raw_keep
        if isinstance(raw_keep, bool)
        else str(raw_keep).strip().lower() in {"1", "true", "yes", "y"}
    )


def _write_final_document_markdown(
    config: RuntimeConfig,
    basename: str,
    run_result: PipelineRunResult,
    output_node: str,
) -> str | None:
    output_dir = Path(config.outputs)
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"{basename}.md"

    document = _find_output_document_result(run_result, output_node)
    if document is not None:
        from core.services.markdown_validation import document_result_status
        state = document_result_status(document)
        run_result.metadata_by_node.setdefault(output_node, {})["result_status"] = state
    if document is not None and document.markdown:
        final_path.write_text(document.markdown, encoding="utf-8")
        print(f"최종 markdown 저장 완료: {final_path} <- native document result")
        return str(final_path)

    if document is not None:
        artifact = next(
            (
                item
                for item in document.artifacts
                if item.media_type == "text/markdown" and Path(item.path).exists()
            ),
            None,
        )
        if artifact is not None:
            source_path = Path(artifact.path)
            document.markdown = source_path.read_text(encoding="utf-8")
            run_result.metadata_by_node.setdefault(output_node, {})["result_status"] = document_result_status(document)
            final_path.write_text(
                document.markdown, encoding="utf-8"
            )
            print(f"최종 markdown 저장 완료: {final_path} <- {source_path.name}")
            return str(final_path)

    raise ValueError(
        f"configured output node produced no Markdown document: {output_node}"
    )


def _find_output_document_result(
    run_result: PipelineRunResult, output_node: str
) -> DocumentDTO | None:
    value = run_result.values_by_node.get(output_node)
    return value if isinstance(value, DocumentDTO) else None
