from __future__ import annotations

import re
import json
from pathlib import Path

from core.domain.artifacts import ArtifactRef
from core.domain.document.models import DocumentDTO, DocumentMetadataDTO
from core.domain.layout.models import LayoutBlockDTO, PageEnrichedDTO
from core.domain.markdown.models import (
    PageMarkdownDTO,
    StructuredMarkdownBlockDTO,
    TableOutputFormat,
    StructuredRestoreContext,
)
from core.domain.markdown.protocol import structured_placeholder, TABLE_REFERENCE_RE, PROTOCOL_VERSION
from core.prompts.utils import html_table_to_markdown
from core.prompts.utils import VLM_CAPTION_END_TAG, VLM_CAPTION_START_TAG
from core.services.page_failures import failure_markdown, page_failures, record_page_failure
from core.services.markdown_safety import sanitize_markdown_image_urls
from core.services.structured_tables import (
    parse_table_output_format,
    render_validated_table,
    sanitize_table_html,
)


def format_page_enrichment_as_markdown(
    page: PageEnrichedDTO,
    *,
    include_table_crop_images: bool = False,
    restore_tables: bool = False,
    include_page_marker: bool = True,
) -> PageMarkdownDTO:
    failures = page_failures(page.page)
    structured_blocks = build_structured_markdown_blocks(
        page,
        include_table_crop_images=include_table_crop_images,
        stable_table_ids=restore_tables,
    )
    failures = page_failures(page.page)
    raw_markdown = _blocks_to_markdown(
        page.blocks,
        structured_blocks=structured_blocks,
        include_table_crop_images=include_table_crop_images,
        restore_tables=restore_tables,
    )
    markdown = sanitize_markdown_image_urls(process_vlm_caption_blocks(raw_markdown))
    cot_markdown = raw_markdown + _table_html_debug_block(page) + _block_context_debug(page)
    prefix = f"@page:{page.page.page_no}\n\n" if include_page_marker else ""
    supplied = tuple(b.placeholder for b in structured_blocks if b.placeholder.startswith("[[TABLE_BLOCK:"))
    # Only explicit host/native provenance grants a literal exemption. Model
    # captions and whole-page output cannot exempt themselves using a code fence.
    literals = tuple(m.group() for b in page.blocks if b.metadata.get("native_text_direct") or b.metadata.get("literal_reference_source") for m in TABLE_REFERENCE_RE.finditer(b.text or ""))
    context = StructuredRestoreContext(supplied, "incomplete" if failures else "complete", literals)
    page.page.metadata["structured_markdown_protocol"] = PROTOCOL_VERSION
    page.page.metadata["structured_source_references"] = list(supplied)
    page.page.metadata["structured_registry_status"] = context.registry_status
    page.page.metadata["structured_literal_references"] = list(literals)
    if failures:
        markdown = "\n\n".join(filter(None, [markdown, failure_markdown(failures)]))
    return PageMarkdownDTO(
        page=page.page,
        markdown=(prefix + markdown).rstrip(),
        cot_markdown=(prefix + cot_markdown).rstrip(),
        structured_blocks=structured_blocks,
        failures=failures,
        restore_context=context,
    )


