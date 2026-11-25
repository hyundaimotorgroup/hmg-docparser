from __future__ import annotations

from core.adapters.triton.ocr import PaddleOCRRequest, PaddleTritonOCRAdapter
from core.adapters.local_http import infer_local_paddle_ocr
from core.engine.runtime.time_budget import remaining_timeout_seconds
from core.domain.layout.models import PageEnrichedDTO, PageLayoutDTO
from core.interfaces.node import Node, NodeContext, NodeResult
from core.services.text_ocr import apply_ocr_results_to_page_layout, load_block_crop_images
from core.services.page_failures import record_page_failure


class PaddleTritonOCRNode(Node):
    node_name = "paddle_triton_ocr"
    input_type = "page_layout_dto@v1"
    output_type = "page_enriched_dto@v1"
    is_page_parallel = True

    def run(self, context: NodeContext, value: object) -> NodeResult:
        page_layouts, single_input = _coerce_page_layouts(value)
        enriched_pages = [
            _run_page_ocr(context, page_layout)
            for page_layout in page_layouts
        ]
        value_out: PageEnrichedDTO | list[PageEnrichedDTO] = (
            enriched_pages[0] if single_input else enriched_pages
        )
        return NodeResult(
            value=value_out,
            metadata={
                "page_count": len(enriched_pages),
                "block_count": sum(len(page.blocks) for page in enriched_pages),
                "ocr_block_count": sum(
                    1
                    for page in enriched_pages
                    for block in page.blocks
                    if block.metadata.get("ocr_line_count") is not None
                ),
            },
        )


def _run_page_ocr(context: NodeContext, page_layout: PageLayoutDTO) -> PageEnrichedDTO:
    target_blocks, images = load_block_crop_images(page_layout)
    if not images:
        return PageEnrichedDTO(
            page=page_layout.page,
            blocks=list(page_layout.blocks),
            source_node_id=context.node_id,
        )

    try:
        transport = _str_config(context, "transport", "ocr_transport", "triton")
        if transport == "fastapi":
            ocr_results = infer_local_paddle_ocr(
                images,
                _required_str_config(context, "server_url", "ocr_triton_url"),
                padding=_int_config(context, "padding", "ocr_triton_padding", 75),
                timeout_seconds=remaining_timeout_seconds(_runtime_config(context), reserve_seconds=5.0),
                cancellation_check=_cancellation_check(context),
            )
        elif transport == "triton":
            request = PaddleOCRRequest(
                images=images,
                server_url=_required_str_config(context, "server_url", "ocr_triton_url"),
                model_name=_str_config(context, "model_name", "ocr_triton_model_name", "paddle"),
                padding=_int_config(context, "padding", "ocr_triton_padding", 75),
                ssl=_bool_config(context, "ssl", "ocr_triton_ssl", False),
                token=_optional_str(context.config.get("token"))
                or _optional_str(_runtime_config(context).get("ocr_triton_token")),
                concurrency=_int_config(context, "concurrency", "ocr_triton_concurrency", 4),
                timeout_seconds=remaining_timeout_seconds(_runtime_config(context), reserve_seconds=5.0),
                cancellation_check=_cancellation_check(context),
            )
            ocr_results = PaddleTritonOCRAdapter().invoke(request)
        else:
            raise ValueError(f"Unsupported OCR transport: {transport}")
        return apply_ocr_results_to_page_layout(
            page_layout,
            target_blocks=target_blocks,
            ocr_results=ocr_results,
            source_node_id=context.node_id,
            min_score=_float_config(context, "min_score", 0.9),
        )
    except Exception as exc:
        record_page_failure(page_layout.page, "ocr", exc)
        return PageEnrichedDTO(
            page=page_layout.page,
            blocks=list(page_layout.blocks),
            source_node_id=context.node_id,
        )
    finally:
        for image in images:
            image.close()


def _coerce_page_layouts(value: object) -> tuple[list[PageLayoutDTO], bool]:
    if isinstance(value, PageLayoutDTO):
        return [value], True
    if isinstance(value, list) and all(isinstance(item, PageLayoutDTO) for item in value):
        return value, False
    raise TypeError("paddle_triton_ocr expects PageLayoutDTO or list[PageLayoutDTO]")


def _runtime_config(context: NodeContext) -> dict[str, object]:
    value = context.metadata.get("runtime_config", {})
    return value if isinstance(value, dict) else {}


def _cancellation_check(context: NodeContext):
    value = context.metadata.get("cancellation_check")
    return value if callable(value) else None


def _str_config(context: NodeContext, node_key: str, runtime_key: str, default: str) -> str:
    node_value = _optional_str(context.config.get(node_key))
    if node_value:
        return node_value
    runtime_value = _optional_str(_runtime_config(context).get(runtime_key))
    return runtime_value or default


def _required_str_config(context: NodeContext, node_key: str, runtime_key: str) -> str:
    value = _optional_str(context.config.get(node_key))
    if value:
        return value
    runtime_value = _optional_str(_runtime_config(context).get(runtime_key))
    if runtime_value:
        return runtime_value
    raise ValueError(f"{context.node_id} requires '{node_key}' or runtime '{runtime_key}'")


def _int_config(context: NodeContext, node_key: str, runtime_key: str, default: int) -> int:
    value = context.config.get(node_key, _runtime_config(context).get(runtime_key, default))
    try:
        int_value = int(value)
    except (TypeError, ValueError):
        return default
    return int_value if int_value > 0 else default


def _float_config(context: NodeContext, key: str, default: float) -> float:
    value = context.config.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool_config(context: NodeContext, node_key: str, runtime_key: str, default: bool) -> bool:
    value = context.config.get(node_key, _runtime_config(context).get(runtime_key, default))
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
