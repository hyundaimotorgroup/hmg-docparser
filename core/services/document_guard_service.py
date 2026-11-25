from __future__ import annotations

from pathlib import Path

from core.services.document_limits import (
    BYTES_PER_MB,
    DEFAULT_MAX_INPUT_MB,
    DocumentLimits,
    DocumentValidationError,
    assert_allowed_input,
)


DEFAULT_MAX_PDF_BYTES = DEFAULT_MAX_INPUT_MB * BYTES_PER_MB


class ProtectedDocumentError(RuntimeError):
    """Raised when an input document is protected and cannot be parsed."""


def assert_processable_document(
    path: str | Path,
    *,
    max_pdf_bytes: int = DEFAULT_MAX_PDF_BYTES,
    limits: DocumentLimits | None = None,
) -> None:
    effective_limits = limits or DocumentLimits(max_input_mb=max_pdf_bytes / BYTES_PER_MB)
    document_path = assert_allowed_input(path, limits=effective_limits)
    try:
        import pypdf

        with document_path.open("rb") as file:
            reader = pypdf.PdfReader(file)
            if getattr(reader, "is_encrypted", False):
                raise ProtectedDocumentError(f"보호된 PDF는 지원하지 않습니다: {document_path.name}")
            page_count = len(reader.pages)
            if page_count > effective_limits.max_pdf_pages:
                raise DocumentValidationError(
                    "too_many_pages",
                    f"PDF has {page_count} pages; limit is {effective_limits.max_pdf_pages}",
                )
            if _has_aip_marker(reader):
                raise ProtectedDocumentError(f"보호된 PDF는 지원하지 않습니다: {document_path.name}")
    except ProtectedDocumentError:
        raise
    except DocumentValidationError:
        raise
    except Exception as exc:
        raise DocumentValidationError("corrupt_pdf", f"invalid or unreadable PDF: {document_path.name}") from exc


def _has_aip_marker(reader: object) -> bool:
    pages = getattr(reader, "pages", ())
    if not pages:
        return False
    try:
        text = pages[0].extract_text() or ""
    except Exception:
        return False
    keywords = (
        "Microsoft Azure Information Protection",
        "이 문서는 보호된 문서입니다",
        "지원되는 PDF 리더 앱을 사용하여 볼 수 있습니다",
        "MSIP_Label_",
    )
    return any(keyword in text for keyword in keywords)


def is_oversized_pdf(pdf_path: str | Path, *, max_pdf_bytes: int = DEFAULT_MAX_PDF_BYTES) -> bool:
    path = Path(pdf_path)
    return path.suffix.lower() == ".pdf" and path.is_file() and path.stat().st_size > max_pdf_bytes


def is_aip_protected_pdf(pdf_path: str | Path) -> bool:
    """Detect encrypted or AIP-protected PDFs without masking corrupt input as protected."""
    path = Path(pdf_path)
    if path.suffix.lower() != ".pdf":
        return False
    try:
        import pypdf

        with path.open("rb") as file:
            reader = pypdf.PdfReader(file)
            return bool(getattr(reader, "is_encrypted", False) or _has_aip_marker(reader))
    except Exception:
        return False