def save_page_markdowns_as_document(
    pages: list[PageMarkdownDTO],
    *,
    output_dir: str,
    document_id: str,
    task_name: str = "LAYOUT",
    save_suffix: str = "",
    save_debug_artifacts: bool = False,
) -> DocumentDTO:
    ordered_pages = sorted(pages, key=lambda item: item.page.page_no)
    result_text = sanitize_markdown_image_urls(
        "\n".join(page.markdown for page in ordered_pages).strip()
    )
    has_cot = any(page.cot_markdown is not None for page in ordered_pages)
    result_text_cot = "\n".join(
        page.cot_markdown or page.markdown for page in ordered_pages
    ).strip()
    result_text_wo_cot = process_vlm_caption_blocks(result_text)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    markdown_path = output_path / f"{document_id}_{task_name}{save_suffix}.md"
    markdown_path.write_text(result_text_wo_cot, encoding="utf-8")

    artifacts = [
        ArtifactRef(
            path=str(markdown_path),
            media_type="text/markdown",
            description="layout markdown",
        ),
    ]
    if save_debug_artifacts and has_cot:
        private_dir = output_path / "_private"
        private_dir.mkdir(parents=True, exist_ok=True)
        cot_path = private_dir / f"{document_id}_{task_name}_debug{save_suffix}.md"
        cot_path.write_text(result_text_cot, encoding="utf-8")
        artifacts.append(
            ArtifactRef(
                path=str(cot_path),
                media_type="text/markdown",
                description="layout markdown debug",
            )
        )

    return DocumentDTO(
        document_id=document_id,
        metadata=DocumentMetadataDTO(
            source_path=str(markdown_path),
            file_name=markdown_path.name,
            mime_type="text/markdown",
            page_count=len(ordered_pages),
        ),
        pages=[page.page for page in ordered_pages],
        markdown=result_text_wo_cot,
        artifacts=artifacts,
    )


def process_vlm_caption_blocks(text: str) -> str:
    if not text:
        return text

    patterns = (
        re.compile(
            r"\n?```\s*\n<VLM image caption>(.*?)</VLM image caption>\s*```",
            re.DOTALL,
        ),
        re.compile(
            rf"{re.escape(VLM_CAPTION_START_TAG)}\s*\n?(.*?){re.escape(VLM_CAPTION_END_TAG)}",
            re.DOTALL,
        ),
    )

    def _extract_output_only(match: re.Match[str]) -> str:
        block_content = match.group(1).strip()

        json_output_match = re.search(
            r'"output"\s*:\s*"((?:[^"\\]|\\.)*)"',
            block_content,
            re.DOTALL,
        )
        if json_output_match:
            output_text = json_output_match.group(1)
            output_text = json.loads('"' + output_text + '"').strip()
            if output_text:
                return f"{VLM_CAPTION_START_TAG}\n{output_text}\n{VLM_CAPTION_END_TAG}"

        labeled_output_match = re.search(
            r"(?:^|\n)(?:@출력:|출력:)\s*(.*)",
            block_content,
            re.DOTALL,
        )
        if labeled_output_match:
            output_text = labeled_output_match.group(1).strip()
            if output_text:
                return f"{VLM_CAPTION_START_TAG}\n{output_text}\n{VLM_CAPTION_END_TAG}"

        return match.group(0)

    for pattern in patterns:
        text = pattern.sub(_extract_output_only, text)
    return text


def _blocks_to_markdown(
    blocks: list[LayoutBlockDTO],
    *,
    structured_blocks: list[StructuredMarkdownBlockDTO],
    include_table_crop_images: bool,
    restore_tables: bool = False,
) -> str:
    lines = []
    structured_by_block_id = {
        structured.block_id: structured for structured in structured_blocks
    }
    for block in sorted(blocks, key=_block_order):
        structured = structured_by_block_id.get(block.block_id)
        if structured and structured.placeholder.startswith("[[TABLE_BLOCK:"):
            if restore_tables:
                lines.append(structured.rendered_text + _table_context_tail(block, structured))
            else:
                lines.append(_table_placeholder_text(structured))
            continue

        text = (block.text or "").strip()
        if include_table_crop_images:
            text = _prepend_table_crop_link(block, text)
        if text:
            lines.append(text)
    return "\n\n".join(lines).strip()


