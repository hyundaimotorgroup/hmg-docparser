"""Runtime page-graph expansion.

This module turns a *document-scoped* DAG into a *page-scoped* DAG once the page
count is known (i.e. after the fan-out/split node has run).

Motivation: the pipeline scheduler advances one node at a time and only enqueues a
child node when *all* of its parents finish. With a single node per stage that means
every page must clear a stage before any page enters the next stage — a hard
node-boundary barrier. By replicating each page-scoped node into one instance per
page and re-wiring the edges per page, the *existing* scheduler streams pages
independently: page 1 can be at ``format_markdown`` while page 3 is still at
``layout``, with no code change to the scheduling loop itself.

Design notes:
- Pure data transformation. No pydantic / domain / engine imports so it stays unit
  testable on any Python (the rest of the codebase requires 3.10+).
- Node scope is derived from ``input.is_list`` / ``output.is_list`` (see
  :func:`classify_scope`) so no config schema change is required.
- Only PAGE-scoped nodes are replicated. FANOUT nodes run once (already executed
  before expansion); FANIN / DOC nodes run once and collect per-page results.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Node scopes.
FANOUT = "fanout"  # scalar -> list   (e.g. split document into pages) — runs once
PAGE = "page"      # list -> list     (per-page transform) — replicated per page
FANIN = "fanin"    # list -> scalar   (assemble pages into a document) — runs once
DOC = "doc"        # scalar -> scalar (document-level, after fan-in) — runs once

# Separator between an original node id and its page index in an expanded id.
PAGE_SUFFIX = "#p"


def classify_scope(*, input_is_list: bool, output_is_list: bool) -> str:
    """Derive a node's page scope from its declared IO list-ness."""
    if not input_is_list and output_is_list:
        return FANOUT
    if input_is_list and output_is_list:
        return PAGE
    if input_is_list and not output_is_list:
        return FANIN
    return DOC


def page_id(node_id: str, page_index: int) -> str:
    return f"{node_id}{PAGE_SUFFIX}{page_index}"


# Kinds of value source feeding an expanded node's input.
SRC_NODE = "node"        # value = output of a single (expanded) node
SRC_PAGE_OF = "page_of"  # value = element [page_index] of a fan-out node's list output
SRC_COLLECT = "collect"  # value = list of the outputs of every page copy of a page node


@dataclass(frozen=True)
class InputSource:
    kind: str
    # For SRC_NODE: the expanded node id. For SRC_PAGE_OF / SRC_COLLECT: the *origin* id.
    ref: str
    page_index: int | None = None          # SRC_PAGE_OF only
    members: tuple[str, ...] = ()           # SRC_COLLECT only (expanded ids, page order)

    def upstream_refs(self) -> tuple[str, ...]:
        """Expanded node ids this source depends on (for scheduling edges)."""
        if self.kind == SRC_NODE:
            return (self.ref,)
        if self.kind == SRC_COLLECT:
            return self.members
        # SRC_PAGE_OF references a fan-out node that ran before expansion.
        return (self.ref,)


@dataclass(frozen=True)
class ExpandedNode:
    id: str                       # expanded id (page id for PAGE nodes, else origin id)
    origin: str                   # original node id
    scope: str
    page_index: int | None        # set for PAGE nodes, else None
    sources: tuple[InputSource, ...]  # ordered, aligned with the node's original deps


@dataclass
class ExpandedGraph:
    nodes: list[ExpandedNode]
    # expanded_id -> list of expanded upstream ids that are *scheduled* in this pass
    # (fan-out refs are excluded because those nodes already completed pre-expansion).
    upstream: dict[str, list[str]] = field(default_factory=dict)
    downstream: dict[str, list[str]] = field(default_factory=dict)

    def by_id(self) -> dict[str, ExpandedNode]:
        return {node.id: node for node in self.nodes}


