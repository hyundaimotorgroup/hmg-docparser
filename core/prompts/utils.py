import json
import hashlib
import re
from typing import Optional, Dict, Any, Union
from bs4 import BeautifulSoup, NavigableString, Tag


from core.domain.markdown.protocol import VLM_CAPTION_START_TAG, VLM_CAPTION_END_TAG

def get_markdown_tables_in_text(input_text: str):
    # 마크다운 테이블 추출 정규식: |로 시작해서 줄바꿈 포함 행들이 반복되는 패턴
    pattern = r'(?:\|.*\|(?:\s*\n|\r\n))+'
    tables = re.findall(pattern, input_text)
    return [table.strip() for table in tables if table.strip()]


def sanitize_filename(title):
    """
    파일명으로 사용할 수 있도록 문자열을 정리합니다.
    공백, 대괄호[], 소괄호()를 포함한 특수문자를 언더스코어(_)로 바꿉니다.

    Args:
        title: 원본 제목 문자열

    Returns:
        str: 정리된 파일명
    """
    import re

    # 파일명으로 사용할 수 없는 문자, 공백, 및 대괄호/소괄호를 포함한 것들을 언더스코어로 변경
    # \s는 공백, 탭, 줄바꿈 등 모든 공백 문자를 의미합니다.
    sanitized = re.sub(r'[<>:"/\\|?*\[\]()\s]', '_', title)

    # 연속된 언더스코어 하나로 축소
    sanitized = re.sub(r'_+', '_', sanitized)

    # 맨 앞이나 뒤에 올 수 있는 언더스코어 제거
    sanitized = sanitized.strip('_')

    # 파일명 길이 제한 (OS 호환성을 위해)
    sanitized = sanitized[:100]

    return sanitized


def shorten_filename(filename: str, *, max_bytes: int = 180) -> str:
    encoded = filename.encode("utf-8")
    if len(encoded) <= max_bytes:
        return filename

    stem, extension = _split_filename(filename)
    digest = hashlib.sha1(encoded).hexdigest()[:12]
    reserved_bytes = len(f"_{digest}{extension}".encode("utf-8"))
    truncated_stem = truncate_utf8_bytes(stem, max_bytes=max_bytes - reserved_bytes).rstrip("._-")
    if not truncated_stem:
        truncated_stem = "file"
    return f"{truncated_stem}_{digest}{extension}"


def truncate_utf8_bytes(text: str, *, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""

    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text

    truncated = encoded[:max_bytes]
    while truncated:
        try:
            return truncated.decode("utf-8")
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return ""


def _split_filename(filename: str) -> tuple[str, str]:
    dot_index = filename.rfind(".")
    if dot_index <= 0:
        return filename or "file", ""
    return filename[:dot_index], filename[dot_index:]

def strip_code_fence(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r"^```(?:json|JSON|python|Python|html|HTML)?\s*", "", text)
    if text.endswith("```"):
        text = text[:-3].rstrip()
    return text.strip()


def normalize_escaped_html(text: str) -> str:
    if not text:
        return text
    normalized = text.replace(r"\"", '"')
    if "\\n" in normalized and "\n" not in normalized:
        normalized = normalized.replace("\\n", "\n")
    if "\\t" in normalized and "\t" not in normalized:
        normalized = normalized.replace("\\t", "\t")
    return normalized


def extract_balanced_json_object(text: str) -> Optional[str]:
    if not text:
        return None

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for idx in range(start, len(text)):
        ch = text[idx]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]

    return None

def extract_json_string_value(text: str, key: str) -> Optional[str]:
    if not text:
        return None

    key_pattern = f'"{key}"'
    key_pos = text.find(key_pattern)
    if key_pos == -1:
        return None

    colon_pos = text.find(":", key_pos + len(key_pattern))
    if colon_pos == -1:
        return None

    quote_pos = text.find('"', colon_pos + 1)
    if quote_pos == -1:
        return None

    result_chars = []
    escape = False

    for idx in range(quote_pos + 1, len(text)):
        ch = text[idx]

        if escape:
            result_chars.append(ch)
            escape = False
            continue

        if ch == "\\":
            result_chars.append(ch)
            escape = True
            continue

        if ch == '"' and _looks_like_json_value_end(text, idx):
            raw_value = "".join(result_chars)
            try:
                return json.loads(f'"{raw_value}"')
            except Exception:
                return raw_value

        result_chars.append(ch)

    raw_value = "".join(result_chars)
    try:
        return json.loads(f'"{raw_value}"')
    except Exception:
        return raw_value


