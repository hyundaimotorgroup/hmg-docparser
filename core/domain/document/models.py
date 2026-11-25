from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.artifacts import ArtifactRef


@dataclass(slots=True)
class DocumentMetadataDTO:
    source_path: str
    file_name: str
    mime_type: str | None = None
    page_count: int | None = None


@dataclass(slots=True)
class PageDTO:
    document_id: str
    page_no: int
    width: int | None = None
    height: int | None = None
    pdf_artifact: ArtifactRef | None = None
    image_artifact: ArtifactRef | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class DocumentDTO:
    document_id: str
    metadata: DocumentMetadataDTO
    pages: list[PageDTO] = field(default_factory=list)
    extracted_text: str | None = None
    markdown: str | None = None
    artifacts: list[ArtifactRef] = field(default_factory=list)
