from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import zipfile


BYTES_PER_MB = 1024 * 1024
DEFAULT_MAX_INPUT_MB = 100
DEFAULT_MAX_PDF_PAGES = 500
DEFAULT_MAX_ZIP_MEMBERS = 1_000
DEFAULT_MAX_ZIP_UNCOMPRESSED_MB = 500
DEFAULT_MAX_ZIP_COMPRESSION_RATIO = 100.0


class DocumentValidationError(ValueError):
    """An input document violated the parser's local resource policy."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class DocumentLimits:
    """Central, local limits for files accepted by the PDF parser."""

    allowed_extensions: tuple[str, ...] = (".pdf",)
    max_input_mb: float = DEFAULT_MAX_INPUT_MB
    max_pdf_pages: int = DEFAULT_MAX_PDF_PAGES
    max_zip_members: int = DEFAULT_MAX_ZIP_MEMBERS
    max_zip_uncompressed_mb: float = DEFAULT_MAX_ZIP_UNCOMPRESSED_MB
    max_zip_compression_ratio: float = DEFAULT_MAX_ZIP_COMPRESSION_RATIO

    def __post_init__(self) -> None:
        extensions = tuple(_normalize_extension(item) for item in self.allowed_extensions)
        if not extensions:
            raise ValueError("allowed_extensions must not be empty")
        if any(value <= 0 for value in (
            self.max_input_mb,
            self.max_pdf_pages,
            self.max_zip_members,
            self.max_zip_uncompressed_mb,
        )):
            raise ValueError("document limits must be positive")
        if self.max_zip_compression_ratio < 1:
            raise ValueError("max_zip_compression_ratio must be at least 1")
        object.__setattr__(self, "allowed_extensions", extensions)

    @property
    def max_input_bytes(self) -> int:
        return int(self.max_input_mb * BYTES_PER_MB)

    @property
    def max_zip_uncompressed_bytes(self) -> int:
        return int(self.max_zip_uncompressed_mb * BYTES_PER_MB)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object] | None) -> "DocumentLimits":
        if raw is None:
            return cls()
        defaults = cls()
        allowed = raw.get("allowed_extensions", defaults.allowed_extensions)
        if not isinstance(allowed, (list, tuple)) or not all(isinstance(item, str) for item in allowed):
            raise ValueError("document_limits.allowed_extensions must be a list of extensions")
        return cls(
            allowed_extensions=tuple(allowed),
            max_input_mb=_positive_float(raw.get("max_input_mb", defaults.max_input_mb), "max_input_mb"),
            max_pdf_pages=_positive_int(raw.get("max_pdf_pages", defaults.max_pdf_pages), "max_pdf_pages"),
            max_zip_members=_positive_int(raw.get("max_zip_members", defaults.max_zip_members), "max_zip_members"),
            max_zip_uncompressed_mb=_positive_float(
                raw.get("max_zip_uncompressed_mb", defaults.max_zip_uncompressed_mb),
                "max_zip_uncompressed_mb",
            ),
            max_zip_compression_ratio=_positive_float(
                raw.get("max_zip_compression_ratio", defaults.max_zip_compression_ratio),
                "max_zip_compression_ratio",
            ),
        )


def assert_allowed_input(path: str | Path, *, limits: DocumentLimits) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise DocumentValidationError("invalid_input_path", f"regular input file required: {candidate.name}")
    suffix = candidate.suffix.lower()
    if suffix not in limits.allowed_extensions:
        allowed = ", ".join(limits.allowed_extensions)
        raise DocumentValidationError("unsupported_extension", f"unsupported input extension {suffix or '<none>'}; allowed: {allowed}")
    if candidate.stat().st_size > limits.max_input_bytes:
        raise DocumentValidationError("input_too_large", f"input exceeds {limits.max_input_bytes} bytes: {candidate.name}")
    return candidate


def validate_zip_archive(path: str | Path, *, limits: DocumentLimits) -> None:
    archive_path = Path(path)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) > limits.max_zip_members:
                raise DocumentValidationError("zip_too_many_files", "ZIP contains too many files")
            total_size = sum(member.file_size for member in members)
            if total_size > limits.max_zip_uncompressed_bytes:
                raise DocumentValidationError("zip_too_large", "ZIP expands beyond the configured size limit")
            for member in members:
                compressed = max(member.compress_size, 1)
                if member.file_size / compressed > limits.max_zip_compression_ratio:
                    raise DocumentValidationError("zip_compression_ratio", f"ZIP member compression ratio is too high: {member.filename}")
    except zipfile.BadZipFile as exc:
        raise DocumentValidationError("corrupt_zip", f"invalid ZIP archive: {archive_path.name}") from exc


def _normalize_extension(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized or "/" in normalized or "\\" in normalized:
        raise ValueError(f"invalid extension: {value!r}")
    return normalized if normalized.startswith(".") else f".{normalized}"


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"document_limits.{field_name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"document_limits.{field_name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"document_limits.{field_name} must be positive")
    return parsed


def _positive_float(value: object, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"document_limits.{field_name} must be a number") from exc
    if parsed <= 0:
        raise ValueError(f"document_limits.{field_name} must be positive")
    return parsed
