from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from core.engine.config.models import NodeSpec, PipelineGraphConfig
from core.interfaces.registry import NodeRegistry

START_NODE_ID = "__START__"
DEFAULT_KNOWN_DTO_TYPES = {
    "document_dto@v1",
    "page_dto@v1",
    "page_layout_dto@v1",
    "page_enriched_dto@v1",
    "page_markdown_dto@v1",
    "none",
}
REQUIRED_NODE_CONFIG_KEYS = {
    "image_vlm_processor": ("model_name",),
    "table_vlm_caption_maker": ("model_name",),
    "global_context_extraction_vlm_merger": ("model_name",),
    "text_image_vlm_merger": ("model_name",),
    "text_markdown_llm_merger": ("model_name",),
}


@dataclass(slots=True)
class CompiledPipeline:
    graph: PipelineGraphConfig
    topological_order: list[str]
    upstream_by_node: dict[str, list[str]]
    downstream_by_node: dict[str, list[str]]


def compile_pipeline_graph(
    graph: PipelineGraphConfig,
    *,
    registry: NodeRegistry | None = None,
    known_dto_types: set[str] | None = None,
) -> CompiledPipeline:
    dto_types = known_dto_types or DEFAULT_KNOWN_DTO_TYPES
    nodes_by_id = _validate_unique_ids(graph.nodes)

    for node in graph.nodes:
        _validate_node_registration(node, registry)
        _validate_node_dto_types(node, dto_types)
        _validate_execution_scope(node)
        _validate_dependencies_exist(node, nodes_by_id)
        _validate_dependency_type_compatibility(node, nodes_by_id)
        _validate_required_node_config(node)
        _validate_label_routing_config(node)
        _validate_merge_config(node)

    _validate_output_node(graph, nodes_by_id)

    upstream = {
        node.id: [dep for dep in node.depends_on if dep != START_NODE_ID]
        for node in graph.nodes
    }
    downstream = _build_downstream_map(upstream)
    topological_order = _topological_sort(upstream, downstream)

    return CompiledPipeline(
        graph=graph,
        topological_order=topological_order,
        upstream_by_node=upstream,
        downstream_by_node=downstream,
    )


def _validate_unique_ids(nodes: list[NodeSpec]) -> dict[str, NodeSpec]:
    nodes_by_id: dict[str, NodeSpec] = {}
    for node in nodes:
        if node.id in nodes_by_id:
            raise ValueError(f"duplicated node id: {node.id}")
        nodes_by_id[node.id] = node
    return nodes_by_id


def _validate_node_registration(node: NodeSpec, registry: NodeRegistry | None) -> None:
    if registry is None:
        return
    try:
        registry.get(node.node)
    except KeyError as exc:
        raise ValueError(f"node is not registered: {node.node}") from exc


def _validate_node_dto_types(node: NodeSpec, dto_types: set[str]) -> None:
    for io_spec in (node.input, node.output):
        if io_spec.type not in dto_types:
            raise ValueError(f"unknown dto type: {io_spec.type} in node {node.id}")


def _validate_execution_scope(node: NodeSpec) -> None:
    expected_shape = {
        "fanout": (False, True),
        "page": (True, True),
        "fanin": (True, False),
        "document": (False, False),
    }[node.execution_scope]
    actual_shape = (node.input.is_list, node.output.is_list)
    if actual_shape != expected_shape:
        raise ValueError(
            f"execution_scope {node.execution_scope!r} requires input/output "
            f"is_list={expected_shape}: {node.id}"
        )


def _validate_output_node(graph: PipelineGraphConfig, nodes_by_id: dict[str, NodeSpec]) -> None:
    output = nodes_by_id.get(graph.output_node)
    if output is None:
        raise ValueError(f"pipeline.output_node is not a node id: {graph.output_node}")
    if output.output.type != "document_dto@v1" or output.output.is_list:
        raise ValueError(
            "pipeline.output_node must output a non-list document_dto@v1: "
            f"{graph.output_node}"
        )


def _validate_dependencies_exist(node: NodeSpec, nodes_by_id: dict[str, NodeSpec]) -> None:
    start_count = node.depends_on.count(START_NODE_ID)
    if start_count:
        if start_count != 1 or len(node.depends_on) != 1 or node.execution_scope != "fanout":
            raise ValueError(f"__START__ is allowed only as the sole fanout dependency: {node.id}")
    for dep in node.depends_on:
        if dep == START_NODE_ID:
            continue
        if dep not in nodes_by_id:
            raise ValueError(f"unknown dependency '{dep}' in node {node.id}")


