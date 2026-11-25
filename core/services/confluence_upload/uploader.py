from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.services.confluence_upload.client import ConfluenceClient
from core.services.confluence_upload.markdown import prepare_confluence_pages
from core.services.confluence_upload.models import (
    ConfluenceUploadOptions,
    ConfluenceUploadResult,
    PreparedConfluencePage,
)
from core.services.confluence_upload.utils import safe_filename, sanitize_title, strip_processing_title_suffixes


def upload_markdown_to_confluence(
    *,
    markdown: str,
    document_title: str,
    output_dir: Path,
    markdown_base_dir: Path,
    options: ConfluenceUploadOptions,
) -> ConfluenceUploadResult:
    title = sanitize_title(strip_processing_title_suffixes(options.title or document_title))
    client = ConfluenceClient(options)
    client.get_space(options.space_id)

    prepared_pages = prepare_confluence_pages(
        markdown=markdown,
        title=title,
        markdown_base_dir=markdown_base_dir,
        output_dir=output_dir,
        options=options,
    )

    page_results: list[dict[str, Any]] = []
    warnings: list[str] = []
    uploaded = 0
    attempted = 0
    for prepared_page in prepared_pages:
        page_result, attachment_count, page_warnings = _upload_prepared_page(
            client=client,
            prepared_page=prepared_page,
            options=options,
        )
        page_results.append(page_result)
        uploaded += int(page_result.get("attachment_uploaded_count") or 0)
        attempted += attachment_count
        warnings.extend(page_warnings)

    first_page = page_results[0] if page_results else {}
    result = ConfluenceUploadResult(
        status="uploaded",
        page_id=first_page.get("page_id"),
        page_url=first_page.get("page_url"),
        title=title,
        operation="split_upload" if len(page_results) > 1 else first_page.get("operation"),
        attachment_count=uploaded,
        pages=page_results,
        warnings=warnings,
        metadata={
            "space_id": options.space_id,
            "parent_id": str(options.parent_id),
            "page_count": len(page_results),
            "attachment_attempted_count": attempted,
            "attachment_failed_count": attempted - uploaded,
        },
    )
    result.artifact_path = str(write_upload_result_artifact(result, output_dir=output_dir, document_title=title))
    return result


def write_upload_result_artifact(
    result: ConfluenceUploadResult,
    *,
    output_dir: Path,
    document_title: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{safe_filename(document_title)}_confluence_upload.json"
    path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _upload_prepared_page(
    *,
    client: ConfluenceClient,
    prepared_page: PreparedConfluencePage,
    options: ConfluenceUploadOptions,
) -> tuple[dict[str, Any], int, list[str]]:
    existing = client.get_page_by_title(options.space_id, prepared_page.title)
    if existing and options.update_existing:
        page = client.update_page(
            page_id=str(existing["id"]),
            title=prepared_page.title,
            body_storage=prepared_page.body_storage,
            current_version=existing.get("version", {}).get("number", 1),
        )
        operation = "updated"
    elif existing:
        raise ValueError(f"Confluence page already exists and update_existing=false: {prepared_page.title}")
    else:
        page = client.create_page(
            space_id=options.space_id,
            parent_id=options.parent_id,
            title=prepared_page.title,
            body_storage=prepared_page.body_storage,
        )
        operation = "created"

    page_id = str(page["id"])
    warnings: list[str] = []
    try:
        for attachment in client.list_attachments(page_id):
            attachment_id = attachment.get("id")
            if attachment_id:
                client.delete_attachment(str(attachment_id))
    except Exception as exc:
        warnings.append(f"failed to delete existing attachments for page {page_id}: {type(exc).__name__}")

    uploaded = 0
    failed = 0
    for attachment_path, attachment_name in prepared_page.attachments:
        try:
            client.upload_attachment(page_id=page_id, path=attachment_path, attachment_name=attachment_name)
            uploaded += 1
        except Exception as exc:
            failed += 1
            warnings.append(
                "failed to upload attachment "
                f"page_id={page_id} title={prepared_page.title!r} "
                f"name={attachment_name!r} path={str(attachment_path)!r} "
                f"size={_file_size_or_none(attachment_path)} error_type={type(exc).__name__}"
            )

    return (
        {
            "page_id": page_id,
            "page_url": client.page_url(page),
            "title": prepared_page.title,
            "operation": operation,
            "attachment_count": len(prepared_page.attachments),
            "attachment_uploaded_count": uploaded,
            "attachment_failed_count": failed,
            "part_index": prepared_page.part_index,
            "part_count": prepared_page.part_count,
            "start_page": prepared_page.start_page,
            "end_page": prepared_page.end_page,
        },
        len(prepared_page.attachments),
        warnings,
    )


def _file_size_or_none(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None
