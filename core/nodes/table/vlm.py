from __future__ import annotations

from pathlib import Path

from core.domain.layout.models import PageEnrichedDTO, PageLayoutDTO
from core.engine.runtime.time_budget import remaining_timeout_seconds
from core.interfaces.node import Node, NodeContext, NodeResult
from core.observability.llm_usage import build_llm_observability
from core.services.table_vlm import enrich_tables_with_vlm
from core.services.page_failures import record_block_failures, record_page_failure


class TableVLMCaptionMakerNode(Node):
    node_name = "table_vlm_caption_maker"
    input_type = "page_layout_dto@v1"
    output_type = "page_enriched_dto@v1"
    is_page_parallel = True

    def run(self, context: NodeContext, value: object) -> NodeResult:
        page_layouts, single_input = _coerce_page_layouts(value)
        model_name = _str_config(context, "model_name", "vlm_model_name", "")
        if not model_name:
            raise ValueError(
                "table_vlm_caption_maker requires model_name or runtime vlm_model_name"
            )
        from core.services.model_routing import (
            select_model_route,
            node_inference_options,
        )

        defaults = {"model_name": model_name}
        runtime = _runtime_config(context)
        for key in (
            "provider",
            "base_url",
            "api_key",
            "api_version",
            "project_id",
            "api_type",
            "extra_body",
        ):
            defaults[key] = runtime.get("vlm_" + key)
        table_output_format = _table_output_format_config(context)
        output_dir = _resolve_output_dir(context)
        file_prefix = _str_config(context, "file_prefix", "document_id", "") or (
            page_layouts[0].page.document_id if page_layouts else "document"
        )
        usage_callback, trace_metadata = build_llm_observability(context)
        options = node_inference_options(context)
        enriched_pages = []
        for page_layout in page_layouts:
            try:
                result_blocks = {}
                for level in (None, 1, 2, 3):
                    blocks = [
                        b
                        for b in page_layout.blocks
                        if (
                            b.metadata.get("stage2_level")
                            if b.metadata.get("stage2_level") in (1, 2, 3)
                            else None
                        )
                        == level
                    ]
                    if not blocks:
                        continue
                    route = select_model_route(
                        context.config, level=level, defaults=defaults
                    )
                    kwargs = route.kwargs()
                    reasoning = kwargs.pop("reasoning")
                    deployment = kwargs.pop("deployment")
                    sub = PageLayoutDTO(page=page_layout.page, blocks=blocks)
                    enriched = enrich_tables_with_vlm(
                        sub,
                        output_dir=output_dir,
                        file_prefix=file_prefix,
                        **kwargs,
                        inference_options={
                            **options,
                            "reasoning": reasoning,
                            "deployment": deployment,
                        },
                        max_workers=_int_config(
                            context, "max_workers", "vlm_max_workers", 1
                        ),
                        source_node_id=context.node_id,
                        usage_callback=usage_callback,
                        trace_metadata=trace_metadata,
                        timeout_seconds=remaining_timeout_seconds(
                            runtime, reserve_seconds=5.0
                        ),
                        table_output_format=_table_output_format_config(context),
                    )
                    _validate_enrichment(sub, enriched, "table_vlm")
                    result_blocks.update({b.block_id: b for b in enriched.blocks})
                ordered = [result_blocks[b.block_id] for b in page_layout.blocks]
                if record_block_failures(page_layout.page, ordered, "table_vlm"):
                    enriched_pages.append(
                        PageEnrichedDTO(
                            page=page_layout.page,
                            blocks=[],
                            source_node_id=context.node_id,
                        )
                    )
                    continue
                enriched_pages.append(
                    PageEnrichedDTO(
                        page=page_layout.page,
                        blocks=ordered,
                        source_node_id=context.node_id,
                    )
                )
            except Exception as exc:
                record_page_failure(page_layout.page, "table_vlm", exc)
                enriched_pages.append(
                    PageEnrichedDTO(
                        page=page_layout.page, blocks=[], source_node_id=context.node_id
                    )
                )
        value_out: PageEnrichedDTO | list[PageEnrichedDTO] = (
            enriched_pages[0] if single_input else enriched_pages
        )
        return NodeResult(
            value=value_out,
            metadata={
                "page_count": len(enriched_pages),
                "block_count": sum(len(page.blocks) for page in enriched_pages),
                "table_processed_count": sum(
                    1
                    for page in enriched_pages
                    for block in page.blocks
                    if block.metadata.get("table_vlm_processed") is True
                ),
                "table_error_count": sum(
                    1
                    for page in enriched_pages
                    for block in page.blocks
                    if block.metadata.get("table_vlm_error")
                ),
                "table_crop_saved_count": sum(
                    1
                    for page in enriched_pages
                    for block in page.blocks
                    if block.metadata.get("table_crop_saved") is True
                ),
                "table_output_format": table_output_format,
                "failed_pages": sum(
                    1
                    for page in page_layouts
                    if page.page.metadata.get("page_failures")
                ),
                "output_dir": output_dir,
            },
        )


def _validate_enrichment(
    expected: PageLayoutDTO, actual: PageEnrichedDTO, stage: str
) -> None:
    expected_ids = [block.block_id for block in expected.blocks]
    actual_ids = [block.block_id for block in actual.blocks]
    if actual_ids != expected_ids or len(actual_ids) != len(set(actual_ids)):
        raise ValueError(
            f"{stage} provider result block coverage does not match request"
        )


def _coerce_page_layouts(value: object) -> tuple[list[PageLayoutDTO], bool]:
    if isinstance(value, PageLayoutDTO):
        return [value], True
    if isinstance(value, list) and all(
        isinstance(item, PageLayoutDTO) for item in value
    ):
        return value, False
    raise TypeError(
        "table_vlm_caption_maker expects PageLayoutDTO or list[PageLayoutDTO]"
    )


def _runtime_config(context: NodeContext) -> dict[str, object]:
    value = context.metadata.get("runtime_config", {})
    return value if isinstance(value, dict) else {}


def _resolve_output_dir(context: NodeContext) -> str:
    configured = _optional_str(context.config.get("output_dir"))
    if configured:
        return configured
    runtime_outputs = _optional_str(_runtime_config(context).get("outputs"))
    return runtime_outputs or str(Path("outputs") / "table-vlm")


def _str_config(
    context: NodeContext, node_key: str, runtime_key: str, default: str
) -> str:
    node_value = _optional_str(context.config.get(node_key))
    if node_value:
        return node_value
    runtime_value = _optional_str(_runtime_config(context).get(runtime_key))
    return runtime_value or default


def _table_output_format_config(context: NodeContext) -> str:
    runtime_value = _optional_str(_runtime_config(context).get("table_output_format"))
    if runtime_value:
        return runtime_value
    return _str_config(
        context, "table_output_format", "table_output_format", "markdown"
    )


def _int_config(
    context: NodeContext, node_key: str, runtime_key: str, default: int
) -> int:
    value = context.config.get(
        node_key, _runtime_config(context).get(runtime_key, default)
    )
    try:
        int_value = int(value)
    except (TypeError, ValueError):
        return default
    return int_value if int_value > 0 else default


def _dict_config(
    context: NodeContext, node_key: str, runtime_key: str
) -> dict[str, object]:
    value = context.config.get(node_key, _runtime_config(context).get(runtime_key, {}))
    return value if isinstance(value, dict) else {}


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
