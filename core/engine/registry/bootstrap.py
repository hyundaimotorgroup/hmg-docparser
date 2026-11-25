from __future__ import annotations

from core.engine.registry.in_memory import InMemoryNodeRegistry
from core.interfaces.registry import NodeRegistry


def build_node_registry_for_graph(graph) -> InMemoryNodeRegistry:
    registry = InMemoryNodeRegistry()
    for node_name in sorted({node.node for node in graph.nodes}):
        register_node_by_name(registry, node_name)
    return registry


def register_node_by_name(registry: NodeRegistry, node_name: str) -> NodeRegistry:
    if node_name == "markdown_document_loader":
        from core.nodes.document.markdown import MarkdownDocumentLoaderNode

        registry.register(MarkdownDocumentLoaderNode.node_name, MarkdownDocumentLoaderNode)
        return registry

    if node_name == "pdf_page_split_loader":
        from core.nodes.document.split import PdfPageSplitLoaderNode

        registry.register(PdfPageSplitLoaderNode.node_name, PdfPageSplitLoaderNode)
        return registry


    if node_name == "confluence_uploader":
        from core.nodes.confluence import ConfluenceUploadNode

        registry.register(ConfluenceUploadNode.node_name, ConfluenceUploadNode)
        return registry

    if node_name == "layout.block_context_restorer":
        from core.nodes.layout.block_context import BlockContextRestoreNode
        registry.register(BlockContextRestoreNode.node_name, BlockContextRestoreNode)
        return registry

    if node_name in {"dolphin_layout_parser", "dolphin_vllm_layout_parser", "layout.label_filter", "layout.merge_page_enrichments"}:
        from core.nodes.layout import DolphinLayoutParserNode, DolphinVLLMLayoutParserNode, LayoutLabelFilterNode, PageEnrichmentMergeNode

        nodes = {
            DolphinLayoutParserNode.node_name: DolphinLayoutParserNode,
            DolphinVLLMLayoutParserNode.node_name: DolphinVLLMLayoutParserNode,
            LayoutLabelFilterNode.node_name: LayoutLabelFilterNode,
            PageEnrichmentMergeNode.node_name: PageEnrichmentMergeNode,
        }
        registry.register(node_name, nodes[node_name])
        return registry

    if node_name in {"layout_markdown_formatter", "markdown_document_saver"}:
        from core.nodes.markdown import LayoutMarkdownFormatterNode, MarkdownDocumentSaverNode

        nodes = {
            LayoutMarkdownFormatterNode.node_name: LayoutMarkdownFormatterNode,
            MarkdownDocumentSaverNode.node_name: MarkdownDocumentSaverNode,
        }
        registry.register(node_name, nodes[node_name])
        return registry

    if node_name in {
        "text_image_vlm_merger",
        "global_context_extraction_vlm_merger",
        "text_markdown_llm_merger",
        "markdown_document_assembler",
    }:
        from core.nodes.merge import (
            GlobalContextExtractionNode,
            MarkdownDocumentAssemblerNode,
            TextImageVLMMergeNode,
            TextMarkdownLLMMergeNode,
        )

        nodes = {
            GlobalContextExtractionNode.node_name: GlobalContextExtractionNode,
            MarkdownDocumentAssemblerNode.node_name: MarkdownDocumentAssemblerNode,
            TextImageVLMMergeNode.node_name: TextImageVLMMergeNode,
            TextMarkdownLLMMergeNode.node_name: TextMarkdownLLMMergeNode,
        }
        registry.register(node_name, nodes[node_name])
        return registry

    if node_name == "image_vlm_processor":
        from core.nodes.image import ImageVLMProcessorNode

        registry.register(ImageVLMProcessorNode.node_name, ImageVLMProcessorNode)
        return registry

    if node_name == "paddle_triton_ocr":
        from core.nodes.ocr import PaddleTritonOCRNode

        registry.register(PaddleTritonOCRNode.node_name, PaddleTritonOCRNode)
        return registry

    if node_name == "table_vlm_caption_maker":
        from core.nodes.table import TableVLMCaptionMakerNode

        registry.register(TableVLMCaptionMakerNode.node_name, TableVLMCaptionMakerNode)
        return registry

    if node_name in {"stage1_page_router", "stage2_element_router"}:
        from core.nodes.router.stage1 import Stage1PageRouterNode
        from core.nodes.router.stage2 import Stage2ElementRouterNode

        nodes = {
            Stage1PageRouterNode.node_name: Stage1PageRouterNode,
            Stage2ElementRouterNode.node_name: Stage2ElementRouterNode,
        }
        registry.register(node_name, nodes[node_name])
        return registry

    if node_name == "whole_page_llm_processor":
        from core.nodes.llm.whole_page import WholePageLLMProcessorNode

        registry.register(WholePageLLMProcessorNode.node_name, WholePageLLMProcessorNode)
        return registry

    if node_name == "pdfplumber_extractor":
        from core.nodes.text_extraction import PdfplumberExtractorNode

        registry.register(PdfplumberExtractorNode.node_name, PdfplumberExtractorNode)
        return registry

    raise ValueError(f"unknown node name: {node_name}")


