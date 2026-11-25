from __future__ import annotations

import zipfile
from pathlib import Path

from core.services.document_limits import DocumentLimits, DocumentValidationError


def zip_output_dir(job_id, output_dir, basenames=None, *, limits: DocumentLimits | None = None):
    output_dir = Path(output_dir)
    zip_path = output_dir.parent / (job_id + ".zip")
    final_basenames = [str(basename) for basename in (basenames or [])]
    effective_limits = limits or DocumentLimits()
    files = _collect_output_files(output_dir, final_basenames)
    _assert_package_limits(files, effective_limits)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_ref:
        for path, archive_name in files:
            zip_ref.write(path, archive_name)

    return str(zip_path)


def _write_directory_to_zip(zip_ref, directory: Path, arc_dirname: str):
    files = [path for path in directory.rglob("*") if path.is_file()]
    if not files:
        zip_ref.writestr(f"{arc_dirname}/", "")
        return

    for path in files:
        zip_ref.write(path, path.relative_to(directory.parent))


def _collect_output_files(output_dir: Path, basenames: list[str]) -> list[tuple[Path, Path]]:
    files: list[tuple[Path, Path]] = []
    for basename in basenames:
        markdown_path = output_dir / f"{basename}.md"
        if markdown_path.is_file():
            files.append((markdown_path, Path(markdown_path.name)))
    for dirname in ("table_imgs", "imgs"):
        directory = output_dir / dirname
        if directory.is_dir():
            files.extend((path, path.relative_to(output_dir)) for path in directory.rglob("*") if path.is_file())
    return files


def _assert_package_limits(files: list[tuple[Path, Path]], limits: DocumentLimits) -> None:
    if len(files) > limits.max_zip_members:
        raise DocumentValidationError("output_too_many_files", "output contains too many files to package")
    total_size = sum(path.stat().st_size for path, _ in files)
    if total_size > limits.max_zip_uncompressed_bytes:
        raise DocumentValidationError("output_too_large", "output exceeds the configured packaging limit")
