from __future__ import annotations

import html
import json
from pathlib import Path
import re

from core.services.confluence_upload.models import (
    ConfluenceUploadOptions,
    MarkdownPageChunk,
    PreparedConfluencePage,
)
from core.services.confluence_upload.utils import create_sanitized_name, sanitize_title
from core.services.structured_tables import sanitize_table_html


def markdown_to_confluence_storage(
    markdown: str,
    *,
    markdown_base_dir: Path,
    output_dir: Path,
    options: ConfluenceUploadOptions | None = None,
    total_page_count: int | None = None,
) -> tuple[str, list[tuple[Path, str]]]:
    attachments: list[tuple[Path, str]] = []
    options = options or ConfluenceUploadOptions(
        token="",
        space_id="",
        parent_id="",
        base_url="https://example.invalid",
    )
    markdown = _normalize_markdown_source(markdown)

    def replace_image(match: re.Match[str]) -> str:
        alt = html.escape(match.group(1) or "")
        raw_path = match.group(2).strip()
        resolved = _resolve_local_path(raw_path, markdown_base_dir=markdown_base_dir, output_dir=output_dir)
        if resolved is None:
            return f"<p>{alt}</p>"
        attachment_name = create_sanitized_name(resolved.name)
        attachments.append((resolved, attachment_name))
        return (
            '<ac:image ac:alt="' + alt + '">'
            '<ri:attachment ri:filename="' + html.escape(attachment_name) + '" />'
            "</ac:image>"
        )

    source = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_image, markdown)
    source = convert_vlm_caption_blocks(
        source,
        start_tag=options.vlm_caption_start_tag,
        end_tag=options.vlm_caption_end_tag,
        extract_output_only=options.vlm_caption_extract_output_only,
        mode=options.vlm_caption_format_mode,
        panel_title=options.vlm_caption_panel_title,
        expand_title=options.vlm_caption_expand_title,
        custom_template=options.vlm_caption_custom_template,
    )
    source = convert_table_format_blocks(source)
    source = add_styled_page_separators(source, total_page_count=total_page_count)
    source, storage_blocks = _protect_storage_blocks(source)
    body_storage = blocks_to_storage_html(source)
    return _restore_storage_blocks(body_storage, storage_blocks), attachments


def prepare_confluence_pages(
    *,
    markdown: str,
    title: str,
    markdown_base_dir: Path,
    output_dir: Path,
    options: ConfluenceUploadOptions,
) -> list[PreparedConfluencePage]:
    markdown = _normalize_markdown_source(markdown)
    chunks = split_markdown_by_pages(markdown, page_split_size=options.page_split_size)
    is_split = len(chunks) > 1
    prepared: list[PreparedConfluencePage] = []
    for chunk in chunks:
        page_title = (
            format_split_title(title, chunk, options.split_title_template)
            if is_split
            else title
        )
        body_storage, attachments = markdown_to_confluence_storage(
            chunk.md_text,
            markdown_base_dir=markdown_base_dir,
            output_dir=output_dir,
            options=options,
            total_page_count=chunk.total_pages,
        )
        prepared.append(
            PreparedConfluencePage(
                title=page_title,
                body_storage=body_storage,
                attachments=attachments,
                part_index=chunk.part_index,
                part_count=chunk.part_count,
                start_page=chunk.start_page,
                end_page=chunk.end_page,
            )
        )
    return prepared


def split_markdown_by_pages(markdown: str, page_split_size: int | None = 50) -> list[MarkdownPageChunk]:
    markdown = _normalize_markdown_source(markdown)
    page_matches = list(re.finditer(r"@page:(\d+)", markdown))
    if not page_matches or not page_split_size or page_split_size <= 0:
        return [MarkdownPageChunk(md_text=markdown)]

    total_pages = len(page_matches)
    preamble = markdown[: page_matches[0].start()].strip()
    sections: list[dict[str, object]] = []
    for index, match in enumerate(page_matches):
        content_end = page_matches[index + 1].start() if index + 1 < total_pages else len(markdown)
        sections.append(
            {
                "page_number": int(match.group(1)),
                "text": markdown[match.start() : content_end].strip(),
            }
        )

    chunks: list[MarkdownPageChunk] = []
    grouped_sections = [
        sections[index : index + page_split_size]
        for index in range(0, len(sections), page_split_size)
    ]
    part_count = len(grouped_sections)
    for part_index, group in enumerate(grouped_sections, start=1):
        chunk_parts = [str(section["text"]) for section in group]
        if part_index == 1 and preamble:
            chunk_parts.insert(0, preamble)
        chunks.append(
            MarkdownPageChunk(
                md_text="\n\n".join(chunk_parts),
                part_index=part_index,
                part_count=part_count,
                start_page=int(group[0]["page_number"]),
                end_page=int(group[-1]["page_number"]),
                total_pages=total_pages,
            )
        )
    return chunks


