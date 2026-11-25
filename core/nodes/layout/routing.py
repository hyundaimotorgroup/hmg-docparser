from __future__ import annotations

from collections.abc import Sequence

from core.domain.layout.models import PageEnrichedDTO, PageLayoutDTO
from core.interfaces.node import Node, NodeContext, NodeResult
from core.services.layout_routing import filter_page_layouts_by_label, merge_page_enrichments


class LayoutLabelFilterNode(Node):
    node_name = "layout.label_filter"
    input_type = "page_layout_dto@v1"
    output_type = "page_layout_dto@v1"

    def run(self, context: NodeContext, value: object) -> NodeResult:
        single_input = isinstance(value, PageLayoutDTO)
        page_layouts = _coerce_page_layouts(value)
        filtered = filter_page_layouts_by_label(
            page_layouts,
            input_labels=_optional_str_list(context.config.get("input_labels")),
            input_exclude_labels=_optional_str_list(context.config.get("input_exclude_labels")),
        )
        # Preserve input arity so the streaming (per-page) runner keeps feeding a single
        # PageLayoutDTO downstream; a list input still yields a list.
        value_out = (filtered[0] if filtered else value) if single_input else filtered
        return NodeResult(
            value=value_out,
            metadata={
                "input_page_count": len(page_layouts),
                "output_block_count": sum(len(page.blocks) for page in filtered),
            },
        )


class PageEnrichmentMergeNode(Node):
    node_name = "layout.merge_page_enrichments"
    input_type = "page_enriched_dto@v1"
    output_type = "page_enriched_dto@v1"

    def run(self, context: NodeContext, value: object) -> NodeResult:
        dependencies = [str(dep) for dep in context.metadata.get("depends_on", [])]
        # `value` is aligned with `dependencies` (one entry per upstream branch). In the
        # streaming runner each entry is a single PageEnrichedDTO for this page; in the
        # legacy document-level runner each entry is a list[PageEnrichedDTO].
        value_list = value if isinstance(value, list) else [value]
        if len(dependencies) == len(value_list):
            branch_inputs = value_list
        elif len(dependencies) == 1:
            branch_inputs = [value]
        else:
            raise ValueError(
                "merge node dependency count does not match input branch count "
                f"({len(dependencies)} != {len(value_list)})"
            )

        streaming = all(isinstance(item, PageEnrichedDTO) for item in branch_inputs)
        branches = {
            dep: ([item] if isinstance(item, PageEnrichedDTO) else item)
            for dep, item in zip(dependencies, branch_inputs)
        }
        merged = merge_page_enrichments(
            branches,
            merge_key=str(context.config.get("merge_key", "block_id")),
            field_priority=_coerce_field_priority(context.config.get("field_priority")),
        )
        # Single page in (streaming) -> single page out, preserving arity for the runner.
        value_out = merged[0] if streaming and merged else merged
        return NodeResult(
            value=value_out,
            metadata={
                "input_branch_count": len(branches),
                "output_page_count": len(merged),
                "output_block_count": sum(len(page.blocks) for page in merged),
            },
        )


def _coerce_page_layouts(value: object) -> list[PageLayoutDTO]:
    if isinstance(value, PageLayoutDTO):
        return [value]
    if isinstance(value, list) and all(isinstance(item, PageLayoutDTO) for item in value):
        return value
    raise TypeError("layout label filter expects PageLayoutDTO or list[PageLayoutDTO]")


def _optional_str_list(value: object) -> Sequence[str] | None:
    if value is None:
        return None
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise TypeError("expected list[str]")


def _coerce_field_priority(value: object) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError("field_priority must be dict[str, list[str]]")

    coerced: dict[str, list[str]] = {}
    for field_name, priority in value.items():
        if not isinstance(field_name, str):
            raise TypeError("field_priority field names must be strings")
        if not isinstance(priority, list) or not all(isinstance(item, str) for item in priority):
            raise TypeError("field_priority values must be list[str]")
        coerced[field_name] = priority
    return coerced
