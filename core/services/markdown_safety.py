from __future__ import annotations

import re
import html
from urllib.parse import unquote
from pathlib import PurePosixPath

_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_SAFE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def sanitize_markdown_image_urls(markdown: str) -> str:
    """Keep only relative image artifact paths; replace unsafe links with their alt text."""

    def replace(match: re.Match[str]) -> str:
        alt, target = match.group(1), match.group(2).strip()
        decoded = unquote(html.unescape(target))
        path = PurePosixPath(decoded.split("#", 1)[0].split("?", 1)[0])
        if (
            target
            and ":" not in decoded
            and "\\" not in decoded
            and not any(ord(c) < 32 for c in decoded)
            and not target.startswith(("/", "\\"))
            and not path.is_absolute()
            and ".." not in path.parts
            and path.suffix.lower() in _SAFE_IMAGE_EXTENSIONS
        ):
            return match.group(0)
        return alt

    return _MARKDOWN_IMAGE_RE.sub(replace, markdown)


def sanitize_output_markdown(markdown):
    """Escape executable HTML; retain validated tables and harmless textual Markdown.

    Consumers must still render Markdown with raw HTML disabled or a sanitizer.
    """
    from core.services.structured_tables import sanitize_table_html

    tables = []
    # Pick markers absent from the input so provider text cannot impersonate a table.
    marker = "OSS_SAFE_TABLE"
    while marker in markdown:
        marker += "_"

    def table_fragment(match):
        try:
            value = sanitize_table_html(match.group(0))
        except ValueError:
            value = html.escape(match.group(0))
        tables.append(value)
        return f"{marker}{len(tables) - 1}END"

    markdown = re.sub(
        r"<table\b[^>]*>.*?</table\s*>", table_fragment, markdown, flags=re.I | re.S
    )
    # Outside validated tables, escape every HTML tag, including entity-obfuscated
    # URLs and custom elements; attribute blacklists cannot establish safety.
    markdown = re.sub(r"<[^>]+>", lambda m: html.escape(m.group(0)), markdown)
    for index, table in enumerate(tables):
        markdown = markdown.replace(f"{marker}{index}END", table)
    markdown = re.sub(
        r"(?<!!)\[([^\]]*)\]\(([^)]+)\)",
        lambda m: (
            m.group(1)
            if re.match(
                r"\s*(?:javascript|data|vbscript|file):",
                unquote(html.unescape(m.group(2))),
                re.I,
            )
            else m.group(0)
        ),
        markdown,
    )
    return sanitize_markdown_image_urls(markdown)


def preserve_image_captions(output, source):
    """Restore exact linked captions when a later merge changes or omits details."""
    from core.prompts.utils import (
        VLM_CAPTION_START_TAG as start,
        VLM_CAPTION_END_TAG as end,
    )

    source = sanitize_markdown_image_urls(source or "")
    start, end = start.strip(), end.strip()
    pattern = re.compile(
        r"(!\[[^\]]*\]\([^)]+\))\s*" + re.escape(start) + r".*?" + re.escape(end), re.S
    )
    for match in pattern.finditer(source or ""):
        original = match.group(0)
        link = match.group(1)
        target = _MARKDOWN_IMAGE_RE.match(link).group(2)
        existing = re.compile(r"!\[[^\]]*\]\(" + re.escape(target) + r"\)")
        found = existing.search(output)
        if found:
            tail = output[found.end() :]
            caption = re.match(
                r"\s*" + re.escape(start) + r".*?" + re.escape(end), tail, re.S
            )
            boundary = found.end() + (caption.end() if caption else 0)
            output = output[: found.start()] + original + output[boundary:]
        elif original not in output:
            output = output.rstrip() + "\n\n" + original
    # Some source images have no caption fence. Preserve their supplied links
    # too, without duplicating a link whose alt text changed during refinement.
    for match in _MARKDOWN_IMAGE_RE.finditer(source):
        target = match.group(2)
        if not any(item.group(2) == target for item in _MARKDOWN_IMAGE_RE.finditer(output)):
            output = output.rstrip() + "\n\n" + match.group(0)
    return output