def build_structured_markdown_blocks(
    page: PageEnrichedDTO,
    *,
    include_table_crop_images: bool = False,
    stable_table_ids: bool = False,
) -> list[StructuredMarkdownBlockDTO]:
    blocks = []
    for item_idx, block in enumerate(sorted(page.blocks, key=_block_order)):
        if _is_table_block(block):
            nested_prefix = (
                structured_placeholder("table", page.page.document_id, page.page.page_no, block.block_id)[14:-2]
                if stable_table_ids else _nested_table_prefix(page.page.page_no, item_idx)
            )
            html_raw = (block.table_html_raw or "").strip() or None
            render_format = TableOutputFormat.MARKDOWN
            invalid_table = False
            try:
                render_format = parse_table_output_format(
                    str(block.metadata.get("table_render_format") or "markdown")
                )
                if html_raw:
                    html_raw = sanitize_table_html(html_raw)
                rendered_text = _render_table_block_text(
                    block,
                    html_raw=html_raw,
                    render_format=render_format,
                    nested_table_prefix=nested_prefix,
                )
            except (ValueError, TypeError):
                # Keep the identity and usable page blocks when a table cannot
                # cross the validated renderer boundary. Raw data remains private.
                invalid_table = True
                rendered_text = ""
                record_page_failure(page.page, "structured_registry", "invalid_rendered_table")
            if include_table_crop_images and rendered_text:
                rendered_text = _prepend_table_crop_link(block, rendered_text)
            blocks.append(
                StructuredMarkdownBlockDTO(
                    block_id=block.block_id,
                    label=block.label,
                    placeholder=_table_placeholder(
                        page.page.document_id, page.page.page_no, block
                    ),
                    rendered_text=rendered_text,
                    render_format=render_format,
                    reading_order=block.reading_order,
                    summary=_table_summary(
                        block,
                        rendered_text=rendered_text,
                        html_raw=None if invalid_table else html_raw,
                        nested_table_prefix=nested_prefix,
                    ),
                    html_raw=html_raw,
                    metadata=dict(block.metadata),
                )
            )
            continue
        if _is_image_block(block):
            blocks.append(
                StructuredMarkdownBlockDTO(
                    block_id=block.block_id,
                    label=block.label,
                    placeholder=_image_placeholder(
                        page.page.document_id, page.page.page_no, block
                    ),
                    rendered_text=(block.text or "").strip(),
                    render_format=TableOutputFormat.MARKDOWN,
                    reading_order=block.reading_order,
                    summary=(block.title or "").strip() or None,
                    metadata=dict(block.metadata),
                )
            )
    return blocks


def _is_table_block(block: LayoutBlockDTO) -> bool:
    label = (block.label or "").strip().lower()
    return label in {"table", "tab"} or bool((block.table_html_raw or "").strip())


def _is_image_block(block: LayoutBlockDTO) -> bool:
    label = (block.label or "").strip().lower()
    return label in {"img", "fig", "figure", "image", "picture", "chart"}


def _table_placeholder(document_id: str, page_no: int, block: LayoutBlockDTO) -> str:
    return structured_placeholder("table", document_id, page_no, block.block_id)


def _image_placeholder(document_id: str, page_no: int, block: LayoutBlockDTO) -> str:
    return structured_placeholder("image", document_id, page_no, block.block_id)


def _nested_table_prefix(page_no: int, item_idx: int) -> str:
    return f"table_p{page_no}_i{item_idx}_nested"


def _render_table_block_text(
    block: LayoutBlockDTO,
    *,
    html_raw: str | None,
    render_format: TableOutputFormat,
    nested_table_prefix: str,
) -> str:
    if html_raw:
        return render_validated_table(
            html_raw,
            render_format.value,
            nested_table_prefix=nested_table_prefix,
        ).strip()
    return (block.text or "").strip()


def _table_placeholder_text(block: StructuredMarkdownBlockDTO) -> str:
    if block.summary:
        return f"{block.placeholder}\n{block.summary}"
    return block.placeholder


