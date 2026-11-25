from __future__ import annotations

from core.domain.document.models import PageDTO
from core.domain.markdown.models import PageMarkdownDTO
from core.interfaces.node import Node, NodeContext, NodeResult
from core.services.page_failures import failure_markdown, page_failures, record_page_failure
from core.services.pdfplumber_extraction import extract_pdfplumber_markdown


class PdfplumberExtractorNode(Node):
    node_name = "pdfplumber_extractor"
    input_type = "page_dto@v1"
    output_type = "page_markdown_dto@v1"
    is_page_parallel = True

    def run(self, context: NodeContext, value: object) -> NodeResult:
        if not isinstance(value, PageDTO):
            raise TypeError("pdfplumber_extractor expects PageDTO input")

        try:
            markdown = extract_pdfplumber_markdown(value)
        except Exception as exc:
            failure = record_page_failure(value, "pdfplumber", exc)
            markdown = PageMarkdownDTO(
                page=value,
                markdown=f"@page:{value.page_no}\n\n{failure_markdown([failure])}",
                failures=page_failures(value),
            )
        return NodeResult(
            value=markdown,
            metadata={
                "document_id": value.document_id,
                "page_no": value.page_no,
                "has_text": bool(markdown.markdown.strip()),
                "failure_count": len(markdown.failures),
            },
        )
