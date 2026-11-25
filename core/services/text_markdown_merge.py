from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
import re
from pathlib import Path

from core.adapters.models import build_chat_model_adapter
from core.domain.document.models import DocumentDTO
from core.domain.markdown.models import PageMarkdownDTO, StructuredMarkdownBlockDTO
from core.interfaces.adapters import ChatModelAdapter, ChatModelRequest
from core.prompts.llm import LLM_TASK_LIST, build_task_prompt_llm, get_schema_llm
from core.services.markdown_document_assemble import assemble_merged_pages_document
from core.services.structured_markdown_restore import context_for_pages, restore_model_outputs
from core.services.page_failures import (
    failure_markdown,
    page_failures,
    record_page_failure,
)


def merge_page_markdown_sets_with_llm(
    primary_pages: list[PageMarkdownDTO],
    secondary_pages: list[PageMarkdownDTO],
    *,
    output_dir: str,
    document_id: str,
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
    save_suffix: str = "_OCR",
    adapter: ChatModelAdapter | None = None,
    usage_callback: Callable[[dict[str, object]], None] | None = None,
    trace_metadata: dict[str, object] | None = None,
    timeout_seconds: float | None = None,
) -> DocumentDTO:
    primary_by_page = _page_map(primary_pages)
    secondary_by_page = _page_map(secondary_pages)
    if set(primary_by_page) != set(secondary_by_page):
        raise ValueError(
            "page markdown sets must have identical page numbers: "
            f"{sorted(primary_by_page)} != {sorted(secondary_by_page)}"
        )

    page_numbers = sorted(primary_by_page)
    worker_count = max(1, min(max_workers, len(page_numbers) or 1))
    model_adapter = adapter or build_chat_model_adapter(provider)

    merged: list[PageMarkdownDTO] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(
                merge_one_page_markdown,
                primary_by_page[page_no],
                secondary_by_page[page_no],
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
            )
            for page_no in page_numbers
        ]
        for future in as_completed(futures):
            merged.append(future.result())

    return assemble_merged_pages_document(
        merged,
        output_dir=output_dir,
        document_id=document_id,
        task_name=LLM_TASK_LIST[0],
        save_suffix=save_suffix,
    )


def merge_one_page_markdown(
    primary_page: PageMarkdownDTO,
    secondary_page: PageMarkdownDTO,
    *,
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
) -> PageMarkdownDTO:
    inherited_failures = list(
        dict.fromkeys(
            [
                *primary_page.failures,
                *secondary_page.failures,
                *page_failures(primary_page.page),
                *page_failures(secondary_page.page),
            ]
        )
    )
    blocks = _merge_structured_blocks(primary_page, secondary_page)
    context = context_for_pages(primary_page, secondary_page)
    for failure in inherited_failures:
        record_page_failure(primary_page.page, failure.stage, failure.reason)
    if inherited_failures or secondary_page.page.metadata.get("stage1_level") == 1:
        source = secondary_page if secondary_page.markdown.strip() else primary_page
        body_input = _page_body(source.markdown)
        if inherited_failures:
            other = _page_body(primary_page.markdown)
            if other.strip() and other not in body_input:
                body_input = other + "\n\n" + body_input
        body, cot = restore_model_outputs(body_input, _page_body(source.cot_markdown or source.markdown), blocks, page=primary_page.page, context=context, recovery_dir=recovery_dir)
        for failure in inherited_failures:
            if failure.render_markdown() not in body:
                body = body.rstrip() + "\n\n" + failure.render_markdown()
        return PageMarkdownDTO(page=primary_page.page, markdown=body, cot_markdown=cot, structured_blocks=blocks, failures=page_failures(primary_page.page), restore_context=context)

    try:
        model_adapter = adapter or build_chat_model_adapter(provider)
        output_text, cot_text = _merge_one_page(
            model_adapter,
            LLM_TASK_LIST[0],
            primary_page,
            secondary_page,
            model_name,
            base_url,
            api_key,
            api_version,
            project_id,
            api_type,
            extra_body or {},
            usage_callback,
            trace_metadata or {},
            int(primary_page.page.page_no),
            timeout_seconds,
            recovery_dir,
            inference_options,
        )
    except Exception as exc:
        failure = record_page_failure(primary_page.page, "text_markdown_merge", exc)
        body, cot = restore_model_outputs(_page_body(primary_page.markdown) + "\n\n" + _page_body(secondary_page.markdown), "", blocks, page=primary_page.page, context=context, recovery_dir=recovery_dir)
        return PageMarkdownDTO(
            page=primary_page.page,
            markdown=body + "\n\n" + failure_markdown([failure]),
            structured_blocks=blocks,
            restore_context=context,
            failures=[*page_failures(primary_page.page)],
        )

    return PageMarkdownDTO(
        page=primary_page.page,
        markdown=output_text,
        cot_markdown=cot_text,
        failures=page_failures(primary_page.page),
        structured_blocks=blocks,
        restore_context=context,
    )


