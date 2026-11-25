from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable, Sequence
from pathlib import Path

from PIL import Image

from core.adapters.models import build_chat_model_adapter
from core.domain.document.models import DocumentDTO
from core.domain.markdown.models import PageMarkdownDTO
from core.interfaces.adapters import ChatModelAdapter, ChatModelRequest
from core.prompts.vlm import build_task_prompt_vlm, get_schema_vlm
from core.services.markdown_document_assemble import assemble_merged_pages_document
from core.services.structured_markdown_restore import context_for_pages, restore_model_outputs
from core.services.page_failures import (
    failure_markdown,
    page_failures,
    record_page_failure,
)
from core.services.pdf_rendering import render_pdf_page


def merge_page_markdown_with_images_vlm(
    pages: list[PageMarkdownDTO],
    *,
    output_dir: str,
    document_id: str,
    prompt_key: str = "COMBINE_TEXT",
    schema_key: str = "COMBINE_TEXT",
    task_name: str = "COMBINE_TEXT",
    model_name: str,
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_version: str | None = None,
    project_id: str | None = None,
    api_type: str | None = None,
    extra_body: dict[str, object] | None = None,
    max_workers: int = 1,
    inference_options: dict | None = None,
    save_suffix: str = "",
    adapter: ChatModelAdapter | None = None,
    usage_callback: Callable[[dict[str, object]], None] | None = None,
    trace_metadata: dict[str, object] | None = None,
    timeout_seconds: float | None = None,
    skip_levels: Sequence[int] = (),
) -> DocumentDTO:
    ordered_pages = sorted(pages, key=lambda page: page.page.page_no)
    worker_count = max(1, min(max_workers, len(ordered_pages) or 1))
    model_adapter = adapter or build_chat_model_adapter(provider)

    merged: list[PageMarkdownDTO] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(
                merge_one_page_image,
                page_markdown,
                prompt_key=prompt_key,
                schema_key=schema_key,
                task_name=task_name,
                model_name=model_name,
                base_url=base_url,
                api_key=api_key,
                api_version=api_version,
                project_id=project_id,
                api_type=api_type,
                extra_body=extra_body,
                usage_callback=usage_callback,
                trace_metadata=trace_metadata,
                timeout_seconds=timeout_seconds,
                adapter=model_adapter,
                recovery_dir=_recovery_dir(output_dir),
                inference_options=inference_options,
                skip_levels=skip_levels,
            )
            for page_markdown in ordered_pages
        ]
        for future in as_completed(futures):
            merged.append(future.result())

    return assemble_merged_pages_document(
        merged,
        output_dir=output_dir,
        document_id=document_id,
        task_name=task_name,
        save_suffix=save_suffix,
    )


def merge_one_page_image(
    page: PageMarkdownDTO,
    *,
    prompt_key: str,
    schema_key: str,
    task_name: str,
    model_name: str,
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_version: str | None = None,
    project_id: str | None = None,
    api_type: str | None = None,
    extra_body: dict[str, object] | None = None,
    adapter: ChatModelAdapter | None = None,
    usage_callback: Callable[[dict[str, object]], None] | None = None,
    trace_metadata: dict[str, object] | None = None,
    timeout_seconds: float | None = None,
    recovery_dir: str | None = None,
    inference_options: dict | None = None,
    skip_levels: Sequence[int] = (),
) -> PageMarkdownDTO:
    inherited_failures = list(dict.fromkeys([*page.failures, *page_failures(page.page)]))
    context = context_for_pages(page)
    if inherited_failures or page.page.metadata.get("stage1_level") in skip_levels:
        body, cot = restore_model_outputs(_page_body(page.markdown), _page_body(page.cot_markdown) if page.cot_markdown is not None else "", page.structured_blocks, page=page.page, context=context, recovery_dir=recovery_dir)
        for failure in inherited_failures:
            record_page_failure(page.page, failure.stage, failure.reason)
            if failure.render_markdown() not in body:
                body = body.rstrip() + "\n\n" + failure.render_markdown()
        return PageMarkdownDTO(page=page.page, markdown=body, cot_markdown=cot if page.cot_markdown is not None else None, structured_blocks=list(page.structured_blocks), failures=inherited_failures, restore_context=context)
    try:
        model_adapter = adapter or build_chat_model_adapter(provider)
        output_text, cot_text = _merge_one_page(
            model_adapter,
            page,
            prompt_key,
            schema_key,
            task_name,
            model_name,
            base_url,
            api_key,
            api_version,
            project_id,
            api_type,
            extra_body or {},
            usage_callback,
            trace_metadata or {},
            timeout_seconds,
            recovery_dir,
            inference_options,
        )
    except Exception as exc:
        failure = record_page_failure(page.page, "text_image_vlm_merge", exc)
        body, cot = restore_model_outputs(_page_body(page.markdown), _page_body(page.cot_markdown) if page.cot_markdown is not None else "", page.structured_blocks, page=page.page, context=context, recovery_dir=recovery_dir)
        return PageMarkdownDTO(
            page=page.page, markdown=body.rstrip() + "\n\n" + failure_markdown([failure]),
            cot_markdown=cot if page.cot_markdown is not None else None,
            structured_blocks=list(page.structured_blocks), failures=page_failures(page.page), restore_context=context,
        )

    return PageMarkdownDTO(
        page=page.page,
        markdown=output_text,
        cot_markdown=cot_text,
        failures=page_failures(page.page),
        structured_blocks=list(page.structured_blocks),
        restore_context=context,
    )