def _validate_dependency_type_compatibility(node: NodeSpec, nodes_by_id: dict[str, NodeSpec]) -> None:
    actual_dependencies = [dep for dep in node.depends_on if dep != START_NODE_ID]
    if not actual_dependencies:
        return

    if len(actual_dependencies) > 1 and not node.input.is_list:
        raise ValueError(f"multi-dependency node must accept list input: {node.id}")

    for dep_id in actual_dependencies:
        dep = nodes_by_id[dep_id]
        if dep.output.type != node.input.type:
            raise ValueError(
                f"dto type mismatch: {dep.id} -> {node.id} "
                f"({dep.output.type} != {node.input.type})"
            )
        if dep.output.is_list != node.input.is_list:
            raise ValueError(
                f"list cardinality mismatch: {dep.id} -> {node.id} "
                f"({dep.output.is_list} != {node.input.is_list})"
            )


def _validate_required_node_config(node: NodeSpec) -> None:
    required_keys = REQUIRED_NODE_CONFIG_KEYS.get(node.node, ())
    missing = [
        key
        for key in required_keys
        if not _is_non_empty_str(node.node_config.get(key))
    ]
    if missing:
        raise ValueError(f"node_config missing required keys for {node.node} ({node.id}): {missing}")

    if node.node == "layout.label_filter":
        has_input_labels = "input_labels" in node.node_config
        has_input_exclude_labels = "input_exclude_labels" in node.node_config
        if not has_input_labels and not has_input_exclude_labels:
            raise ValueError(
                f"layout.label_filter requires input_labels or input_exclude_labels: {node.id}"
            )

    if node.node == "layout.merge_page_enrichments":
        for key in ("merge_key", "field_priority"):
            if key not in node.node_config:
                raise ValueError(f"layout.merge_page_enrichments requires node_config.{key}: {node.id}")


def _validate_label_routing_config(node: NodeSpec) -> None:
    has_input_labels = "input_labels" in node.node_config
    has_input_exclude_labels = "input_exclude_labels" in node.node_config
    if has_input_labels and has_input_exclude_labels:
        raise ValueError(
            f"node_config cannot use both input_labels and input_exclude_labels: {node.id}"
        )

    for key in ("input_labels", "input_exclude_labels"):
        if key not in node.node_config:
            continue
        labels = node.node_config[key]
        if not _is_non_empty_str_list(labels):
            raise ValueError(f"node_config.{key} must be a non-empty list[str]: {node.id}")


def _validate_merge_config(node: NodeSpec) -> None:
    merge_key = node.node_config.get("merge_key")
    if merge_key is not None and merge_key != "block_id":
        raise ValueError(f"node_config.merge_key currently supports only 'block_id': {node.id}")

    actual_dependencies = [dep for dep in node.depends_on if dep != START_NODE_ID]
    if node.node == "text_markdown_llm_merger" and len(actual_dependencies) != 2:
        raise ValueError(f"text_markdown_llm_merger requires exactly two ordered branches: {node.id}")
    if node.node == "text_markdown_llm_merger":
        primary = node.node_config.get("primary_node_id")
        if primary != actual_dependencies[0]:
            raise ValueError(
                "text_markdown_llm_merger primary_node_id must name the first dependency: "
                f"{node.id}"
            )
    if node.node == "layout.merge_page_enrichments" and len(actual_dependencies) < 2:
        raise ValueError(f"layout.merge_page_enrichments requires at least two branches: {node.id}")

    field_priority = node.node_config.get("field_priority")
    if field_priority is None:
        return
    if not isinstance(field_priority, dict) or not field_priority:
        raise ValueError(f"node_config.field_priority must be a non-empty dict: {node.id}")

    dependency_ids = set(actual_dependencies)
    for field_name, priority in field_priority.items():
        if not isinstance(field_name, str) or not field_name.strip():
            raise ValueError(f"field_priority field names must be non-empty strings: {node.id}")
        if not _is_non_empty_str_list(priority):
            raise ValueError(f"field_priority.{field_name} must be a non-empty list[str]: {node.id}")
        unknown = sorted(set(priority) - dependency_ids)
        if unknown:
            raise ValueError(
                f"field_priority.{field_name} references non-dependency nodes in {node.id}: {unknown}"
            )


def _is_non_empty_str_list(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(isinstance(item, str) and item.strip() for item in value)


def _is_non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _build_downstream_map(upstream: dict[str, list[str]]) -> dict[str, list[str]]:
    downstream = {node_id: [] for node_id in upstream}
    for node_id, deps in upstream.items():
        for dep in deps:
            downstream.setdefault(dep, []).append(node_id)
    for node_id in downstream:
        downstream[node_id].sort()
    return downstream


def _topological_sort(
    upstream: dict[str, list[str]],
    downstream: dict[str, list[str]],
) -> list[str]:
    indegree = {node_id: len(deps) for node_id, deps in upstream.items()}
    queue = deque(sorted(node_id for node_id, count in indegree.items() if count == 0))
    order: list[str] = []

    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for child in downstream.get(node_id, []):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(order) != len(upstream):
        unresolved = sorted(node_id for node_id, count in indegree.items() if count > 0)
        raise ValueError(f"cycle detected in pipeline graph: {unresolved}")

    return order
