from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re

from core.domain.document.models import PageDTO
from core.domain.markdown.protocol import STRUCTURED_PLACEHOLDER_RE


class TableOutputFormat(str, Enum):
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    TOON = "toon"


_STRUCTURED_PLACEHOLDER_RE = STRUCTURED_PLACEHOLDER_RE


@dataclass(frozen=True, slots=True)
class StructuredRestoreContext:
    supplied_references: tuple[str, ...] = ()
    registry_status: str = "unknown"
    literal_references: tuple[str, ...] = ()
    rendered_ids: tuple[str, ...] = ()

    def __post_init__(self):
        if self.registry_status not in {"complete", "incomplete", "unknown"}:
            raise ValueError("invalid registry status")


@dataclass(frozen=True, slots=True)
class PageFailureDTO:
    stage: str
    reason: str

    def render_markdown(self) -> str:
        return f"[Error] {self.stage}: {self.reason}"


@dataclass(slots=True)
class StructuredMarkdownBlockDTO:
    block_id: str
    label: str
    placeholder: str
    rendered_text: str
    render_format: TableOutputFormat
    reading_order: int | None = None
    summary: str | None = None
    html_raw: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.block_id.strip():
            raise ValueError("structured block_id must not be empty")
        if not _STRUCTURED_PLACEHOLDER_RE.fullmatch(self.placeholder):
            raise ValueError("structured placeholder must be a stable TABLE_BLOCK or IMAGE_BLOCK token")
        try:
            self.render_format = TableOutputFormat(self.render_format)
        except ValueError as exc:
            raise ValueError(f"unsupported structured render_format: {self.render_format}") from exc


@dataclass(slots=True)
class PageMarkdownDTO:
    page: PageDTO
    markdown: str
    cot_markdown: str | None = None
    structured_blocks: list[StructuredMarkdownBlockDTO] = field(default_factory=list)
    failures: list[PageFailureDTO] = field(default_factory=list)
    restore_context: StructuredRestoreContext = field(default_factory=StructuredRestoreContext)
