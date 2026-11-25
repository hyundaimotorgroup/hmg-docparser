from __future__ import annotations

from pathlib import Path

from core.domain.markdown.models import PageMarkdownDTO
from core.interfaces.node import Node, NodeContext, NodeResult
from core.services.markdown_document_assemble import assemble_merged_pages_document
from core.services.markdown_validation import document_result_status


class MarkdownDocumentAssemblerNode(Node):
    node_name = "markdown_document_assembler"
    input_type = "page_markdown_dto@v1"
    output_type = "document_dto@v1"

    def run(self, context: NodeContext, value: object) -> NodeResult:
        pages = _coerce_pages(value)
        if not pages:
            raise ValueError("markdown_document_assembler expects at least one PageMarkdownDTO")

        document_id = _str_config(context, "document_id", "document_id", pages[0].page.document_id)
        document = assemble_merged_pages_document(
            pages,
            output_dir=_resolve_output_dir(context),
            document_id=document_id,
            task_name=str(context.config.get("task_name", "COMBINE_TEXT")),
            save_suffix=str(context.config.get("save_suffix", "")),
            save_debug_artifacts=_bool_config(context, "save_debug_artifacts", False),
        )
        return NodeResult(
            value=document,
            metadata={
                "page_count": len(document.pages),
                "result_status": document_result_status(document),
                "markdown_length": len(document.markdown or ""),
                "artifacts": [artifact.path for artifact in document.artifacts],
            },
        )


def _coerce_pages(value: object) -> list[PageMarkdownDTO]:
    if isinstance(value, PageMarkdownDTO):
        return [value]
    if isinstance(value, list) and all(isinstance(item, PageMarkdownDTO) for item in value):
        return value
    raise TypeError("markdown_document_assembler expects list[PageMarkdownDTO]")


def _resolve_output_dir(context: NodeContext) -> str:
    configured = _optional_str(context.config.get("output_dir"))
    if configured:
        return configured
    runtime_outputs = _optional_str(_runtime_config(context).get("outputs"))
    return runtime_outputs or str(Path("outputs") / "markdown-document")


def _runtime_config(context: NodeContext) -> dict[str, object]:
    value = context.metadata.get("runtime_config", {})
    return value if isinstance(value, dict) else {}


def _str_config(context: NodeContext, node_key: str, runtime_key: str, default: str) -> str:
    node_value = _optional_str(context.config.get(node_key))
    if node_value is not None:
        return node_value
    runtime_value = _optional_str(_runtime_config(context).get(runtime_key))
    return runtime_value if runtime_value is not None else default


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _bool_config(context: NodeContext, key: str, default: bool) -> bool:
    value = context.config.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