def expand_graph(
    *,
    scheduled_ids: list[str],
    deps: dict[str, list[str]],
    scope: dict[str, str],
    page_count: int,
    prerun_ids: frozenset[str],
) -> ExpandedGraph:
    """Build the per-page expanded scheduling graph.

    Args:
        scheduled_ids: node ids to schedule in this pass (PAGE + FANIN + DOC).
        deps: original upstream map (node_id -> [dep ids], excluding START).
        scope: node_id -> scope (FANOUT/PAGE/FANIN/DOC).
        page_count: number of pages produced by the fan-out node.
        prerun_ids: ids already executed before expansion (FANOUT nodes). Their
            outputs are available; edges pointing at them are not scheduled edges.

    Returns:
        ExpandedGraph with replicated PAGE nodes and re-wired input sources.
    """
    if page_count < 0:
        raise ValueError(f"page_count must be >= 0, got {page_count}")
    _ = prerun_ids  # documented in the signature; edges are derived from expanded_ids

    nodes: list[ExpandedNode] = []

    def source_for_dep(dep_id: str, page_index: int | None) -> InputSource:
        dep_scope = scope.get(dep_id)
        if dep_scope == FANOUT:
            # A page node reading the fan-out list: take just this page's element.
            if page_index is None:
                # A fan-in reading a fan-out list directly: whole list is one dep value.
                return InputSource(kind=SRC_NODE, ref=dep_id)
            return InputSource(kind=SRC_PAGE_OF, ref=dep_id, page_index=page_index)
        if dep_scope == PAGE:
            if page_index is None:
                # fan-in / doc node collecting every page copy into a list.
                members = tuple(page_id(dep_id, p) for p in range(page_count))
                return InputSource(kind=SRC_COLLECT, ref=dep_id, members=members)
            # page node reading its per-page upstream page node.
            return InputSource(kind=SRC_NODE, ref=page_id(dep_id, page_index))
        # FANIN / DOC upstream (single scalar value).
        return InputSource(kind=SRC_NODE, ref=dep_id)

    for node_id in scheduled_ids:
        node_scope = scope[node_id]
        node_deps = deps.get(node_id, [])
        if node_scope == PAGE:
            for p in range(page_count):
                sources = tuple(source_for_dep(dep, p) for dep in node_deps)
                nodes.append(
                    ExpandedNode(
                        id=page_id(node_id, p),
                        origin=node_id,
                        scope=PAGE,
                        page_index=p,
                        sources=sources,
                    )
                )
        else:
            sources = tuple(source_for_dep(dep, None) for dep in node_deps)
            nodes.append(
                ExpandedNode(
                    id=node_id,
                    origin=node_id,
                    scope=node_scope,
                    page_index=None,
                    sources=sources,
                )
            )

    expanded_ids = {node.id for node in nodes}
    upstream: dict[str, list[str]] = {}
    for node in nodes:
        ups: list[str] = []
        seen: set[str] = set()
        for src in node.sources:
            for ref in src.upstream_refs():
                # Only edges to nodes scheduled in this pass impose a wait. Refs to
                # pre-run fan-out nodes are absent from expanded_ids (already done).
                if ref in expanded_ids and ref not in seen:
                    ups.append(ref)
                    seen.add(ref)
        upstream[node.id] = ups

    downstream: dict[str, list[str]] = {node.id: [] for node in nodes}
    for node_id, ups in upstream.items():
        for dep in ups:
            downstream.setdefault(dep, []).append(node_id)
    for node_id in downstream:
        downstream[node_id].sort()

    return ExpandedGraph(nodes=nodes, upstream=upstream, downstream=downstream)


def resolve_input_value(
    sources: tuple[InputSource, ...],
    outputs: dict[str, object],
    initial_value: object,
) -> object:
    """Resolve the value fed to an expanded node from completed outputs.

    Mirrors the legacy single/multi-dependency contract: no deps -> initial value;
    one source -> that value; many -> a list aligned with the node's original deps.
    """
    if not sources:
        return initial_value
    values: list[object] = []
    for src in sources:
        if src.kind == SRC_NODE:
            values.append(outputs[src.ref])
        elif src.kind == SRC_PAGE_OF:
            values.append(outputs[src.ref][src.page_index])  # type: ignore[index]
        elif src.kind == SRC_COLLECT:
            values.append([outputs[member] for member in src.members])
        else:  # pragma: no cover - guarded by construction
            raise ValueError(f"unknown source kind: {src.kind}")
    return values[0] if len(values) == 1 else values
