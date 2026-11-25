from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.artifacts import ArtifactRef
from core.domain.document.models import PageDTO

BBox = tuple[int, int, int, int]


@dataclass(slots=True)
class LayoutBlockDTO:
    block_id: str
    label: str
    bbox: BBox | None = None
    reading_order: int | None = None
    crop_artifact: ArtifactRef | None = None
    text: str | None = None
    title: str | None = None
    score: float | None = None
    table_html_raw: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class PageLayoutDTO:
    page: PageDTO
    blocks: list[LayoutBlockDTO] = field(default_factory=list)


@dataclass(slots=True)
class PageEnrichedDTO:
    page: PageDTO
    blocks: list[LayoutBlockDTO] = field(default_factory=list)
    source_node_id: str | None = None
