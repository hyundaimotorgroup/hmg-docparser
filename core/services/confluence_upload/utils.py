from __future__ import annotations

import re
from pathlib import Path


def sanitize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()[:240] or "Parsed Document"


PROCESSING_TITLE_SUFFIXES = (
    "_debug",
    "_COT",
    "_OCR",
    "_LAYOUT",
    "_pdfplumber",
    "_COMBINE_TEXT",
    "_REFINE_TABLE",
)


def strip_processing_title_suffixes(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        return "Parsed Document"

    changed = True
    while changed:
        changed = False
        for suffix in PROCESSING_TITLE_SUFFIXES:
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].rstrip(" _.-")
                changed = True
        refined = re.sub(r"_REFINE_TABLE(?:_\d+)?$", "", cleaned).rstrip(" _.-")
        if refined != cleaned:
            cleaned = refined
            changed = True
    return cleaned or title.strip() or "Parsed Document"


def create_sanitized_name(original_filename: str) -> str:
    chars_to_replace = {
        "[": "_",
        "]": "_",
        "(": "_",
        ")": "_",
        "-": "_",
        " ": "_",
        "◈": "_",
        ".": "_",
    }
    name = Path(original_filename).stem
    ext = Path(original_filename).suffix
    sanitized_name = name
    for char, replacement in chars_to_replace.items():
        sanitized_name = sanitized_name.replace(char, replacement)
    while "__" in sanitized_name:
        sanitized_name = sanitized_name.replace("__", "_")
    sanitized_name = sanitized_name.strip("_") or "attachment"
    return sanitized_name + ext


def safe_filename(filename: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename).strip(" ._")
    return safe or "confluence_upload"