def _merge_one_page(
    adapter: ChatModelAdapter,
    page_markdown: PageMarkdownDTO,
    prompt_key: str,
    schema_key: str,
    task_name: str,
    model_name: str,
    base_url: str | None,
    api_key: str | None,
    api_version: str | None,
    project_id: str | None,
    api_type: str | None,
    extra_body: dict[str, object],
    usage_callback: Callable[[dict[str, object]], None] | None,
    trace_metadata: dict[str, object],
    timeout_seconds: float | None,
    recovery_dir: str | None,
    inference_options: dict | None = None,
) -> tuple[str, str]:
    image = _render_page_image(page_markdown)
    result = adapter.invoke(
        ChatModelRequest(
            prompt="",
            task_prompt=build_task_prompt_vlm(
                prompt_key,
                {"text": _page_body(page_markdown.markdown)},
                (inference_options or {}).get("user_prompt"),
                policy=(inference_options or {}).get("prompt_policy"),
            ),
            **(inference_options or {}),
            model_name=model_name,
            images=[image],
            schema=get_schema_vlm(schema_key),
            base_url=base_url,
            api_key=api_key,
            api_version=api_version,
            project_id=project_id,
            api_type=api_type,
            extra_body=extra_body,
            usage_callback=usage_callback,
            trace_metadata={
                **trace_metadata,
                "page_no": page_markdown.page.page_no,
                "task_name": task_name,
            },
            timeout_seconds=timeout_seconds,
        )
    )
    from core.services.model_output import validate_model_output

    result = validate_model_output(result, get_schema_vlm(schema_key))
    structured_blocks = page_markdown.structured_blocks
    output_text, cot_text = restore_model_outputs(
        _normalize_output_text(result), _build_cot_text(result), structured_blocks,
        page=page_markdown.page, context=context_for_pages(page_markdown), recovery_dir=recovery_dir,
    )
    from core.services.markdown_safety import preserve_image_captions

    return preserve_image_captions(
        output_text, page_markdown.markdown
    ), preserve_image_captions(cot_text, page_markdown.markdown)


def _render_page_image(page_markdown: PageMarkdownDTO) -> Image.Image:
    artifact = page_markdown.page.pdf_artifact
    if artifact is None:
        raise ValueError(
            f"page has no pdf_artifact: {page_markdown.page.document_id}:{page_markdown.page.page_no}"
        )
    pdf_path = Path(artifact.path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"page PDF not found: {pdf_path}")

    return render_pdf_page(pdf_path, dpi=300)


def _page_body(markdown: str) -> str:
    first_newline = markdown.find("\n")
    if markdown.lstrip().startswith("@page:") and first_newline >= 0:
        return markdown[first_newline + 1 :]
    return markdown


def _normalize_output_text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, dict):
        output_text = content.get("output")
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        for key in ("text", "result", "content", "response", "answer"):
            fallback = content.get(key)
            if isinstance(fallback, str) and fallback.strip():
                return fallback
        return str(content)
    return str(content)


def _build_cot_text(content: object) -> str:
    if isinstance(content, dict):
        reasoning = content.get("reasoning", "")
        output = _normalize_output_text(content)
        if reasoning:
            return f"추론:\n{reasoning}\n\n출력:\n{output}"
        return output
    return str(content or "")


def _recovery_dir(output_dir: str) -> str:
    return str(Path(output_dir) / "_private" / "structured-recovery")