def format_split_title(
    title: str,
    chunk: MarkdownPageChunk,
    split_title_template: str,
) -> str:
    return sanitize_title(
        split_title_template.format(
            title=title,
            part=chunk.part_index,
            total=chunk.part_count,
            start_page=chunk.start_page,
            end_page=chunk.end_page,
        )
    )


def _normalize_markdown_source(markdown: str) -> str:
    if not markdown:
        return markdown

    escaped_newline_count = len(_ESCAPED_NEWLINE_RE.findall(markdown))
    if escaped_newline_count < 2:
        return markdown

    real_newline_count = markdown.count("\n") + markdown.count("\r")
    if real_newline_count > escaped_newline_count and not _looks_like_escaped_markdown(markdown):
        return markdown

    normalized = _ESCAPED_NEWLINE_RE.sub("\n", markdown)
    normalized = normalized.replace(r"\"", '"')
    normalized = normalized.replace(r"\'", "'")
    normalized = normalized.replace(r"\t", "\t")
    return normalized


_ESCAPED_NEWLINE_RE = re.compile(r"\\+r\\+n|\\+n|\\+r")


def _looks_like_escaped_markdown(markdown: str) -> bool:
    return bool(
        re.search(
            r"\\+n(?:\\+n)?\s*(?:@page:\d+|#{1,6}\s|\*\*|[-*+]\s+|\d+[.)]\s+|\| |<table\b)",
            markdown,
            flags=re.I,
        )
    )


def add_styled_page_separators(markdown: str, *, total_page_count: int | None = None) -> str:
    page_matches = list(re.finditer(r"@page:(\d+)", markdown))
    if not page_matches:
        return markdown

    processed: list[str] = []
    display_total_pages = total_page_count or len(page_matches)
    for index, match in enumerate(page_matches):
        page_number = match.group(1)
        content_start = match.end()
        content_end = page_matches[index + 1].start() if index + 1 < len(page_matches) else len(markdown)
        page_content = markdown[content_start:content_end].strip()
        processed.append(
            '<hr style="margin: 0;" />\n'
            '<div style="margin: 0; padding: 0; text-align: center; '
            'font-weight: bold; color: #333; line-height: 1.2;">'
            f"Page: {page_number}/{display_total_pages}"
            "</div>"
        )
        if page_content:
            processed.append(page_content)
    return "\n\n".join(processed)


def convert_vlm_caption_blocks(
    markdown: str,
    *,
    start_tag: str,
    end_tag: str,
    extract_output_only: bool,
    mode: str,
    panel_title: str,
    expand_title: str,
    custom_template: str | None,
) -> str:
    text = markdown
    built_in_pairs = {
        ("<VLM image caption>", "</VLM image caption>"),
        ("(VLM image caption)", "(/VLM image caption)"),
    }
    pairs = [] if (start_tag, end_tag) in built_in_pairs else [(start_tag, end_tag)]
    seen: set[tuple[str, str]] = set()
    for caption_start, caption_end in pairs:
        if (caption_start, caption_end) in seen:
            continue
        seen.add((caption_start, caption_end))
        text = _convert_vlm_caption_pair(
            text,
            start_tag=caption_start,
            end_tag=caption_end,
            extract_output_only=extract_output_only,
            mode=mode,
            panel_title=panel_title,
            expand_title=expand_title,
            custom_template=custom_template,
        )
    for pattern in _builtin_vlm_caption_patterns():
        text = _convert_vlm_caption_pattern(
            text,
            pattern=pattern,
            extract_output_only=extract_output_only,
            mode=mode,
            panel_title=panel_title,
            expand_title=expand_title,
            custom_template=custom_template,
        )
    return text


