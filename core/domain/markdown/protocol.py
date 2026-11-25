"""Host-owned structured Markdown wire protocol."""
from __future__ import annotations

import hashlib
import re

PROTOCOL_VERSION = "structured-markdown-1"
PROMPT_VERSION = "3"
VLM_CAPTION_START_TAG = "\n```vlm_image_caption"
VLM_CAPTION_END_TAG = "\n```\n"
STRUCTURED_PLACEHOLDER_RE = re.compile(
    r"^\[\[(?:TABLE_BLOCK:table_[0-9a-f]{16}|IMAGE_BLOCK:image_[0-9a-f]{16})\]\]$"
)
# Deliberately broader than the DTO validator, including unclosed/malformed tokens.
TABLE_REFERENCE_RE = re.compile(r"\[\[TABLE_BLOCK:[^\r\n]*?(?:\]\]|(?=\r?\n|$))")


def structured_placeholder(kind: str, document_id: str, page_no: int, block_id: str) -> str:
    if kind not in {"table", "image"}:
        raise ValueError("unsupported structured block kind")
    digest = hashlib.sha256(f"{document_id}\x1f{page_no}\x1f{block_id}".encode()).hexdigest()[:16]
    return f"[[{kind.upper()}_BLOCK:{kind}_{digest}]]"


EXAMPLE_TABLE_TOKENS = tuple(structured_placeholder("table", "example", 1, str(i)) for i in range(4))

