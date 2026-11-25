from __future__ import annotations

from abc import ABC, abstractmethod

from core.interfaces.node import Node


class NodeRegistry(ABC):
    @abstractmethod
    def register(self, node_name: str, node_cls: type[Node]) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, node_name: str) -> type[Node]:
        raise NotImplementedError
