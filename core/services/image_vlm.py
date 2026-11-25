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
    VLM_CAPTION_END_TAG,
    VLM_CAPTION_START_TAG,
    sanitize_filename,
    shorten_filename,
)
from core.prompts.vlm import build_task_prompt_vlm, get_schema_vlm


def enrich_images_with_vlm(
    page_layout: PageLayoutDTO,
    *,
    output_dir: str,
    file_prefix: str,
    model_name: str,
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_version: str | None = None,
    project_id: str | None = None,
    api_type: str | None = None,
    extra_body: dict[str, object] | None = None,
    max_workers: int = 1,
    use_vlm_parse: bool = True,
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
                lambda block: _process_image_block(
                    block,
                    page_no=page_layout.page.page_no,
                    output_dir=output_dir,
                    file_prefix=file_prefix,
                    model_name=model_name,
                    provider=provider,
                    base_url=base_url,
                    api_key=api_key,
                    api_version=api_version,
                    project_id=project_id,
                    api_type=api_type,
                    extra_body=extra_body or {},
                    use_vlm_parse=use_vlm_parse,
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
            _apply_image_result(block, result_by_block_id.get(block.block_id))
            for block in page_layout.blocks
        ],
        source_node_id=source_node_id,
    )


def _process_image_block(
    block: LayoutBlockDTO,
    *,
    page_no: int,
    output_dir: str,
    file_prefix: str,
    model_name: str,
    provider: str | None,
    base_url: str | None,
    api_key: str | None,
    api_version: str | None,
    project_id: str | None,
    api_type: str | None,
    extra_body: dict[str, object],
    use_vlm_parse: bool,
    usage_callback: Callable[[dict[str, object]], None] | None,
    trace_metadata: dict[str, object],
    timeout_seconds: float | None,
    inference_options: dict | None = None,
) -> dict[str, object]:
    if block.crop_artifact is None:
        return {"markdown": "", "error": "missing crop_artifact"}

    image: Image.Image | None = None
    try:
        with Image.open(block.crop_artifact.path) as opened:
            opened.load()
            image = opened.copy()
        vlm_result: dict[str, object] = {}
        if use_vlm_parse:
            result = build_chat_model_adapter(provider).invoke(
                ChatModelRequest(
                    prompt="",
                    task_prompt=build_task_prompt_vlm(
                        "IMAGE_PARSE",
                        user_prompt=(inference_options or {}).get("user_prompt"),
                        policy=(inference_options or {}).get("prompt_policy"),
                    ),
                    **(inference_options or {}),
                    model_name=model_name,
                    images=[image],
                    schema=get_schema_vlm("IMAGE_PARSE"),
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
                        "task_name": "IMAGE_PARSE",
                    },
                    timeout_seconds=timeout_seconds,
                )
            )
            from core.services.model_output import validate_model_output

            result = validate_model_output(result, get_schema_vlm("IMAGE_PARSE"))
            if not isinstance(result, dict):
                raise ValueError("image VLM provider returned a non-object response")
            if not str(result.get("output", "")).strip():
                raise ValueError("image VLM provider returned an empty output")
            vlm_result = result

        title = str(vlm_result.get("title", "") or "").strip()
        filename = _build_image_filename(
            file_prefix=file_prefix,
            page_no=page_no,
            block=block,
            title=title,
        )
        image_dir = Path(output_dir) / "imgs"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / filename
        image.save(image_path)

        caption_text = (
            " ".join(title.replace("[", "").replace("]", "").split())
            if title
            else "img"
        )
        markdown = f"![{caption_text}](imgs/{filename})"
        if use_vlm_parse:
            markdown += f"\n{VLM_CAPTION_START_TAG}\n{vlm_result['output']}\n{VLM_CAPTION_END_TAG}"
        return {
            "markdown": markdown,
            "artifact": ArtifactRef(
                path=str(image_path),
                media_type="image/png",
                description="image vlm crop",
            ),
            "title": title,
            "used_vlm": use_vlm_parse,
        }
    except Exception as exc:
        return {
            "markdown": "",
            "error": "model block processing failed (" + type(exc).__name__ + ")",
            "used_vlm": use_vlm_parse,
        }
    finally:
        if image is not None:
            image.close()


def _apply_image_result(
    block: LayoutBlockDTO,
    result: dict[str, object] | None,
) -> LayoutBlockDTO:
    if result is None:
        return block

    metadata = dict(block.metadata)
    metadata["image_vlm_processed"] = True
    metadata["image_vlm_used"] = bool(result.get("used_vlm"))
    if result.get("title"):
        metadata["image_vlm_title"] = result["title"]
    if result.get("error"):
        metadata["image_vlm_error"] = result["error"]

    artifact = result.get("artifact")
    return replace(
        block,
        text=str(result.get("markdown", "")),
        title=str(result.get("title", "")) or block.title,
        crop_artifact=artifact
        if isinstance(artifact, ArtifactRef)
        else block.crop_artifact,
        metadata=metadata,
    )


def _build_image_filename(
    *,
    file_prefix: str,
    page_no: int,
    block: LayoutBlockDTO,
    title: str,
) -> str:
    safe_prefix = sanitize_filename(file_prefix)
    reading_order = block.reading_order if block.reading_order is not None else 0
    legacy_page_idx = max(int(page_no) - 1, 0)
    item_idx = _safe_int(block.metadata.get("layout_item_idx"), reading_order)
    base = f"{safe_prefix}_{legacy_page_idx}_{item_idx}_{reading_order}"
    if title:
        base = f"{base}_{sanitize_filename(title)}"
    return shorten_filename(f"{base}.png")


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
