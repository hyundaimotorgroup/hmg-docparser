from __future__ import annotations

from pathlib import Path

from core.domain.layout.models import PageEnrichedDTO
from core.domain.markdown.models import PageMarkdownDTO
from core.interfaces.node import Node, NodeContext, NodeResult
from core.services.layout_markdown import format_page_enrichment_as_markdown, save_page_markdowns_as_document


class LayoutMarkdownFormatterNode(Node):
    node_name = "layout_markdown_formatter"
    input_type = "page_enriched_dto@v1"
    output_type = "page_markdown_dto@v1"
    is_page_parallel = True

    def run(self, context: NodeContext, value: object) -> NodeResult:
        pages, single_input = _coerce_enriched_pages(value)
        include_table_crop_images = _bool_config(
            context,
            "include_table_crop_images",
            "include_table_crop_images",
            False,
        )
        markdown_pages = [
            format_page_enrichment_as_markdown(
                page,
                include_table_crop_images=include_table_crop_images,
                restore_tables=bool(context.config.get("restore_tables", False)),
                include_page_marker=bool(context.config.get("include_page_marker", True)),
            )
            for page in pages
        ]
        value_out: PageMarkdownDTO | list[PageMarkdownDTO] = (
            markdown_pages[0] if single_input else markdown_pages
        )
        return NodeResult(
            value=value_out,
            metadata={
                "page_count": len(markdown_pages),
                "non_empty_pages": sum(1 for page in markdown_pages if page.markdown.strip()),
                "include_table_crop_images": include_table_crop_images,
            },
        )


class MarkdownDocumentSaverNode(Node):
    node_name = "markdown_document_saver"
    input_type = "page_markdown_dto@v1"
    output_type = "document_dto@v1"

    def run(self, context: NodeContext, value: object) -> NodeResult:
        pages = _coerce_markdown_pages(value)
        if not pages:
            raise ValueError("markdown_document_saver expects at least one PageMarkdownDTO")

        document_id = _str_config(context, "document_id", "document_id", pages[0].page.document_id)
        document = save_page_markdowns_as_document(
            pages,
            output_dir=_resolve_output_dir(context),
            document_id=document_id,
            task_name=_str_config(context, "task_name", "task_name", "LAYOUT"),
            save_suffix=_str_config(context, "save_suffix", "save_suffix", ""),
            save_debug_artifacts=_bool_config(
                context,
                "save_debug_artifacts",
                "save_debug_artifacts",
                False,
            ),
        )
        return NodeResult(
            value=document,
            metadata={
                "page_count": len(pages),
                "markdown_length": len(document.markdown or ""),
                "artifacts": [artifact.path for artifact in document.artifacts],
            },
        )


def _coerce_enriched_pages(value: object) -> tuple[list[PageEnrichedDTO], bool]:
    if isinstance(value, PageEnrichedDTO):
        return [value], True
    if isinstance(value, list) and all(isinstance(item, PageEnrichedDTO) for item in value):
        return value, False
    raise TypeError("layout_markdown_formatter expects PageEnrichedDTO or list[PageEnrichedDTO]")


def _coerce_markdown_pages(value: object) -> list[PageMarkdownDTO]:
    if isinstance(value, PageMarkdownDTO):
        return [value]
    if isinstance(value, list) and all(isinstance(item, PageMarkdownDTO) for item in value):
        return value
    raise TypeError("markdown_document_saver expects PageMarkdownDTO or list[PageMarkdownDTO]")


def _resolve_output_dir(context: NodeContext) -> str:
    configured = _optional_str(context.config.get("output_dir"))
    if configured:
        return configured
    runtime_outputs = _optional_str(_runtime_config(context).get("outputs"))
    return runtime_outputs or str(Path("outputs") / "layout-markdown")


def _runtime_config(context: NodeContext) -> dict[str, object]:
    value = context.metadata.get("runtime_config", {})
    return value if isinstance(value, dict) else {}


def _str_config(context: NodeContext, node_key: str, runtime_key: str, default: str) -> str:
    node_value = _optional_str(context.config.get(node_key))
    if node_value is not None:
        return node_value
    runtime_value = _optional_str(_runtime_config(context).get(runtime_key))
    return runtime_value if runtime_value is not None else default


def _bool_config(context: NodeContext, node_key: str, runtime_key: str, default: bool) -> bool:
    value = context.config.get(node_key, _runtime_config(context).get(runtime_key, default))
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