def format_vlm_caption(
    caption_text: str,
    *,
    mode: str,
    panel_title: str,
    expand_title: str,
    custom_template: str | None,
) -> str:
    caption_text = (caption_text or "").strip()
    caption_html = blocks_to_storage_html(caption_text, heading_level_offset=1)
    caption_escaped = html.escape(caption_text)

    if mode == "panel_pre":
        return (
            '<ac:structured-macro ac:name="panel">\n'
            f'<ac:parameter ac:name="title">{html.escape(panel_title)}</ac:parameter>\n'
            "<ac:rich-text-body>\n"
            f"<pre>{caption_escaped}</pre>"
            "\n</ac:rich-text-body>\n"
            "</ac:structured-macro>"
        )
    if mode == "panel_markdown":
        return (
            '<ac:structured-macro ac:name="panel">\n'
            f'<ac:parameter ac:name="title">{html.escape(panel_title)}</ac:parameter>\n'
            "<ac:rich-text-body>\n"
            f"{caption_html}"
            "\n</ac:rich-text-body>\n"
            "</ac:structured-macro>"
        )
    if mode == "expand":
        return (
            '<ac:structured-macro ac:name="expand">\n'
            f'<ac:parameter ac:name="title">{html.escape(expand_title)}</ac:parameter>\n'
            "<ac:rich-text-body>\n"
            f"{caption_html}"
            "\n</ac:rich-text-body>\n"
            "</ac:structured-macro>"
        )
    if mode == "blockquote":
        return f"<blockquote>{caption_html}</blockquote>"
    if mode == "plain":
        return caption_html
    if mode == "custom":
        if not custom_template:
            raise ValueError("vlm_caption_format_mode='custom' requires vlm_caption_custom_template")
        return custom_template.format(
            title=html.escape(panel_title),
            expand_title=html.escape(expand_title),
            caption_html=caption_html,
            caption_escaped=caption_escaped,
        )
    raise ValueError(f"unsupported vlm_caption_format_mode: {mode}")


def convert_table_format_blocks(markdown: str) -> str:
    if not markdown:
        return markdown

    pattern = re.compile(r"```([A-Za-z0-9_-]+)[ \t]*\n(.*?)\n```", flags=re.S)

    def replace(match: re.Match[str]) -> str:
        language = match.group(1).strip().lower()
        body = match.group(2).strip()
        if language == "json":
            return _format_json_storage_block(body)
        if language == "toon":
            return _format_toon_storage_block(body)
        if language == "html":
            return _format_html_storage_block(body)
        return match.group(0)

    return pattern.sub(replace, markdown)


def _format_json_storage_block(json_text: str) -> str:
    return (
        '\n<ac:structured-macro ac:name="code">\n'
        '<ac:parameter ac:name="language">json</ac:parameter>\n'
        f"<ac:plain-text-body><![CDATA[{_cdata_safe_text(json_text)}]]></ac:plain-text-body>\n"
        "</ac:structured-macro>\n"
    )


def _format_toon_storage_block(toon_text: str) -> str:
    escaped = html.escape(toon_text)
    return (
        '\n<ac:structured-macro ac:name="panel">\n'
        '<ac:parameter ac:name="title">TOON</ac:parameter>\n'
        "<ac:rich-text-body>\n"
        f"<pre>{escaped}</pre>\n"
        "</ac:rich-text-body>\n"
        "</ac:structured-macro>\n"
    )


def _format_html_storage_block(html_text: str) -> str:
    return f"\n{sanitize_table_html(html_text)}\n"


def _cdata_safe_text(text: str) -> str:
    return text.replace("]]>", "]]]]><![CDATA[>")


def blocks_to_storage_html(markdown: str, *, heading_level_offset: int = 0) -> str:
    lines = markdown.splitlines()
    parts: list[str] = []
    paragraph: list[str] = []
    in_code = False
    code_lines: list[str] = []
    i = 0

    def flush_paragraph() -> None:
        if paragraph:
            parts.append("<p>" + "<br />".join(_inline(line) for line in paragraph) + "</p>")
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                parts.append("<pre>" + html.escape("\n".join(code_lines)) + "</pre>")
                code_lines.clear()
                in_code = False
            else:
                flush_paragraph()
                in_code = True
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        if re.fullmatch(r"[-*_]\s*[-*_]\s*[-*_][\s\-*_]*", stripped):
            flush_paragraph()
            parts.append("<hr />")
            i += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            level = min(len(heading.group(1)) + heading_level_offset, 6)
            parts.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        table = _collect_markdown_table(lines, i)
        if table is not None:
            flush_paragraph()
            table_html, next_i = table
            parts.append(table_html)
            i = next_i
            continue

        if re.match(r"^[-*+]\s+", stripped):
            flush_paragraph()
            items: list[str] = []
            while i < len(lines) and re.match(r"^[-*+]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*+]\s+", "", lines[i].strip()))
                i += 1
            parts.append("<ul>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ul>")
            continue

        if re.match(r"^\d+[.)]\s+", stripped):
            flush_paragraph()
            items = []
            while i < len(lines) and re.match(r"^\d+[.)]\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+[.)]\s+", "", lines[i].strip()))
                i += 1
            parts.append("<ol>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ol>")
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            parts.append("<blockquote><p>" + "<br />".join(_inline(line) for line in quote_lines) + "</p></blockquote>")
            continue

        if _is_raw_storage_line(stripped):
            flush_paragraph()
            parts.append(stripped)
            i += 1
            continue

        if _is_storage_placeholder(stripped):
            flush_paragraph()
            parts.append(stripped)
            i += 1
            continue

        paragraph.append(line)
        i += 1

    flush_paragraph()
    if in_code:
        parts.append("<pre>" + html.escape("\n".join(code_lines)) + "</pre>")
    return "\n".join(parts) if parts else "<p></p>"


