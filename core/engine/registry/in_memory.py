from __future__ import annotations

from core.interfaces.node import Node
from core.interfaces.registry import NodeRegistry


class InMemoryNodeRegistry(NodeRegistry):
    def __init__(self) -> None:
        self._nodes: dict[str, type[Node]] = {}

    def register(self, node_name: str, node_cls: type[Node]) -> None:
        if not node_name:
            raise ValueError("node_name must not be empty")
        if node_name in self._nodes:
            raise ValueError(f"node already registered: {node_name}")
        self._nodes[node_name] = node_cls

    def get(self, node_name: str) -> type[Node]:
        try:
            return self._nodes[node_name]
        except KeyError as exc:
            raise KeyError(f"node is not registered: {node_name}") from exc

    def has(self, node_name: str) -> bool:
        return node_name in self._nodes

    def list_names(self) -> list[str]:
        return sorted(self._nodes.keys())
