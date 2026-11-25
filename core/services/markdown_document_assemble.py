from __future__ import annotations

from pathlib import Path
import re

from core.domain.artifacts import ArtifactRef
from core.domain.document.models import DocumentDTO, DocumentMetadataDTO
from core.domain.markdown.models import PageMarkdownDTO
from core.services.markdown_validation import validate_page_markdown


def assemble_merged_pages_document(
    pages: list[PageMarkdownDTO],
    *,
    output_dir: str,
    document_id: str,
    task_name: str,
    save_suffix: str = "",
    save_debug_artifacts: bool = False,
) -> DocumentDTO:
    ordered = sorted(pages, key=lambda page: page.page.page_no)
    for page in ordered:
        validate_page_markdown(page)
    markdown = _join_page_outputs((page.page.page_no, page.markdown) for page in ordered)
    cot_markdown = _join_page_outputs(
        (page.page.page_no, page.cot_markdown or page.markdown) for page in ordered
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    markdown_path = output_path / f"{document_id}_{task_name}{save_suffix}.md"
    markdown_path.write_text(markdown, encoding="utf-8")

    artifacts = [
        ArtifactRef(path=str(markdown_path), media_type="text/markdown", description="combined markdown"),
    ]
    if save_debug_artifacts:
        private_dir = output_path / "_private"
        private_dir.mkdir(parents=True, exist_ok=True)
        cot_path = private_dir / f"{document_id}_{task_name}_debug{save_suffix}.md"
        cot_path.write_text(cot_markdown, encoding="utf-8")
        artifacts.append(
            ArtifactRef(path=str(cot_path), media_type="text/markdown", description="combined markdown debug")
        )

    return DocumentDTO(
        document_id=document_id,
        metadata=DocumentMetadataDTO(
            source_path=str(markdown_path),
            file_name=markdown_path.name,
            mime_type="text/markdown",
            page_count=len(ordered),
        ),
        pages=[page.page for page in ordered],
        markdown=markdown,
        extracted_text=markdown,
        artifacts=artifacts,
    )


def _join_page_outputs(items) -> str:
    ordered = sorted(items, key=lambda item: item[0])
    return "\n".join(
        f"\n@page:{page_no}\n" + re.sub(
            rf"^\s*@page:{page_no}(?=\s|$)[^\S\n]*\n?", "", content, count=1
        )
        for page_no, content in ordered
    )