def _table_summary(
    block: LayoutBlockDTO,
    *,
    rendered_text: str,
    html_raw: str | None,
    nested_table_prefix: str,
) -> str | None:
    markdown = rendered_text
    if html_raw:
        markdown = html_table_to_markdown(
            html_raw,
            nested_table_prefix=nested_table_prefix,
        )

    rows = _first_markdown_table_rows(markdown)
    if not rows:
        title = (block.title or "").strip()
        return f"table summary: {title}" if title else None

    selected = []
    labels = ["header", "first_row", "last_row"]
    indexes = [0, 1, len(rows) - 1]
    seen = set()
    for label, index in zip(labels, indexes):
        if index < 0 or index >= len(rows) or index in seen:
            continue
        seen.add(index)
        selected.append(f"{label}: {rows[index]}")
    return "\n".join(selected).strip() or None


def _markdown_table_rows(markdown: str) -> list[str]:
    rows = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and all(cell and set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        rows.append(" | ".join(cells))
    return rows


def _first_markdown_table_rows(markdown: str) -> list[str]:
    """Summarize the outer table only after nested tables were separated."""
    table_lines = []
    started = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.append(line)
            started = True
            continue
        if started:
            break
    return _markdown_table_rows("\n".join(table_lines))


def _prepend_table_crop_link(block: LayoutBlockDTO, text: str) -> str:
    markdown_path = block.metadata.get("table_crop_markdown_path")
    if not isinstance(markdown_path, str) or not markdown_path.strip():
        return text

    alt_text = _table_crop_alt_text(block)
    image_link = f"![{alt_text}]({markdown_path.strip()})"
    if not text:
        return image_link
    if text.startswith(image_link):
        return text
    return f"{image_link}\n\n{text}"


def _table_crop_alt_text(block: LayoutBlockDTO) -> str:
    reading_order = block.reading_order if block.reading_order is not None else 0
    return f"table {reading_order}"


def _table_html_debug_block(page: PageEnrichedDTO) -> str:
    debug_blocks = []
    for item_idx, block in enumerate(sorted(page.blocks, key=_block_order)):
        raw_html = (block.table_html_raw or "").strip()
        if not raw_html:
            continue
        reading_order = (
            block.reading_order if block.reading_order is not None else item_idx
        )
        debug_blocks.append(
            "\n".join(
                [
                    (
                        "<!-- TABLE DEBUG START "
                        f"page={page.page.page_no} item={item_idx} reading_order={reading_order} -->"
                    ),
                    "```html",
                    raw_html,
                    "```",
                    f"<!-- TABLE DEBUG END page={page.page.page_no} item={item_idx} -->",
                ]
            )
        )

    if not debug_blocks:
        return ""
    return "\n\n## TABLE HTML DEBUG\n\n" + "\n\n".join(debug_blocks)


def _block_order(block: LayoutBlockDTO) -> int:
    if block.reading_order is not None:
        return int(block.reading_order)
    return 10**9


# Preserve the old helper for existing trusted callers.
_structured_blocks = build_structured_markdown_blocks


def _table_context_tail(block, structured):
    context = block.metadata.get("block_context_restore")
    if not isinstance(context, dict):
        return ""
    if (context.get("status") != "restored" or context.get("role") != "table"
            or context.get("block_id") != block.block_id
            or context.get("placeholder") != structured.placeholder):
        return ""
    reference, output = context.get("input_reference"), context.get("output")
    if not isinstance(reference, str) or not isinstance(output, str) or not reference.startswith(structured.placeholder):
        return ""
    # Revalidate metadata at the consumer boundary, including exact references.
    from core.services.block_context_restore import validate_block_response, BlockResponseError
    try:
        validate_block_response({"reasoning": "", "output": output}, reference, "table")
    except BlockResponseError:
        return ""
    return output[len(reference):]


def _block_context_debug(page):
    contexts = [b.metadata["block_context_restore"] for b in page.blocks
                if isinstance(b.metadata.get("block_context_restore"), dict)]
    return "\n\n```block_context_debug\n" + json.dumps(contexts, ensure_ascii=False, indent=2) + "\n```" if contexts else ""
