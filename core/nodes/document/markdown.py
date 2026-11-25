from __future__ import annotations

from pathlib import Path

from core.domain.artifacts import ArtifactRef
from core.domain.document.models import DocumentDTO, DocumentMetadataDTO
from core.interfaces.node import Node, NodeContext, NodeResult


class MarkdownDocumentLoaderNode(Node):
    node_name = "markdown_document_loader"
    input_type = "document_dto@v1"
    output_type = "document_dto@v1"

    def run(self, context: NodeContext, value: object) -> NodeResult:
        if not isinstance(value, DocumentDTO):
            raise TypeError("markdown_document_loader expects DocumentDTO input")

        path = Path(value.metadata.source_path)
        if not path.exists():
            raise FileNotFoundError(f"markdown file not found: {path}")
        if path.suffix.lower() not in {".md", ".markdown"}:
            raise ValueError(f"markdown_document_loader expects .md/.markdown input: {path}")

        markdown = path.read_text(encoding=_encoding(context))
        document = DocumentDTO(
            document_id=value.document_id or path.stem,
            metadata=DocumentMetadataDTO(
                source_path=str(path),
                file_name=path.name,
                mime_type="text/markdown",
                page_count=_count_page_markers(markdown) or None,
            ),
            markdown=markdown,
            artifacts=[
                ArtifactRef(
                    path=str(path),
                    media_type="text/markdown",
                    description="source markdown",
                )
            ],
        )
        return NodeResult(
            value=document,
            metadata={
                "source_path": str(path),
                "markdown_length": len(markdown),
                "page_count": document.metadata.page_count,
            },
        )


def _encoding(context: NodeContext) -> str:
    configured = context.config.get("encoding")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return "utf-8"


def _count_page_markers(markdown: str) -> int:
    return sum(1 for line in markdown.splitlines() if line.startswith("@page:"))