def _looks_like_json_value_end(text: str, quote_idx: int) -> bool:
    """Detect value-ending quotes in malformed JSON-ish model responses.

    Some VLMs put raw HTML attributes such as colspan="4" inside a JSON string
    without escaping the quotes. Treat a quote as closing only when the
    following non-space text looks like a JSON key boundary or object end.
    """
    tail = text[quote_idx + 1 :].lstrip()
    if not tail:
        return True
    if tail[0] in "}]":
        return True
    return re.match(r',\s*"[^"]+"\s*:', tail) is not None

def extract_output_like_text(text: str) -> str:
    if not text:
        return ""

    text = strip_code_fence(text)

    output_match = re.search(r'@출력:\s*(.*)', text, re.DOTALL)
    if output_match:
        return output_match.group(1).strip()

    output_match = re.search(r'출력:\s*(.*)', text, re.DOTALL)
    if output_match:
        return output_match.group(1).strip()

    json_output_match = re.search(r'"output"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
    if json_output_match:
        try:
            return bytes(json_output_match.group(1), "utf-8").decode("unicode_escape").strip()
        except Exception:
            return json_output_match.group(1).strip()

    if "| " in text or text.startswith("|"):
        table_start = text.find("|")
        if table_start != -1:
            return text[table_start:].strip()

    if "<table" in text.lower():
        html_start = text.lower().find("<table")
        return text[html_start:].strip()

    return text.strip()

def normalize_structured_response(parsed: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        return {"reasoning": "", "output": str(parsed)}

    if "output" in parsed:
        if "reasoning" not in parsed:
            parsed["reasoning"] = ""
        return parsed

    if "raw" in parsed and isinstance(parsed["raw"], str):
        recovered_output = extract_output_like_text(parsed["raw"])
        return {
            "reasoning": parsed.get("reasoning", ""),
            "output": recovered_output,
            **parsed
        }

    return {
        "reasoning": parsed.get("reasoning", ""),
        "output": "",
        **parsed
    }


def _normalize_result(parsed_data: Union[Dict, list, Any], raw_text: str) -> Dict[str, Any]:
    """
    파싱된 데이터가 리스트면 첫 번째 요소를 꺼내고,
    딕셔너리 형태가 되도록 정규화한 뒤 기존 normalize 함수를 호출합니다.
    """
    # 1. 리스트인 경우 첫 번째 요소 추출
    if isinstance(parsed_data, list):
        parsed_data = parsed_data[0] if parsed_data else {}

    # 2. 딕셔너리가 아닌 경우 강제 변환
    if not isinstance(parsed_data, dict):
        return {"reasoning": "", "output": str(parsed_data)}

    # 3. 기존 구조화 정규화 함수 호출
    return normalize_structured_response(parsed_data, raw_text)


def _extract_json_snippet(text: str) -> Optional[str]:
    """
    문자열에서 가장 먼저 발견되는 JSON 객체({}) 또는 배열([])을 추출합니다.
    스택을 사용하여 중첩 구조를 처리합니다.
    """
    stack = []
    start_index = -1

    # JSON 시작/종료 괄호 매핑
    brackets = {'{': '}', '[': ']'}

    for i, char in enumerate(text):
        if char in brackets:
            if not stack:
                start_index = i  # 최상위 괄호 시작
            stack.append(brackets[char])  # 닫는 괄호 기대값 저장

        elif char in brackets.values():
            if stack and stack[-1] == char:
                stack.pop()
                # 스택이 비워지면 하나의 온전한 JSON 블록이 완성된 것
                if not stack:
                    return text[start_index: i + 1]
            else:
                # 괄호 짝이 안 맞으면 무시하거나 초기화 (여기선 단순 무시)
                pass

    return None


def recover_structured_response(ret_txt: str) -> Dict[str, Any]:
    cleaned_txt = strip_code_fence(ret_txt)

    # 1단계: 전체 텍스트를 바로 JSON 파싱 시도
    try:
        parsed = json.loads(cleaned_txt)
        return _normalize_result(parsed, cleaned_txt)
    except json.JSONDecodeError:
        pass

    # 2단계: 텍스트 내에서 JSON 부분만 추출하여 파싱 시도 ({...} 또는 [...])
    json_snippet = _extract_json_snippet(cleaned_txt)
    if json_snippet:
        try:
            parsed = json.loads(json_snippet)
            return _normalize_result(parsed, cleaned_txt)
        except json.JSONDecodeError:
            print(f"[JSON Parsing Error] Snippet extraction failed. Raw: {cleaned_txt[:100]}...")

    # 3단계: Fallback (정규식 등을 이용한 강제 키-값 추출)
    reasoning = extract_json_string_value(cleaned_txt, "reasoning") or ""
    output = extract_json_string_value(cleaned_txt, "output") or extract_output_like_text(cleaned_txt)

    return {
        "error": "json parsing failed",
        "raw": cleaned_txt,
        "reasoning": reasoning.strip(),
        "output": output.strip()
    }


def _html_table_to_markdown_flat(table_html: str) -> str:
    def _strip_code_fence(text: str) -> str:
        text = (text or "").strip()
        text = re.sub(r"^\s*```[A-Za-z]*\s*", "", text)
        if text.endswith("```"):
            text = text[:-3].rstrip()
        return text.strip()

    def _fallback_text(text: str) -> str:
        return _strip_code_fence(text)

    def _cell_text(cell) -> str:
        cell_soup = BeautifulSoup(str(cell), "html.parser")
        cell_root = cell_soup.find(cell.name) or cell_soup
        for br in cell_root.find_all("br"):
            br.replace_with(NavigableString("<br>"))
        text = cell_root.get_text(separator="", strip=False)
        text = re.sub(r"\s*<br>\s*", "<br>", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def _escape_md(text: str) -> str:
        if text is None:
            return ""
        return str(text).replace("|", r"\|")

    def _normalize_row(row, width: int):
        if len(row) < width:
            return row + [""] * (width - len(row))
        return row[:width]

    def _compress_header_path(values):
        compressed = []
        for value in values:
            if not value:
                continue
            if not compressed or compressed[-1] != value:
                compressed.append(value)
        return "_".join(compressed) if compressed else ""

    def _extract_table_grid(table_tag):
        all_trs = table_tag.find_all("tr")
        if not all_trs:
            return [], []

        header_row_indices = set()
        thead = table_tag.find("thead")
        if thead is not None:
            thead_trs = thead.find_all("tr")
            for idx, tr in enumerate(all_trs):
                if tr in thead_trs:
                    header_row_indices.add(idx)
        else:
            for idx, tr in enumerate(all_trs):
                cells = tr.find_all(["th", "td"], recursive=False)
                if cells and all(cell.name == "th" for cell in cells):
                    header_row_indices.add(idx)
                else:
                    break

        grid = []
        occupied = {}

        for row_idx, tr in enumerate(all_trs):
            while len(grid) <= row_idx:
                grid.append([])

            col_idx = 0
            cells = tr.find_all(["th", "td"], recursive=False)

            for cell in cells:
                while (row_idx, col_idx) in occupied:
                    col_idx += 1

                text = _cell_text(cell)
                rowspan = max(1, int(cell.get("rowspan", 1) or 1))
                colspan = max(1, int(cell.get("colspan", 1) or 1))

                for dr in range(rowspan):
                    target_row = row_idx + dr
                    while len(grid) <= target_row:
                        grid.append([])

                    for dc in range(colspan):
                        target_col = col_idx + dc
                        while len(grid[target_row]) <= target_col:
                            grid[target_row].append("")
                        grid[target_row][target_col] = text
                        occupied[(target_row, target_col)] = True

                col_idx += colspan

        width = max((len(row) for row in grid), default=0)
        grid = [_normalize_row(row, width) for row in grid]

        header_rows = []
        body_rows = []
        for idx, row in enumerate(grid):
            if idx in header_row_indices:
                header_rows.append(row)
            else:
                body_rows.append(row)

        return header_rows, body_rows

    def _table_tag_to_markdown(table_tag) -> str:
        header_rows, body_rows = _extract_table_grid(table_tag)

        if not header_rows and not body_rows:
            return ""

        if not header_rows and body_rows:
            header = [f"col_{i+1}" for i in range(len(body_rows[0]))]
        elif len(header_rows) == 1:
            header = header_rows[0]
        else:
            width = max((len(row) for row in header_rows), default=0)
            header = []
            for col_idx in range(width):
                path_values = []
                for row in header_rows:
                    value = row[col_idx] if col_idx < len(row) else ""
                    path_values.append(value)
                header.append(_compress_header_path(path_values))

        width = max(
            len(header),
            max((len(row) for row in body_rows), default=0),
        )
        if width <= 0:
            return ""

        header = _normalize_row(header, width)
        body_rows = [_normalize_row(row, width) for row in body_rows]

        lines = []
        lines.append("| " + " | ".join(_escape_md(x) for x in header) + " |")
        lines.append("| " + " | ".join(["---"] * width) + " |")

        for row in body_rows:
            lines.append("| " + " | ".join(_escape_md(x) for x in row) + " |")

        return "\n".join(lines).strip()

    def _node_to_markdown_parts(node) -> list[str]:
        if isinstance(node, NavigableString):
            text = str(node).strip()
            return [text] if text else []
        if not isinstance(node, Tag):
            return []
        if node.name in {"script", "style"}:
            return []
        if node.name == "table":
            markdown = _table_tag_to_markdown(node)
            return [markdown] if markdown else []
        if node.find("table") is not None:
            parts = []
            for child in node.children:
                parts.extend(_node_to_markdown_parts(child))
            return parts

        text = node.get_text(separator=" ", strip=True)
        text = re.sub(r"[ \t]+", " ", text).strip()
        return [text] if text else []

    original_text = normalize_escaped_html(_fallback_text(table_html))

    try:
        soup = BeautifulSoup(original_text, "html.parser")
        if soup.find("table") is None:
            return original_text

        container = soup.body if soup.body is not None else soup
        parts = []
        for child in container.children:
            parts.extend(_node_to_markdown_parts(child))
        markdown_text = "\n\n".join(part for part in parts if part).strip()
        return markdown_text if markdown_text else original_text

    except Exception:
        return original_text


def html_table_to_markdown(
    table_html: str,
    *,
    nested_table_prefix: str | None = None,
) -> str:
    """Render HTML tables as Markdown, separating nested tables recursively."""
    return _render_html_tables_with_nested_sections(
        table_html,
        render_table=_html_table_to_markdown_flat,
        nested_table_prefix=nested_table_prefix,
    )


def normalize_table_output_format(value: str | None) -> str:
    normalized = (value or "markdown").strip().lower()
    if normalized in {"md", "markdown"}:
        return "markdown"
    if normalized == "html":
        return "html"
    if normalized == "json":
        return "json"
    if normalized == "toon":
        return "toon"
    raise ValueError(f"unsupported table_output_format: {value}")


def render_table_html(
    table_html: str,
    table_output_format: str,
    *,
    nested_table_prefix: str | None = None,
) -> str:
    output_format = normalize_table_output_format(table_output_format)
    if output_format == "html":
        return normalize_escaped_html(table_html).strip()

    if output_format == "markdown":
        return html_table_to_markdown(table_html, nested_table_prefix=nested_table_prefix)
    if output_format == "json":
        return convert_html_tables_to_json_text(
            table_html,
            nested_table_prefix=nested_table_prefix,
        )
    if output_format == "toon":
        json_text = convert_html_tables_to_json_text(
            table_html,
            nested_table_prefix=nested_table_prefix,
        )
        return convert_json_blocks_to_toon(json_text)

    raise ValueError(f"unsupported table_output_format: {table_output_format}")


def convert_html_tables_to_json_text(
    table_html: str,
    indent: int = 2,
    *,
    nested_table_prefix: str | None = None,
) -> str:
    """Convert HTML tables without flattening merged cells through Markdown.

    The public JSON shape remains ``table.meta`` and ``table.rows``.  Regular
    cells remain scalar values; only merged cells carry ``rowspan`` and/or
    ``colspan`` beside their value.  Header paths continue to become nested
    row keys, while generated ``col_1`` names stay literal keys.
    """
    def _render_json_table(table_html_fragment: str) -> str:
        soup = BeautifulSoup(table_html_fragment, "html.parser")
        table = soup.find("table")
        if table is None:
            return ""
        parsed = _html_table_to_json_object(table)
        if not parsed:
            return ""
        return "```json\n" + json.dumps(parsed, ensure_ascii=False, indent=indent) + "\n```"

    return _render_html_tables_with_nested_sections(
        table_html,
        render_table=_render_json_table,
        nested_table_prefix=nested_table_prefix,
    )


def _render_html_tables_with_nested_sections(
    table_html: str,
    *,
    render_table: Any,
    nested_table_prefix: str | None,
) -> str:
    """Separate nested HTML tables before rendering non-HTML table formats.

    Only the outer table keeps its position in the main output.  Nested tables
    are emitted immediately afterwards, while their former cells retain a
    stable reference that is intentionally not a structured-block placeholder.
    """
    original_text = normalize_escaped_html(strip_code_fence(table_html))
    try:
        soup = BeautifulSoup(original_text, "html.parser")
        root_tables = [
            table for table in soup.find_all("table") if table.find_parent("table") is None
        ]
    except Exception:
        return original_text.strip()

    if not root_tables:
        return original_text.strip()

    prefix = (nested_table_prefix or "table_nested").rstrip("_")
    nested_number = 0

    def _render_tree(table: Tag) -> str:
        nonlocal nested_number
        table_copy_soup = BeautifulSoup(str(table), "html.parser")
        table_copy = table_copy_soup.find("table")
        if table_copy is None:
            return ""

        nested_tables = [
            candidate
            for candidate in table_copy.find_all("table")
            if candidate.find_parent("table") is table_copy
        ]
        separated: list[tuple[int, Tag]] = []
        for nested_table in nested_tables:
            nested_number += 1
            number = nested_number
            nested_table.replace_with(
                NavigableString(f"[[NESTED_TABLE:{prefix}_{number}]]")
            )
            separated.append((number, nested_table))

        parts = [render_table(str(table_copy)).strip()]
        for number, nested_table in separated:
            nested_rendered = _render_tree(nested_table)
            if nested_rendered:
                parts.append(f"### 중첩표 {number}\n\n{nested_rendered}")
        return "\n\n".join(part for part in parts if part).strip()

    rendered = [_render_tree(table) for table in root_tables]
    return "\n\n".join(part for part in rendered if part).strip() or original_text.strip()


def _html_table_to_json_object(table_tag: Tag) -> dict[str, object]:
    rows = _html_direct_table_rows(table_tag)
    if not rows:
        return {}

    header_row_indices = _html_header_row_indices(table_tag, rows)
    cells_by_row, column_count = _html_table_cells(rows)
    if column_count == 0:
        return {}

    column_paths = _html_header_paths(
        cells_by_row,
        header_row_indices=header_row_indices,
        column_count=column_count,
    )
    records: list[dict[str, object]] = []
    for row_idx, cells in enumerate(cells_by_row):
        if row_idx in header_row_indices:
            continue
        record: dict[str, object] = {}
        for cell in cells:
            path = column_paths[cell["column"]]
            value: object = cell["value"]
            if cell["rowspan"] > 1 or cell["colspan"] > 1:
                value = {"value": value}
                if cell["rowspan"] > 1:
                    value["rowspan"] = cell["rowspan"]
                if cell["colspan"] > 1:
                    value["colspan"] = cell["colspan"]
            _set_nested_value(record, path, value)
        if _has_non_empty_value(record):
            records.append(record)

    return {"table": {"meta": "", "rows": records}}


def _html_header_row_indices(table_tag: Tag, rows: list[Tag]) -> set[int]:
    thead = table_tag.find("thead")
    if thead is not None:
        header_rows = set(thead.find_all("tr"))
        return {idx for idx, row in enumerate(rows) if row in header_rows}

    indices = set()
    for idx, row in enumerate(rows):
        cells = row.find_all(["th", "td"], recursive=False)
        if cells and all(cell.name == "th" for cell in cells):
            indices.add(idx)
        else:
            break
    return indices


def _html_direct_table_rows(table_tag: Tag) -> list[Tag]:
    """Return rows owned by ``table_tag``, excluding rows of nested tables."""
    return [
        row
        for row in table_tag.find_all("tr")
        if row.find_parent("table") is table_tag
    ]


def _html_table_cells(rows: list[Tag]) -> tuple[list[list[dict[str, object]]], int]:
    occupied: dict[tuple[int, int], dict[str, object]] = {}
    rows_with_cells: list[list[dict[str, object]]] = []
    column_count = 0

    for row_idx, row in enumerate(rows):
        parsed_cells: list[dict[str, object]] = []
        column = 0
        for cell_tag in row.find_all(["th", "td"], recursive=False):
            while (row_idx, column) in occupied:
                column += 1
            rowspan = _html_span(cell_tag, "rowspan")
            colspan = _html_span(cell_tag, "colspan")
            cell = {
                "column": column,
                "rowspan": rowspan,
                "colspan": colspan,
                "value": _html_cell_text(cell_tag),
            }
            parsed_cells.append(cell)
            for row_offset in range(rowspan):
                for column_offset in range(colspan):
                    occupied[(row_idx + row_offset, column + column_offset)] = cell
            column += colspan
        rows_with_cells.append(parsed_cells)
        column_count = max(column_count, column)
    return rows_with_cells, column_count


def _html_header_paths(
    cells_by_row: list[list[dict[str, object]]],
    *,
    header_row_indices: set[int],
    column_count: int,
) -> list[list[str]]:
    if not header_row_indices:
        return [[f"col_{column + 1}"] for column in range(column_count)]

    paths: list[list[str]] = []
    ordered_headers = sorted(header_row_indices)
    for column in range(column_count):
        values: list[str] = []
        seen_cells: set[int] = set()
        for row_idx in ordered_headers:
            for cell in cells_by_row[row_idx]:
                start = int(cell["column"])
                end = start + int(cell["colspan"])
                if start <= column < end and id(cell) not in seen_cells:
                    seen_cells.add(id(cell))
                    value = str(cell["value"]).strip()
                    if value and (not values or values[-1] != value):
                        values.append(value)
                    break
        paths.append(values or [f"col_{column + 1}"])

    used_paths: dict[tuple[str, ...], int] = {}
    for column, path in enumerate(paths):
        path_key = tuple(path)
        used_paths[path_key] = used_paths.get(path_key, 0) + 1
        if used_paths[path_key] > 1:
            paths[column] = [*path, f"col_{column + 1}"]
    return paths


def _html_span(cell: Tag, name: str) -> int:
    try:
        return max(1, int(cell.get(name, 1) or 1))
    except (TypeError, ValueError):
        return 1


def _html_cell_text(cell: Tag) -> str:
    cell_soup = BeautifulSoup(str(cell), "html.parser")
    cell_root = cell_soup.find(cell.name) or cell_soup
    for br in cell_root.find_all("br"):
        br.replace_with(NavigableString("<br>"))
    text = cell_root.get_text(separator="", strip=False)
    text = re.sub(r"\s*<br>\s*", "<br>", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def convert_markdown_tables_to_json_text(markdown_text: str, indent: int = 2) -> str:
    lines = markdown_text.splitlines(True)
    out_lines: list[str] = []
    in_code_fence = False
    heading_stack: list[tuple[int, str]] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.lstrip().startswith("```"):
            in_code_fence = not in_code_fence
            out_lines.append(line)
            i += 1
            continue

        if in_code_fence:
            out_lines.append(line)
            i += 1
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line.strip())
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            out_lines.append(line)
            i += 1
            continue

        if _is_markdown_table_line(line):
            table_lines: list[str] = []
            j = i
            while j < len(lines) and _is_markdown_table_line(lines[j]) and lines[j].strip():
                table_lines.append(lines[j].rstrip("\r\n"))
                j += 1

            meta = " -> ".join(title for _, title in heading_stack).strip()
            parsed = _markdown_table_to_json_object(table_lines, meta=meta)
            if parsed:
                out_lines.append("```json\n")
                out_lines.append(json.dumps(parsed, ensure_ascii=False, indent=indent) + "\n")
                out_lines.append("```\n")
            else:
                out_lines.extend(_ensure_line_end(line) for line in table_lines)

            i = j
            continue

        out_lines.append(line)
        i += 1

    return "".join(out_lines).strip()


def convert_json_blocks_to_toon(markdown_text: str, validate_roundtrip: bool = False) -> str:
    try:
        from py_toon_format import decode, encode
    except ImportError as exc:
        raise RuntimeError(
            "table_output_format='toon' requires py_toon_format. "
            "Install requirements.txt or run: pip install py_toon_format"
        ) from exc

    json_block_re = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)

    def repl(match: re.Match[str]) -> str:
        json_body = match.group(1)
        try:
            obj = _normalize_toon_object(json.loads(json_body))
            toon_string = encode(obj)
            if validate_roundtrip:
                decode(toon_string)
        except Exception:
            return match.group(0)
        return f"```toon\n{toon_string}\n```"

    return json_block_re.sub(repl, markdown_text).strip()


def _normalize_toon_object(value: object, *, key: str | None = None) -> object:
    if isinstance(value, str):
        return re.sub(r"\s*\r?\n\s*", "<br>", value)
    if isinstance(value, list):
        items = [_normalize_toon_object(item) for item in value]
        if key == "rows" and any(isinstance(item, dict) for item in items):
            return {
                f"row_{idx}": item
                for idx, item in enumerate(items, start=1)
            }
        return items
    if isinstance(value, dict):
        return {
            str(child_key): _normalize_toon_object(child, key=str(child_key))
            for child_key, child in value.items()
        }
    return value


def _is_markdown_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.count("|") >= 1 and not stripped.startswith("```")


def _is_markdown_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith(r"\|"):
        stripped = stripped[:-1]

    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in stripped:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    cells.append("".join(current).strip())
    return cells


def _markdown_table_to_json_object(table_lines: list[str], *, meta: str) -> dict[str, object]:
    rows = [_split_markdown_row(line) for line in table_lines if line.strip()]
    if len(rows) < 2 or not _is_markdown_separator_row(rows[1]):
        return {}

    header = rows[0]
    records: list[dict[str, object]] = []
    for row in rows[2:]:
        normalized_row = _normalize_markdown_cells(row, len(header))
        record: dict[str, object] = {}
        for column_name, value in zip(header, normalized_row):
            column_name = column_name.strip()
            if not column_name:
                continue
            _set_nested_value(record, _path_from_merged_header(column_name), value.strip())

        if _has_non_empty_value(record):
            records.append(record)

    return {"table": {"meta": meta, "rows": records}}


def _normalize_markdown_cells(cells: list[str], width: int) -> list[str]:
    if len(cells) < width:
        return cells + [""] * (width - len(cells))
    return cells[:width]


def _path_from_merged_header(text: str) -> list[str]:
    return [part.strip() for part in text.split("_") if part.strip()]


def _set_nested_value(root: dict[str, object], path: list[str], value: object) -> None:
    if not path:
        return
    current = root
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[path[-1]] = value


def _has_non_empty_value(value: object) -> bool:
    if isinstance(value, dict):
        return any(_has_non_empty_value(child) for child in value.values())
    return value != ""


def _ensure_line_end(line: str) -> str:
    return line if line.endswith("\n") else f"{line}\n"
