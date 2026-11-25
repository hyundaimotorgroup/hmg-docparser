from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PIL import Image

from core.adapters.models import build_chat_model_adapter
from core.domain.artifacts import ArtifactRef
from core.domain.layout.models import LayoutBlockDTO, PageEnrichedDTO, PageLayoutDTO
from core.interfaces.adapters import ChatModelRequest
from core.prompts.utils import (
    normalize_escaped_html,
    sanitize_filename,
    shorten_filename,
)
from core.services.structured_tables import (
    parse_table_output_format,
    render_validated_table,
    sanitize_table_html,
)
from core.prompts.vlm import build_task_prompt_vlm, get_schema_vlm


def enrich_tables_with_vlm(
    page_layout: PageLayoutDTO,
    *,
    output_dir: str,
    file_prefix: str,
    model_name: str,
    table_output_format: str = "markdown",
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_version: str | None = None,
    project_id: str | None = None,
    api_type: str | None = None,
    extra_body: dict[str, object] | None = None,
    max_workers: int = 1,
    source_node_id: str | None = None,
    usage_callback: Callable[[dict[str, object]], None] | None = None,
    trace_metadata: dict[str, object] | None = None,
    timeout_seconds: float | None = None,
    inference_options: dict | None = None,
) -> PageEnrichedDTO:
    target_blocks = [
        block for block in page_layout.blocks if block.crop_artifact is not None
    ]
    if not target_blocks:
        return PageEnrichedDTO(
            page=page_layout.page,
            blocks=list(page_layout.blocks),
            source_node_id=source_node_id,
        )

    worker_count = max(1, min(max_workers, len(target_blocks)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(
            executor.map(
                lambda block: _parse_table_block(
                    block,
                    page_no=page_layout.page.page_no,
                    output_dir=output_dir,
                    file_prefix=file_prefix,
                    model_name=model_name,
                    table_output_format=table_output_format,
                    provider=provider,
                    base_url=base_url,
                    api_key=api_key,
                    api_version=api_version,
                    project_id=project_id,
                    api_type=api_type,
                    extra_body=extra_body or {},
                    usage_callback=usage_callback,
                    trace_metadata=trace_metadata or {},
                    timeout_seconds=timeout_seconds,
                    inference_options=inference_options,
                ),
                target_blocks,
            )
        )

    result_by_block_id = {
        block.block_id: result for block, result in zip(target_blocks, results)
    }
    return PageEnrichedDTO(
        page=page_layout.page,
        blocks=[
            _apply_table_result(block, result_by_block_id.get(block.block_id))
            for block in page_layout.blocks
        ],
        source_node_id=source_node_id,
    )


def _parse_table_block(
    block: LayoutBlockDTO,
    *,
    page_no: int,
    output_dir: str,
    file_prefix: str,
    model_name: str,
    table_output_format: str,
    provider: str | None,
    base_url: str | None,
    api_key: str | None,
    api_version: str | None,
    project_id: str | None,
    api_type: str | None,
    extra_body: dict[str, object],
    usage_callback: Callable[[dict[str, object]], None] | None,
    trace_metadata: dict[str, object],
    timeout_seconds: float | None,
    inference_options: dict | None = None,
) -> dict[str, object]:
    if block.crop_artifact is None:
        return {"rendered_text": "", "html_raw": "", "error": "missing crop_artifact"}

    image: Image.Image | None = None
    try:
        with Image.open(block.crop_artifact.path) as opened:
            opened.load()
            image = opened.copy()
        crop_result = _save_table_crop_image(
            image=image,
            page_no=page_no,
            block=block,
            output_dir=output_dir,
            file_prefix=file_prefix,
        )
        result = build_chat_model_adapter(provider).invoke(
            ChatModelRequest(
                prompt="",
                task_prompt=build_task_prompt_vlm(
                    "TABLE_PARSE",
                    user_prompt=(inference_options or {}).get("user_prompt"),
                    policy=(inference_options or {}).get("prompt_policy"),
                ),
                **(inference_options or {}),
                model_name=model_name,
                images=[image],
                schema=get_schema_vlm("TABLE_PARSE"),
                base_url=base_url,
                api_key=api_key,
                api_version=api_version,
                project_id=project_id,
                api_type=api_type,
                extra_body=extra_body,
                usage_callback=usage_callback,
                trace_metadata={
                    **trace_metadata,
                    "page_no": page_no,
                    "block_id": block.block_id,
                    "task_name": "TABLE_PARSE",
                },
                timeout_seconds=timeout_seconds,
            )
        )
        from core.services.model_output import validate_model_output

        result = validate_model_output(result, get_schema_vlm("TABLE_PARSE"))
        if not isinstance(result, dict):
            raise ValueError("table VLM provider returned a non-object response")
        table_html = str(result.get("output", ""))
        reasoning = result.get("reasoning", "")
        if not table_html.strip():
            raise ValueError("table VLM provider returned an empty output")

        table_html = sanitize_table_html(_strip_table_code_fence(table_html))
        rendered_text = render_validated_table(table_html, table_output_format)
        return {
            "rendered_text": rendered_text,
            "render_format": parse_table_output_format(table_output_format).value,
            "html_raw": table_html,
            "reasoning": reasoning,
            **crop_result,
        }
    except Exception as exc:
        return {
            "rendered_text": "",
            "render_format": parse_table_output_format(table_output_format).value,
            "html_raw": "",
            "error": "model block processing failed (" + type(exc).__name__ + ")",
        }
    finally:
        if image is not None:
            image.close()


def _apply_table_result(
    block: LayoutBlockDTO,
    result: dict[str, object] | None,
) -> LayoutBlockDTO:
    if result is None:
        return block

    metadata = dict(block.metadata)
    metadata["table_vlm_processed"] = True
    if result.get("error"):
        metadata["table_vlm_error"] = result["error"]
    if result.get("reasoning"):
        metadata["table_vlm_has_reasoning"] = True
    if result.get("crop_saved"):
        metadata["table_crop_saved"] = True
    if result.get("crop_markdown_path"):
        metadata["table_crop_markdown_path"] = result["crop_markdown_path"]
    if result.get("render_format"):
        metadata["table_render_format"] = result["render_format"]

    artifact = result.get("crop_artifact")
    return replace(
        block,
        text=str(result.get("rendered_text", "")),
        table_html_raw=str(result.get("html_raw", "")),
        crop_artifact=artifact
        if isinstance(artifact, ArtifactRef)
        else block.crop_artifact,
        metadata=metadata,
    )


def normalize_table_output_format(value: str | None) -> str:
    return parse_table_output_format(value).value


def render_table_html(table_html: str, table_output_format: str) -> str:
    return render_validated_table(table_html, table_output_format)


def _strip_table_code_fence(value: str) -> str:
    cleaned = (
        value.replace("```HTML", "").replace("```html", "").replace("```", "").strip()
    )
    return normalize_escaped_html(cleaned)


def _save_table_crop_image(
    *,
    image: Image.Image,
    page_no: int,
    block: LayoutBlockDTO,
    output_dir: str,
    file_prefix: str,
) -> dict[str, object]:
    filename = _build_table_crop_filename(
        file_prefix=file_prefix,
        page_no=page_no,
        block=block,
    )
    image_dir = Path(output_dir) / "table_imgs"
    image_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / filename
    image.save(image_path)
    return {
        "crop_saved": True,
        "crop_markdown_path": f"table_imgs/{filename}",
        "crop_artifact": ArtifactRef(
            path=str(image_path),
            media_type="image/png",
            description="table vlm crop",
        ),
    }


def _build_table_crop_filename(
    *,
    file_prefix: str,
    page_no: int,
    block: LayoutBlockDTO,
) -> str:
    safe_prefix = sanitize_filename(file_prefix) or "document"
    reading_order = block.reading_order if block.reading_order is not None else 0
    legacy_page_idx = max(int(page_no) - 1, 0)
    item_idx = _safe_int(block.metadata.get("layout_item_idx"), reading_order)
    return shorten_filename(
        f"{safe_prefix}_table_{legacy_page_idx}_{item_idx}_{reading_order}.png"
    )


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
