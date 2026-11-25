from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re

from core.domain.artifacts import ArtifactRef
from core.domain.document.models import DocumentDTO, DocumentMetadataDTO, PageDTO
from core.domain.layout.models import LayoutBlockDTO, PageEnrichedDTO, PageLayoutDTO
from core.domain.markdown.models import PageMarkdownDTO

_PAGE_SPLIT_PATTERN = re.compile(r"@page:\s*(\d+)\s*\n", re.MULTILINE)


def document_dto_from_source(
    source_path: str,
    *,
    document_id: str | None = None,
    page_count: int | None = None,
    mime_type: str | None = "application/pdf",
) -> DocumentDTO:
    path = Path(source_path)
    resolved_document_id = document_id or path.stem
    metadata = DocumentMetadataDTO(
        source_path=str(path),
        file_name=path.name,
        mime_type=mime_type,
        page_count=page_count,
    )
    return DocumentDTO(document_id=resolved_document_id, metadata=metadata)


def legacy_page_info_to_page_dto(
    page_info: dict[str, object],
    *,
    document_id: str,
    pdf_artifact: ArtifactRef | None = None,
    image_artifact: ArtifactRef | None = None,
) -> PageDTO:
    return PageDTO(
        document_id=document_id,
        page_no=int(page_info.get("page_no", 0)),
        width=_safe_int(page_info.get("width")),
        height=_safe_int(page_info.get("height")),
        pdf_artifact=pdf_artifact,
        image_artifact=image_artifact,
    )


def legacy_layout_item_to_block_dto(
    item: dict[str, object],
    *,
    document_id: str,
    page_no: int,
    item_idx: int,
    crop_artifact: ArtifactRef | None = None,
) -> LayoutBlockDTO:
    reading_order = _safe_int(item.get("reading_order"))
    block_key = reading_order if reading_order is not None else item_idx
    bbox_value = item.get("bbox")

    metadata = {}
    if item.get("crop") is not None:
        metadata["legacy_has_crop"] = True

    return LayoutBlockDTO(
        block_id=f"{document_id}:{page_no}:{block_key}",
        label=str(item.get("label", "") or ""),
        bbox=_coerce_bbox(bbox_value),
        reading_order=reading_order,
        crop_artifact=crop_artifact,
        text=_safe_str(item.get("text")),
        title=_safe_str(item.get("title")),
        score=_safe_float(item.get("score")),
        table_html_raw=_safe_str(item.get("table_html_raw")),
        metadata=metadata,
    )


def legacy_page_result_to_layout_dto(
    page_result: dict[str, object],
    *,
    document_id: str,
    crop_artifacts: dict[int, ArtifactRef] | None = None,
    image_artifact: ArtifactRef | None = None,
    pdf_artifact: ArtifactRef | None = None,
) -> PageLayoutDTO:
    crop_artifacts = crop_artifacts or {}
    page = legacy_page_info_to_page_dto(
        page_result.get("page_info", {}),
        document_id=document_id,
        pdf_artifact=pdf_artifact,
        image_artifact=image_artifact,
    )
    blocks = [
        legacy_layout_item_to_block_dto(
            item,
            document_id=document_id,
            page_no=page.page_no,
            item_idx=item_idx,
            crop_artifact=crop_artifacts.get(item_idx),
        )
        for item_idx, item in enumerate(page_result.get("layout_dets", []) or [])
    ]
    return PageLayoutDTO(page=page, blocks=blocks)


def legacy_page_result_to_enriched_dto(
    page_result: dict[str, object],
    *,
    document_id: str,
    source_node_id: str | None = None,
    crop_artifacts: dict[int, ArtifactRef] | None = None,
    image_artifact: ArtifactRef | None = None,
    pdf_artifact: ArtifactRef | None = None,
) -> PageEnrichedDTO:
    layout_dto = legacy_page_result_to_layout_dto(
        page_result,
        document_id=document_id,
        crop_artifacts=crop_artifacts,
        image_artifact=image_artifact,
        pdf_artifact=pdf_artifact,
    )
    return PageEnrichedDTO(
        page=layout_dto.page,
        blocks=layout_dto.blocks,
        source_node_id=source_node_id,
    )


def paged_markdown_text_to_dtos(
    text: str,
    *,
    document_id: str,
    pages: list[PageDTO] | None = None,
    cot_text: str | None = None,
) -> list[PageMarkdownDTO]:
    page_texts = _split_paged_text(text)
    cot_page_texts = _split_paged_text(cot_text) if cot_text else {}
    page_map = {page.page_no: page for page in (pages or [])}

    markdown_pages = []
    for page_no, page_markdown in sorted(page_texts.items()):
        page = page_map.get(page_no) or PageDTO(document_id=document_id, page_no=page_no)
        markdown_pages.append(
            PageMarkdownDTO(
                page=page,
                markdown=page_markdown,
                cot_markdown=cot_page_texts.get(page_no),
            )
        )
    return markdown_pages


def paged_text_to_document_dto(
    text: str,
    *,
    source_path: str,
    document_id: str | None = None,
    cot_text: str | None = None,
) -> DocumentDTO:
    page_bodies = _split_paged_text(text)
    document = document_dto_from_source(
        source_path,
        document_id=document_id,
        page_count=len(page_bodies),
        mime_type="text/markdown",
    )
    pages = [PageDTO(document_id=document.document_id, page_no=page_no) for page_no in sorted(page_bodies)]
    markdown_pages = paged_markdown_text_to_dtos(
        text,
        document_id=document.document_id,
        pages=pages,
        cot_text=cot_text,
    )
    markdown = "\n".join(
        f"@page:{page.page.page_no}\n{page.markdown}".rstrip()
        for page in markdown_pages
    ).strip()
    return replace(document, pages=pages, markdown=markdown)


def _split_paged_text(text: str | None) -> dict[int, str]:
    if not text:
        return {}

    matches = list(_PAGE_SPLIT_PATTERN.finditer(text))
    if not matches:
        return {}

    result = {}
    for index, match in enumerate(matches):
        page_no = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[page_no] = text[start:end].strip()
    return result


def _safe_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def _coerce_bbox(value: object) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    coerced = []
    for item in value:
        int_value = _safe_int(item)
        if int_value is None:
            return None
        coerced.append(int_value)
    return tuple(coerced)  # type: ignore[return-value]
