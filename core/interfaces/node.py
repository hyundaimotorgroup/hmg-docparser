from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(slots=True)
class NodeContext:
    job_id: str
    node_id: str
    node_name: str
    config: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class NodeResult:
    value: object
    metadata: dict[str, object] = field(default_factory=dict)


class Node(ABC):
    node_name = ""
    input_type = "none"
    output_type = "none"
    is_page_parallel = False
    max_concurrency = 1

    @abstractmethod
    def run(self, context: NodeContext, value: object) -> NodeResult:
        raise NotImplementedError
