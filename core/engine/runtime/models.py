from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PipelineRunResult:
    values_by_node: dict[str, object] = field(default_factory=dict)
    metadata_by_node: dict[str, dict[str, object]] = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)

    def latest_value(self) -> object | None:
        if not self.execution_order:
            return None
        return self.values_by_node[self.execution_order[-1]]
