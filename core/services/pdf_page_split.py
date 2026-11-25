from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from core.domain.artifacts import ArtifactRef
from core.domain.document.models import DocumentDTO, PageDTO


def split_pdf_document_to_pages(
    document: DocumentDTO,
    *,
    output_dir: str,
) -> list[PageDTO]:
    source_path = Path(document.metadata.source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"source PDF not found: {source_path}")

    page_dir = Path(output_dir) / document.document_id
    page_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(source_path))
    pages: list[PageDTO] = []
    for index, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)
        page_path = page_dir / f"{document.document_id}_p{index:04d}.pdf"
        with page_path.open("wb") as file:
            writer.write(file)

        mediabox = page.mediabox
        pages.append(
            PageDTO(
                document_id=document.document_id,
                page_no=index,
                width=_safe_int(float(mediabox.width)),
                height=_safe_int(float(mediabox.height)),
                pdf_artifact=ArtifactRef(
                    path=str(page_path),
                    media_type="application/pdf",
                    description="single page pdf",
                ),
            )
        )

    return pages


def _safe_int(value: float) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
