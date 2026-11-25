from __future__ import annotations

from pathlib import Path

from core.domain.artifacts import ArtifactRef
from core.domain.document.models import DocumentDTO
from core.interfaces.node import Node, NodeContext, NodeResult
from core.services.confluence_upload import (
    ConfluenceUploadOptions,
    ConfluenceUploadResult,
    upload_markdown_to_confluence,
    write_upload_result_artifact,
)
from core.services.confluence_upload.utils import strip_processing_title_suffixes


class ConfluenceUploadNode(Node):
    node_name = "confluence_uploader"
    input_type = "document_dto@v1"
    output_type = "document_dto@v1"

    def run(self, context: NodeContext, value: object) -> NodeResult:
        if not isinstance(value, DocumentDTO):
            raise TypeError("confluence_uploader expects DocumentDTO")

        options = _build_options(context.config)
        markdown = value.markdown or _read_markdown_artifact(value)
        if not markdown:
            raise ValueError("Confluence upload requested but document markdown is empty")

        output_dir = Path(_optional_str(_runtime_config(context).get("outputs")) or "outputs")
        markdown_base_dir = _document_base_dir(value, output_dir)
        document_title = _resolve_document_title(value, context.config)

        try:
            upload_result = upload_markdown_to_confluence(
                markdown=markdown,
                document_title=document_title,
                output_dir=output_dir,
                markdown_base_dir=markdown_base_dir,
                options=options,
            )
        except Exception as exc:
            # requests exceptions can contain private URLs and response details.
            safe_error = f"Confluence request failed ({type(exc).__name__})"
            failed = ConfluenceUploadResult(
                status="failed",
                title=document_title,
                error=safe_error,
                metadata={"space_id": options.space_id, "parent_id": options.parent_id},
            )
            failed.artifact_path = str(
                write_upload_result_artifact(
                    failed,
                    output_dir=output_dir,
                    document_title=document_title,
                )
            )
            value.artifacts.append(
                ArtifactRef(
                    path=failed.artifact_path,
                    media_type="application/json",
                    description="Confluence upload failure result",
                )
            )
            raise RuntimeError(safe_error) from None

        if upload_result.artifact_path:
            value.artifacts.append(
                ArtifactRef(
                    path=upload_result.artifact_path,
                    media_type="application/json",
                    description="Confluence upload result",
                )
            )
        return NodeResult(value=value, metadata=upload_result.to_dict())


def _build_options(config: dict[str, object]) -> ConfluenceUploadOptions:
    token = _optional_str(config.get("token"))
    space_id = _optional_str(config.get("space_id"))
    parent_id = _optional_str(config.get("parent_id"))
    provided = [token, space_id, parent_id]
    if any(provided) and not all(provided):
        missing = [
            name
            for name, value in (
                ("token", token),
                ("space_id", space_id),
                ("parent_id", parent_id),
            )
            if not value
        ]
        raise ValueError(f"Confluence upload requires token, space_id, parent_id. missing={missing}")
    if not all(provided):
        raise ValueError("Confluence upload config is empty")

    return ConfluenceUploadOptions(
        token=token or "",
        space_id=space_id or "",
        parent_id=parent_id or "",
        base_url=_required_str(config, "base_url"),
        email=_optional_str(config.get("email")),
        title=_optional_str(config.get("title")),
        update_existing=_bool_config(config.get("update_existing"), default=True),
        timeout=_optional_float_config(config.get("timeout")),
        page_split_size=_optional_int(config.get("page_split_size"), default=50),
        split_title_template=_optional_str(config.get("split_title_template")) or "{title}_분할_{part:02d}",
        vlm_caption_start_tag=_optional_str(config.get("vlm_caption_start_tag")) or "(VLM image caption)",
        vlm_caption_end_tag=_optional_str(config.get("vlm_caption_end_tag")) or "(/VLM image caption)",
        vlm_caption_extract_output_only=_bool_config(
            config.get("vlm_caption_extract_output_only"),
            default=True,
        ),
        vlm_caption_format_mode=_optional_str(config.get("vlm_caption_format_mode")) or "panel_markdown",
        vlm_caption_panel_title=_optional_str(config.get("vlm_caption_panel_title")) or "이미지 설명",
        vlm_caption_expand_title=_optional_str(config.get("vlm_caption_expand_title")) or "이미지 설명 펼치기",
        vlm_caption_custom_template=_optional_str(config.get("vlm_caption_custom_template")),
    )


def _runtime_config(context: NodeContext) -> dict[str, object]:
    value = context.metadata.get("runtime_config", {})
    return value if isinstance(value, dict) else {}


def _read_markdown_artifact(document: DocumentDTO) -> str | None:
    for artifact in document.artifacts:
        if artifact.media_type == "text/markdown":
            path = Path(artifact.path)
            if path.exists():
                return path.read_text(encoding="utf-8")
    return None


def _document_base_dir(document: DocumentDTO, output_dir: Path) -> Path:
    for artifact in document.artifacts:
        if artifact.media_type == "text/markdown":
            path = Path(artifact.path)
            if path.exists():
                return path.parent
    return output_dir


def _resolve_document_title(document: DocumentDTO, confluence_config: dict[str, object]) -> str:
    configured_title = _optional_str(confluence_config.get("title"))
    if configured_title:
        return strip_processing_title_suffixes(configured_title)

    candidate = _optional_str(document.document_id) or _optional_str(document.metadata.file_name) or "Parsed Document"
    return strip_processing_title_suffixes(Path(candidate).stem)


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _required_str(config: dict[str, object], key: str) -> str:
    value = _optional_str(config.get(key))
    if value is None:
        raise ValueError(f"Confluence upload requires {key}")
    return value


def _bool_config(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return default


def _optional_float_config(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _optional_int(value: object, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if not value.strip():
            return default
        try:
            return int(value)
        except ValueError:
            return default
    return default
