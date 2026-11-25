from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PIL import Image

from core.adapters.dolphin_vllm.dolphin_vllm import DolphinVLLMLayoutAdapter, DolphinVLLMLayoutRequest
from core.domain.document.models import PageDTO
from core.domain.layout.models import PageLayoutDTO
from core.interfaces.node import Node, NodeContext, NodeResult
from core.engine.runtime.time_budget import remaining_timeout_seconds
from core.services.dolphin_layout import (
    DEFAULT_DOLPHIN_V2_TARGET_SIZE,
    dolphin_vllm_layout_text_to_page_layout,
    render_page_pdf_for_dolphin,
)
from core.services.page_failures import record_page_failure


class DolphinVLLMLayoutParserNode(Node):
    node_name = "dolphin_vllm_layout_parser"
    input_type = "page_dto@v1"
    output_type = "page_layout_dto@v1"
    is_page_parallel = True

    def run(self, context: NodeContext, value: object) -> NodeResult:
        pages, single_input = _coerce_pages(value)
        target_size = _int_config(context, "target_size", "dolphin_target_size", DEFAULT_DOLPHIN_V2_TARGET_SIZE)
        crop_output_dir = _resolve_crop_output_dir(context)
        skip_levels: list[int] = list(context.config.get("skip_levels", []))

        # stage1 라우터가 지정한 skip_levels 페이지는 레이아웃 호출 없이 빈 레이아웃으로 통과
        active_pages = [p for p in pages if not (skip_levels and p.metadata.get("stage1_level", 0) in skip_levels)]

        rendered: list[tuple[PageDTO, Image.Image]] = []
        active_layouts: list[PageLayoutDTO] = []
        try:
            for page in active_pages:
                try:
                    rendered.append((page, render_page_pdf_for_dolphin(page, target_size=target_size)))
                except Exception as exc:
                    record_page_failure(page, "dolphin_layout", exc)
            layout_texts = _invoke(context, [image for _, image in rendered])
            if len(layout_texts) != len(rendered):
                raise RuntimeError(f"Dolphin vLLM layout output count mismatch ({len(layout_texts)} != {len(rendered)})")
            for (page, image), layout_text in zip(rendered, layout_texts):
                try:
                    active_layouts.append(dolphin_vllm_layout_text_to_page_layout(
                        page=page, page_image=image, layout_text=layout_text, crop_output_dir=crop_output_dir,
                    ))
                except Exception as exc:
                    record_page_failure(page, "dolphin_layout", exc)
        except Exception as exc:
            for page, _ in rendered:
                record_page_failure(page, "dolphin_layout", exc)
        finally:
            for _, image in rendered:
                image.close()
        # skip된 페이지는 빈 레이아웃으로 복원, 원래 순서 유지
        layout_by_page = {(pl.page.document_id, pl.page.page_no): pl for pl in active_layouts}
        page_layouts = [
            layout_by_page.get((page.document_id, page.page_no), PageLayoutDTO(page=page, blocks=[]))
            for page in pages
        ]
        value_out: PageLayoutDTO | list[PageLayoutDTO] = page_layouts[0] if single_input else page_layouts
        return NodeResult(
            value=value_out,
            metadata={
                "page_count": len(page_layouts),
                "block_count": sum(len(p.blocks) for p in page_layouts),
                "crop_output_dir": crop_output_dir,
                "failed_pages": sum(1 for page in pages if page.metadata.get("page_failures")),
            },
        )


def _coerce_pages(value: object) -> tuple[list[PageDTO], bool]:
    if isinstance(value, PageDTO):
        return [value], True
    if isinstance(value, list) and all(isinstance(item, PageDTO) for item in value):
        return value, False
    raise TypeError("dolphin_vllm_layout_parser expects PageDTO or list[PageDTO]")


def _invoke(context: NodeContext, images: Sequence[Image.Image]) -> list[str]:
    runtime_config = _runtime_config(context)
    request = DolphinVLLMLayoutRequest(
        images=images,
        server_url=_required_str_config(context, "server_url", "dolphin_triton_url"),
        model_name=_str_config(context, "model_name", "dolphin_triton_model_name", "dolphinv2"),
        prompt=_str_config(context, "prompt", "dolphin_prompt", "Parse the reading order of this document."),
        ssl=_bool_config(context, "ssl", "dolphin_triton_ssl", False),
        token=_optional_str(context.config.get("token")) or _optional_str(runtime_config.get("dolphin_triton_token")),
        timeout_seconds=remaining_timeout_seconds(runtime_config, reserve_seconds=5.0),
    )
    return DolphinVLLMLayoutAdapter().invoke(request)


def _runtime_config(context: NodeContext) -> dict[str, object]:
    value = context.metadata.get("runtime_config", {})
    return value if isinstance(value, dict) else {}


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


def _resolve_crop_output_dir(context: NodeContext) -> str | None:
    configured = _optional_str(context.config.get("crop_output_dir"))
    if configured:
        return configured
    runtime_config = _runtime_config(context)
    outputs = _optional_str(runtime_config.get("outputs"))
    if outputs:
        return str(Path(outputs) / "_layout_crops")
    return None