def _convert_vlm_caption_pair(
    markdown: str,
    *,
    start_tag: str,
    end_tag: str,
    extract_output_only: bool,
    mode: str,
    panel_title: str,
    expand_title: str,
    custom_template: str | None,
) -> str:
    pattern = re.compile(re.escape(start_tag) + r"\s*(.*?)\s*" + re.escape(end_tag), flags=re.S)

    def replace(match: re.Match[str]) -> str:
        caption_text = match.group(1).strip()
        if extract_output_only:
            caption_text = _extract_caption_output_only(caption_text)
        return format_vlm_caption(
            caption_text,
            mode=mode,
            panel_title=panel_title,
            expand_title=expand_title,
            custom_template=custom_template,
        )

    return pattern.sub(replace, markdown)


def _builtin_vlm_caption_patterns() -> tuple[re.Pattern[str], ...]:
    return tuple(
        _compile_vlm_caption_pattern(start_tag, end_tag)
        for start_tag, end_tag in (
            ("<VLM image caption>", "</VLM image caption>"),
            ("(VLM image caption)", "(/VLM image caption)"),
        )
    )


def _compile_vlm_caption_pattern(start_tag: str, end_tag: str) -> re.Pattern[str]:
    optional_opening_fence = r"(?:^[ \t]*```[^\S\r\n]*(?:\r?\n)|(?<=\n)[ \t]*```[^\S\r\n]*(?:\r?\n))?"
    optional_closing_fence = r"[ \t]*(?:\r?\n[ \t]*```)?"
    return re.compile(
        optional_opening_fence
        + r"[ \t]*"
        + re.escape(start_tag)
        + r"\s*(.*?)\s*"
        + re.escape(end_tag)
        + optional_closing_fence,
        flags=re.S,
    )


def _convert_vlm_caption_pattern(
    markdown: str,
    *,
    pattern: re.Pattern[str],
    extract_output_only: bool,
    mode: str,
    panel_title: str,
    expand_title: str,
    custom_template: str | None,
) -> str:
    def replace(match: re.Match[str]) -> str:
        caption_text = match.group(1).strip()
        if extract_output_only:
            caption_text = _extract_caption_output_only(caption_text)
        return format_vlm_caption(
            caption_text,
            mode=mode,
            panel_title=panel_title,
            expand_title=expand_title,
            custom_template=custom_template,
        )

    return pattern.sub(replace, markdown)


def _extract_caption_output_only(caption_text: str) -> str:
    json_output_match = re.search(r'"output"\s*:\s*"((?:[^"\\]|\\.)*)"', caption_text, re.S)
    if json_output_match:
        try:
            output_text = json.loads(f'"{json_output_match.group(1)}"').strip()
        except (TypeError, json.JSONDecodeError):
            output_text = json_output_match.group(1).strip()
        if output_text:
            return output_text

    labeled_output_match = re.search(r"(?:^|\n)(?:@출력:|출력:)\s*(.*)", caption_text, re.S)
    if labeled_output_match and labeled_output_match.group(1).strip():
        return labeled_output_match.group(1).strip()
    return caption_text


