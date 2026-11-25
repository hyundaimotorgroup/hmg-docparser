from __future__ import annotations

from collections.abc import Sequence

import pdfplumber

from core.domain.document.models import PageDTO
from core.domain.markdown.models import PageMarkdownDTO, StructuredRestoreContext
from core.domain.markdown.protocol import TABLE_REFERENCE_RE
from core.services.pdf_rendering import pdf_has_images


def extract_pdfplumber_markdown(page: PageDTO) -> PageMarkdownDTO:
    if page.pdf_artifact is None:
        raise ValueError(f"page has no pdf_artifact: {page.document_id}:{page.page_no}")

    with pdfplumber.open(page.pdf_artifact.path) as pdf:
        text_parts = []
        table_parts = []
        for pdf_page in pdf.pages:
            text = pdf_page.extract_text()
            text_parts.append(text or "")
            tables = pdf_page.extract_tables()
            if tables:
                table_parts.extend(_format_table(table) for table in tables)

    markdown = f"@page:{page.page_no}\n\n[text]\n{_join_parts(text_parts)}"
    if table_parts:
        markdown += f"\n[tables]\n{_join_parts(table_parts)}"

    return PageMarkdownDTO(page=page, markdown=markdown, restore_context=StructuredRestoreContext(registry_status="complete", literal_references=tuple(m.group() for m in TABLE_REFERENCE_RE.finditer(markdown))))


def extract_pdfplumber_text(page: PageDTO) -> str:
    if page.pdf_artifact is None:
        raise ValueError(f"page has no pdf_artifact: {page.document_id}:{page.page_no}")

    with pdfplumber.open(page.pdf_artifact.path) as pdf:
        text_parts = [str(pdf_page.extract_text() or "") for pdf_page in pdf.pages]

    return _join_parts(text_parts).strip()


def extract_pdfplumber_text_if_no_images(page: PageDTO) -> str | None:
    """Preserve the native-text gate, including inline and Form XObject images."""
    if page.pdf_artifact is None:
        raise ValueError(f"page has no pdf_artifact: {page.document_id}:{page.page_no}")

    if pdf_has_images(page.pdf_artifact.path):
        return None
    with pdfplumber.open(page.pdf_artifact.path) as pdf:
        text = _join_parts([str(pdf_page.extract_text() or "") for pdf_page in pdf.pages]).strip()
    return text or None


def join_page_markdowns(pages: Sequence[PageMarkdownDTO]) -> str:
    return "".join(
        "\n\n" + page.markdown.strip()
        for page in sorted(pages, key=lambda item: item.page.page_no)
    )


def _format_table(table: list[list[object]]) -> str:
    table_text = ""
    for row in table:
        table_text += "\n" + str(row)
    return table_text


def _join_parts(parts: Sequence[str]) -> str:
    return "\n".join(part for part in parts if part)