def _merge_one_page(
    adapter: ChatModelAdapter,
    task_name: str,
    primary_page: PageMarkdownDTO,
    secondary_page: PageMarkdownDTO,
    model_name: str,
    base_url: str | None,
    api_key: str | None,
    api_version: str | None,
    project_id: str | None,
    api_type: str | None,
    extra_body: dict[str, object],
    usage_callback: Callable[[dict[str, object]], None] | None,
    trace_metadata: dict[str, object],
    page_no: int,
    timeout_seconds: float | None,
    recovery_dir: str | None,
    inference_options: dict | None = None,
) -> tuple[str, str]:
    structured_blocks = _merge_structured_blocks(primary_page, secondary_page)
    result = adapter.invoke(
        ChatModelRequest(
            prompt="",
            **(inference_options or {}),
            task_prompt=build_task_prompt_llm(
                task_name,
                {
                    "text1": _page_body(primary_page.markdown),
                    "text2": _page_body(secondary_page.markdown),
                },
                (inference_options or {}).get("user_prompt"),
                policy=(inference_options or {}).get("prompt_policy"),
            ),
            model_name=model_name,
            schema=get_schema_llm(task_name),
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
                "task_name": task_name,
            },
            timeout_seconds=timeout_seconds,
        )
    )
    from core.services.model_output import validate_model_output

    result = validate_model_output(result, get_schema_llm(task_name))
    output_text, cot_text = restore_model_outputs(
        _normalize_output_text(result), _build_cot_text(result), structured_blocks,
        page=primary_page.page, context=context_for_pages(primary_page, secondary_page), recovery_dir=recovery_dir,
    )
    output_text = _preserve_metadata_lines(output_text, secondary_page.markdown)
    cot_text = _preserve_metadata_lines(cot_text, secondary_page.markdown)
    from core.services.markdown_safety import preserve_image_captions

    source = primary_page.markdown + "\n" + secondary_page.markdown
    return preserve_image_captions(output_text, source), preserve_image_captions(
        cot_text, source
    )


def _page_map(pages: list[PageMarkdownDTO]) -> dict[int, PageMarkdownDTO]:
    result: dict[int, PageMarkdownDTO] = {}
    for page in pages:
        page_no = int(page.page.page_no)
        if page_no in result:
            raise ValueError(f"duplicated page markdown: {page_no}")
        result[page_no] = page
    return result


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


def _merge_structured_blocks(
    primary_page: PageMarkdownDTO,
    secondary_page: PageMarkdownDTO,
) -> list[StructuredMarkdownBlockDTO]:
    # Preserve duplicate identities so restoration can diagnose conflicts.
    return [*primary_page.structured_blocks, *secondary_page.structured_blocks]


def _preserve_metadata_lines(text: str, source_markdown: str) -> str:
    if not text or not source_markdown:
        return text

    preserved = text
    for label in ("Doc Number", "Doc Title", "Owner", "Ver. Date", "Ver. Level"):
        source_line = _find_metadata_line(source_markdown, label)
        if not source_line:
            continue

        pattern = re.compile(rf"(?m)^{re.escape(label)}\s*:.*$")
        if pattern.search(preserved):
            preserved = pattern.sub(source_line, preserved)
    return preserved


def _find_metadata_line(text: str, label: str) -> str | None:
    pattern = re.compile(rf"(?m)^{re.escape(label)}\s*:.*$")
    match = pattern.search(text)
    if match is None:
        return None
    return match.group(0).strip()


def _recovery_dir(output_dir: str) -> str:
    return str(Path(output_dir) / "_private" / "structured-recovery")
