from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from core.domain.markdown.models import TableOutputFormat
from core.prompts.utils import render_table_html

_ALLOWED_TABLE_TAGS = {
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "caption",
    "colgroup",
    "col",
    "br",
}
_ALLOWED_TABLE_ATTRIBUTES = {"rowspan", "colspan", "scope", "style"}
_TABLE_FORMAT_ALIASES = {
    "md": TableOutputFormat.MARKDOWN,
    **{item.value: item for item in TableOutputFormat},
}


def parse_table_output_format(
    value: str | TableOutputFormat | None,
) -> TableOutputFormat:
    normalized = (
        (value.value if isinstance(value, TableOutputFormat) else value or "markdown")
        .strip()
        .lower()
    )
    try:
        return _TABLE_FORMAT_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported table_output_format: {value}") from exc


def sanitize_table_html(value: str) -> str:
    """Accept only a table fragment and its safe structural markup."""
    soup = BeautifulSoup(value or "", "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError("table VLM output must contain a <table> element")
    for tag in list(table.find_all(True)):
        if tag.name in {"script", "style", "iframe", "object", "embed"}:
            tag.decompose()
            continue
        if tag.name not in _ALLOWED_TABLE_TAGS:
            tag.unwrap()
            continue
        tag.attrs = {
            key: _safe_table_attribute(key, raw)
            for key, raw in tag.attrs.items()
            if key in _ALLOWED_TABLE_ATTRIBUTES
            and _safe_table_attribute(key, raw) is not None
        }
    table.attrs = {}
    sanitized = str(table).strip()
    if not re.search(r"<t[hd]\b", sanitized, flags=re.I):
        raise ValueError("table VLM output must contain at least one table cell")
    return sanitized


def render_validated_table(
    table_html: str,
    output_format: str | TableOutputFormat,
    *,
    nested_table_prefix: str | None = None,
) -> str:
    sanitized_html = sanitize_table_html(table_html)
    table_format = parse_table_output_format(output_format)
    rendered = render_table_html(
        sanitized_html, table_format.value, nested_table_prefix=nested_table_prefix
    ).strip()
    if not rendered:
        raise ValueError("validated table renderer returned an empty output")
    if table_format is TableOutputFormat.JSON:
        _validate_json_table_blocks(rendered)
    return rendered


def _safe_table_attribute(name: str, value: object) -> str | None:
    text = str(value).strip()
    if name == "style":
        safe = []
        for declaration in text.split(";"):
            prop, sep, color = declaration.partition(":")
            color = color.strip().lower()
            if (
                sep
                and prop.strip().lower() in {"color", "background-color"}
                and re.fullmatch(
                    r"#[0-9a-f]{3}(?:[0-9a-f]{3})?|black|white|red|green|blue|yellow|orange|purple|gray|grey|pink|brown|transparent",
                    color,
                )
            ):
                safe.append(prop.strip().lower() + ": " + color)
        return "; ".join(safe) or None
    if name in {"rowspan", "colspan"}:
        try:
            numeric = int(text)
        except ValueError:
            return None
        return str(numeric) if 1 <= numeric <= 1000 else None
    return (
        text.lower()
        if name == "scope" and text.lower() in {"row", "col", "rowgroup", "colgroup"}
        else None
    )


def _validate_json_table_blocks(rendered: str) -> None:
    blocks = [
        block
        for block in re.findall(r"```json\s*(.*?)\s*```", rendered, flags=re.S)
        if block.strip()
    ]
    if not blocks:
        blocks = [rendered]
    for block in blocks:
        parsed = json.loads(block)
        table = parsed.get("table") if isinstance(parsed, dict) else None
        if not isinstance(table, dict) or not isinstance(table.get("rows"), list):
            raise ValueError("table JSON output must contain table.rows as a list")
