from __future__ import annotations

import re

from core.domain.document.models import PageDTO
from core.domain.layout.models import LayoutBlockDTO
from core.domain.markdown.models import PageFailureDTO

_METADATA_KEY = "page_failures"


def record_page_failure(
    page: PageDTO, stage: str, error: Exception | str
) -> PageFailureDTO:
    failure = PageFailureDTO(stage=stage, reason=_reason(error))
    failures = page_failures(page)
    if failure not in failures:
        page.metadata[_METADATA_KEY] = [*failures, failure]
    return failure


def page_failures(page: PageDTO) -> list[PageFailureDTO]:
    value = page.metadata.get(_METADATA_KEY, [])
    return (
        [failure for failure in value if isinstance(failure, PageFailureDTO)]
        if isinstance(value, list)
        else []
    )


def record_block_failures(
    page: PageDTO, blocks: list[LayoutBlockDTO], stage: str
) -> bool:
    failed = False
    for block in blocks:
        error = block.metadata.get(f"{stage}_error")
        if error:
            record_page_failure(page, stage, f"block {block.block_id}: {error}")
            failed = True
    return failed


def failure_markdown(failures: list[PageFailureDTO]) -> str:
    return "\n".join(failure.render_markdown() for failure in failures)


def _reason(error: Exception | str) -> str:
    if isinstance(error, Exception):
        return "processing failed (" + type(error).__name__ + ")"
    message = (
        str(error).strip().splitlines()[0]
        if str(error).strip()
        else type(error).__name__
    )
    message = re.sub(
        r"([?&](?:key|api_key|token|access_token)=)[^&\s\"'<>)]*",
        r"\1<redacted>",
        message,
        flags=re.IGNORECASE,
    )
    return " ".join(message.split())
