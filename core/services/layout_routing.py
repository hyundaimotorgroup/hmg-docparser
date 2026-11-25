from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from core.domain.layout.models import LayoutBlockDTO, PageEnrichedDTO, PageLayoutDTO

MERGEABLE_BLOCK_FIELDS = ("text", "title", "score", "table_html_raw", "crop_artifact")


def filter_page_layouts_by_label(
    pages: Sequence[PageLayoutDTO],
    *,
    input_labels: Sequence[str] | None = None,
    input_exclude_labels: Sequence[str] | None = None,
) -> list[PageLayoutDTO]:
    if input_labels and input_exclude_labels:
        raise ValueError("input_labels and input_exclude_labels are mutually exclusive")

    included = _normalize_labels(input_labels)
    excluded = _normalize_labels(input_exclude_labels)

    return [
        replace(
            page_layout,
            blocks=[
                block
                for block in page_layout.blocks
                if _matches_label_filter(block, included=included, excluded=excluded)
            ],
        )
        for page_layout in pages
    ]


def merge_page_enrichments(
    branches: Mapping[str, Sequence[PageEnrichedDTO]],
    *,
    merge_key: str = "block_id",
    field_priority: Mapping[str, Sequence[str]] | None = None,
) -> list[PageEnrichedDTO]:
    if merge_key != "block_id":
        raise ValueError(f"unsupported merge_key: {merge_key}")
    if not branches:
        return []

    branch_order = list(branches.keys())
    field_priority = field_priority or {}
    pages_by_no = _index_pages_by_no(branches)
    merged_pages: list[PageEnrichedDTO] = []

    for page_no in sorted(pages_by_no):
        page_branches = pages_by_no[page_no]
        base_page = _first_page(page_branches, branch_order)
        block_keys = _ordered_block_keys(page_branches, branch_order)
        merged_blocks = [
            _merge_block(
                page_branches=page_branches,
                branch_order=branch_order,
                block_id=block_id,
                field_priority=field_priority,
            )
            for block_id in block_keys
        ]
        merged_pages.append(
            PageEnrichedDTO(
                page=base_page.page,
                blocks=merged_blocks,
                source_node_id="merge_page_enrichments",
            )
        )

    return merged_pages


def _normalize_labels(labels: Sequence[str] | None) -> set[str]:
    return {label.strip().lower() for label in (labels or []) if label.strip()}


def _matches_label_filter(
    block: LayoutBlockDTO,
    *,
    included: set[str],
    excluded: set[str],
) -> bool:
    label = (block.label or "").strip().lower()
    if included and label not in included:
        return False
    if excluded and label in excluded:
        return False
    return True


def _index_pages_by_no(
    branches: Mapping[str, Sequence[PageEnrichedDTO]],
) -> dict[int, dict[str, PageEnrichedDTO]]:
    pages_by_no: dict[int, dict[str, PageEnrichedDTO]] = {}
    for node_id, pages in branches.items():
        for page in pages:
            pages_by_no.setdefault(page.page.page_no, {})[node_id] = page
    return pages_by_no


def _first_page(
    page_branches: Mapping[str, PageEnrichedDTO],
    branch_order: Sequence[str],
) -> PageEnrichedDTO:
    for node_id in branch_order:
        page = page_branches.get(node_id)
        if page is not None:
            return page
    raise ValueError("page_branches must contain at least one page")


def _ordered_block_keys(
    page_branches: Mapping[str, PageEnrichedDTO],
    branch_order: Sequence[str],
) -> list[str]:
    seen = set()
    block_ids: list[str] = []
    for node_id in branch_order:
        page = page_branches.get(node_id)
        if page is None:
            continue
        for block in page.blocks:
            if block.block_id in seen:
                continue
            seen.add(block.block_id)
            block_ids.append(block.block_id)
    return block_ids


def _merge_block(
    *,
    page_branches: Mapping[str, PageEnrichedDTO],
    branch_order: Sequence[str],
    block_id: str,
    field_priority: Mapping[str, Sequence[str]],
) -> LayoutBlockDTO:
    blocks_by_node = {
        node_id: block
        for node_id, page in page_branches.items()
        for block in page.blocks
        if block.block_id == block_id
    }
    base_block = _first_block(blocks_by_node, branch_order)
    merged_block = replace(base_block, metadata=_merge_metadata(blocks_by_node, branch_order))

    for field_name in MERGEABLE_BLOCK_FIELDS:
        priority = list(field_priority.get(field_name, branch_order))
        selected_value = _select_field_value(blocks_by_node, priority, field_name)
        if selected_value is not None:
            setattr(merged_block, field_name, selected_value)

    merged_block.metadata["merged_from"] = [
        node_id
        for node_id in branch_order
        if node_id in blocks_by_node
    ]
    return merged_block


def _merge_metadata(
    blocks_by_node: Mapping[str, LayoutBlockDTO],
    branch_order: Sequence[str],
) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for node_id in branch_order:
        block = blocks_by_node.get(node_id)
        if block is None:
            continue
        metadata.update(block.metadata)
    return metadata


def _first_block(
    blocks_by_node: Mapping[str, LayoutBlockDTO],
    branch_order: Sequence[str],
) -> LayoutBlockDTO:
    for node_id in branch_order:
        block = blocks_by_node.get(node_id)
        if block is not None:
            return block
    raise ValueError("blocks_by_node must contain at least one block")


def _select_field_value(
    blocks_by_node: Mapping[str, LayoutBlockDTO],
    priority: Sequence[str],
    field_name: str,
) -> object | None:
    for node_id in priority:
        block = blocks_by_node.get(node_id)
        if block is None:
            continue
        value = getattr(block, field_name)
        if _has_value(value):
            return value
    return None


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value == "":
        return False
    return True
