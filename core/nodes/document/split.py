from __future__ import annotations

from pathlib import Path

from core.domain.document.models import DocumentDTO
from core.interfaces.node import Node, NodeContext, NodeResult
from core.services.pdf_page_split import split_pdf_document_to_pages


class PdfPageSplitLoaderNode(Node):
    node_name = "pdf_page_split_loader"
    input_type = "document_dto@v1"
    output_type = "page_dto@v1"

    def run(self, context: NodeContext, value: object) -> NodeResult:
        if not isinstance(value, DocumentDTO):
            raise TypeError("pdf_page_split_loader expects DocumentDTO input")

        output_dir = _resolve_output_dir(context, value)
        pages = split_pdf_document_to_pages(value, output_dir=output_dir)
        return NodeResult(
            value=pages,
            metadata={
                "page_count": len(pages),
                "output_dir": output_dir,
                "artifact_role": "temp",
                "keep_page_artifacts": _bool_config(context.config.get("keep_page_artifacts"), default=False),
            },
        )


def _resolve_output_dir(context: NodeContext, document: DocumentDTO) -> str:
    configured = context.config.get("output_dir")
    if isinstance(configured, str) and configured.strip():
        return configured

    runtime_config = context.metadata.get("runtime_config", {})
    if isinstance(runtime_config, dict):
        base_output = runtime_config.get("outputs")
        if isinstance(base_output, str) and base_output.strip():
            return str(Path(base_output) / "_page_split")

    return str(Path("outputs") / "_page_split" / document.document_id)


def _bool_config(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
