from typing import Any

__all__ = ["MarkdownDocumentLoaderNode", "PdfPageSplitLoaderNode"]


def __getattr__(name: str) -> Any:
    if name == "MarkdownDocumentLoaderNode":
        from core.nodes.document.markdown import MarkdownDocumentLoaderNode

        return MarkdownDocumentLoaderNode
    if name == "PdfPageSplitLoaderNode":
        from core.nodes.document.split import PdfPageSplitLoaderNode

        return PdfPageSplitLoaderNode
    raise AttributeError(name)