def _collect_markdown_table(lines: list[str], start: int) -> tuple[str, int] | None:
    if start + 1 >= len(lines):
        return None
    if "|" not in lines[start] or not _is_table_separator(lines[start + 1]):
        return None
    table_lines: list[str] = []
    i = start
    while i < len(lines) and "|" in lines[i]:
        table_lines.append(lines[i])
        i += 1
    rows = [_split_table_row(line) for line in table_lines]
    width = max((len(row) for row in rows), default=0)
    if width == 0:
        return None
    header = _pad_row(rows[0], width)
    body = [_pad_row(row, width) for row in rows[2:]]
    table_html = ["<table><thead><tr>"]
    table_html.extend(f"<th>{_table_cell_inline(cell)}</th>" for cell in header)
    table_html.append("</tr></thead><tbody>")
    for row in body:
        table_html.append("<tr>")
        table_html.extend(f"<td>{_table_cell_inline(cell)}</td>" for cell in row)
        table_html.append("</tr>")
    table_html.append("</tbody></table>")
    return "".join(table_html), i


def _is_raw_storage_line(line: str) -> bool:
    return line.startswith(
        (
            "<ac:",
            "</ac:",
            "<ri:",
            "</ri:",
            "<hr",
            "<div",
            "</div",
            "<table",
            "</table",
            "<ul",
            "</ul",
            "<ol",
            "</ol",
            "<li",
            "</li",
            "<p",
            "</p",
            "<h1",
            "<h2",
            "<h3",
            "<h4",
            "<h5",
            "<h6",
            "</h1",
            "</h2",
            "</h3",
            "</h4",
            "</h5",
            "</h6",
            "<thead",
            "</thead",
            "<tbody",
            "</tbody",
            "<tr",
            "</tr",
            "<td",
            "</td",
            "<th",
            "</th",
            "<blockquote",
            "</blockquote",
            "<pre",
            "</pre",
        )
    )


_STORAGE_PLACEHOLDER_PREFIX = "@@CONFLUENCE_STORAGE_BLOCK_"
_STORAGE_PLACEHOLDER_RE = re.compile(r"@@CONFLUENCE_STORAGE_BLOCK_(\d+)@@")


def _protect_storage_blocks(markdown: str) -> tuple[str, list[str]]:
    storage_blocks: list[str] = []

    def protect(match: re.Match[str]) -> str:
        token = f"{_STORAGE_PLACEHOLDER_PREFIX}{len(storage_blocks)}@@"
        storage_blocks.append(match.group(0))
        return f"\n{token}\n"

    patterns = (
        r"<ac:structured-macro\b.*?</ac:structured-macro>",
        r"<ac:image\b.*?</ac:image>",
        r"<table\b.*?</table>",
    )
    protected = markdown
    for pattern in patterns:
        protected = re.sub(pattern, protect, protected, flags=re.S)
    return protected, storage_blocks


def _restore_storage_blocks(body_storage: str, storage_blocks: list[str]) -> str:
    def restore(match: re.Match[str]) -> str:
        index = int(match.group(1))
        try:
            return storage_blocks[index]
        except IndexError:
            return match.group(0)

    restored = body_storage
    for _ in range(len(storage_blocks) + 1):
        next_restored = _STORAGE_PLACEHOLDER_RE.sub(restore, restored)
        if next_restored == restored:
            break
        restored = next_restored
    return restored


def _is_storage_placeholder(line: str) -> bool:
    return _STORAGE_PLACEHOLDER_RE.fullmatch(line) is not None


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _pad_row(row: list[str], width: int) -> list[str]:
    return (row + [""] * width)[:width]


def _is_table_separator(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def _inline(text: str) -> str:
    text = _unescape_markdown_punctuation(text)
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def _unescape_markdown_punctuation(text: str) -> str:
    return re.sub(r"\\+([\\`*_{}\[\]()#+\-.!|>])", r"\1", text)


def _table_cell_inline(text: str) -> str:
    rendered = _inline(text)
    return re.sub(r"&lt;br\s*/?&gt;", "<br />", rendered, flags=re.I)


def _resolve_local_path(raw_path: str, *, markdown_base_dir: Path, output_dir: Path) -> Path | None:
    cleaned = raw_path.split("#", 1)[0].split("?", 1)[0].strip()
    if not cleaned or Path(cleaned).is_absolute() or ".." in Path(cleaned).parts:
        return None
    candidates = [
        markdown_base_dir / cleaned,
        output_dir / cleaned,
        output_dir / "imgs" / Path(cleaned).name,
        output_dir / "table_imgs" / Path(cleaned).name,
    ]
    allowed_roots = (markdown_base_dir.resolve(), output_dir.resolve())
    for candidate in candidates:
        resolved = candidate.resolve()
        if (
            candidate.exists()
            and candidate.is_file()
            and any(resolved.is_relative_to(root) for root in allowed_roots)
            and resolved.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            and resolved.stat().st_size <= 10 * 1024 * 1024
        ):
            return resolved
    return None
