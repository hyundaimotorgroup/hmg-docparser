from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ConfluenceUploadOptions:
    token: str
    space_id: str
    parent_id: str
    base_url: str
    email: str | None = None
    title: str | None = None
    update_existing: bool = True
    timeout: float | None = None
    page_split_size: int | None = 50
    split_title_template: str = "{title}_분할_{part:02d}"
    vlm_caption_start_tag: str = "(VLM image caption)"
    vlm_caption_end_tag: str = "(/VLM image caption)"
    vlm_caption_extract_output_only: bool = True
    vlm_caption_format_mode: str = "panel_markdown"
    vlm_caption_panel_title: str = "이미지 설명"
    vlm_caption_expand_title: str = "이미지 설명 펼치기"
    vlm_caption_custom_template: str | None = None


@dataclass(slots=True)
class ConfluenceUploadResult:
    status: str
    page_id: str | None = None
    page_url: str | None = None
    title: str | None = None
    operation: str | None = None
    attachment_count: int = 0
    error: str | None = None
    artifact_path: str | None = None
    pages: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "page_id": self.page_id,
            "page_url": self.page_url,
            "title": self.title,
            "operation": self.operation,
            "attachment_count": self.attachment_count,
            "error": self.error,
            "artifact_path": self.artifact_path,
            "pages": self.pages,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class MarkdownPageChunk:
    md_text: str
    part_index: int = 1
    part_count: int = 1
    start_page: int | None = None
    end_page: int | None = None
    total_pages: int | None = None


@dataclass(slots=True)
class PreparedConfluencePage:
    title: str
    body_storage: str
    attachments: list[tuple[Path, str]]
    part_index: int = 1
    part_count: int = 1
    start_page: int | None = None
    end_page: int | None = None