def build_default_node_registry() -> InMemoryNodeRegistry:
    registry = InMemoryNodeRegistry()
    register_layout_nodes(registry)
    register_markdown_nodes(registry)
    register_merge_nodes(registry)
    register_document_nodes(registry)
    register_image_nodes(registry)
    register_ocr_nodes(registry)
    register_table_nodes(registry)
    register_text_extraction_nodes(registry)
    register_router_nodes(registry)
    register_llm_nodes(registry)
    return registry


def register_router_nodes(registry: NodeRegistry) -> NodeRegistry:
    from core.nodes.router.stage1 import Stage1PageRouterNode
    from core.nodes.router.stage2 import Stage2ElementRouterNode

    registry.register(Stage1PageRouterNode.node_name, Stage1PageRouterNode)
    registry.register(Stage2ElementRouterNode.node_name, Stage2ElementRouterNode)
    return registry


def register_llm_nodes(registry: NodeRegistry) -> NodeRegistry:
    from core.nodes.llm.whole_page import WholePageLLMProcessorNode

    registry.register(WholePageLLMProcessorNode.node_name, WholePageLLMProcessorNode)
    return registry


def register_layout_nodes(registry: NodeRegistry) -> NodeRegistry:
    from core.nodes.layout import DolphinLayoutParserNode, DolphinVLLMLayoutParserNode

    registry.register(DolphinLayoutParserNode.node_name, DolphinLayoutParserNode)
    registry.register(DolphinVLLMLayoutParserNode.node_name, DolphinVLLMLayoutParserNode)
    register_layout_routing_nodes(registry)
    register_node_by_name(registry, "layout.block_context_restorer")
    return registry


def register_layout_routing_nodes(registry: NodeRegistry) -> NodeRegistry:
    from core.nodes.layout import LayoutLabelFilterNode, PageEnrichmentMergeNode

    registry.register(LayoutLabelFilterNode.node_name, LayoutLabelFilterNode)
    registry.register(PageEnrichmentMergeNode.node_name, PageEnrichmentMergeNode)
    return registry


def register_markdown_nodes(registry: NodeRegistry) -> NodeRegistry:
    from core.nodes.markdown import LayoutMarkdownFormatterNode, MarkdownDocumentSaverNode

    registry.register(LayoutMarkdownFormatterNode.node_name, LayoutMarkdownFormatterNode)
    registry.register(MarkdownDocumentSaverNode.node_name, MarkdownDocumentSaverNode)
    return registry


def register_merge_nodes(registry: NodeRegistry) -> NodeRegistry:
    from core.nodes.merge import GlobalContextExtractionNode, MarkdownDocumentAssemblerNode, TextImageVLMMergeNode, TextMarkdownLLMMergeNode

    registry.register(GlobalContextExtractionNode.node_name, GlobalContextExtractionNode)
    registry.register(MarkdownDocumentAssemblerNode.node_name, MarkdownDocumentAssemblerNode)
    registry.register(TextImageVLMMergeNode.node_name, TextImageVLMMergeNode)
    registry.register(TextMarkdownLLMMergeNode.node_name, TextMarkdownLLMMergeNode)
    return registry


def register_document_nodes(registry: NodeRegistry) -> NodeRegistry:
    from core.nodes.document import MarkdownDocumentLoaderNode, PdfPageSplitLoaderNode

    registry.register(MarkdownDocumentLoaderNode.node_name, MarkdownDocumentLoaderNode)
    registry.register(PdfPageSplitLoaderNode.node_name, PdfPageSplitLoaderNode)
    return registry




def register_image_nodes(registry: NodeRegistry) -> NodeRegistry:
    from core.nodes.image import ImageVLMProcessorNode

    registry.register(ImageVLMProcessorNode.node_name, ImageVLMProcessorNode)
    return registry


def register_text_extraction_nodes(registry: NodeRegistry) -> NodeRegistry:
    from core.nodes.text_extraction import PdfplumberExtractorNode

    registry.register(PdfplumberExtractorNode.node_name, PdfplumberExtractorNode)
    return registry


def register_ocr_nodes(registry: NodeRegistry) -> NodeRegistry:
    from core.nodes.ocr import PaddleTritonOCRNode

    registry.register(PaddleTritonOCRNode.node_name, PaddleTritonOCRNode)
    return registry


def register_table_nodes(registry: NodeRegistry) -> NodeRegistry:
    from core.nodes.table import TableVLMCaptionMakerNode

    registry.register(TableVLMCaptionMakerNode.node_name, TableVLMCaptionMakerNode)
    return registry
