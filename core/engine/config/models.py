from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class IOTypeSpec(StrictModel):
    type: str
    is_list: bool = False

    @field_validator("type")
    @classmethod
    def validate_type_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("type must not be empty")
        return normalized


class NodeSpec(StrictModel):
    id: str
    node: str
    input: IOTypeSpec
    output: IOTypeSpec
    description: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    execution_scope: Literal["fanout", "page", "fanin", "document"]
    max_concurrency: StrictInt = 1
    node_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "node")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("depends_on")
    @classmethod
    def validate_depends_on(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("depends_on must contain at least one dependency")
        return normalized

    @field_validator("max_concurrency")
    @classmethod
    def validate_concurrency(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_concurrency must be >= 1")
        return value

    @model_validator(mode="after")
    def validate_typed_node_config(self, info) -> "NodeSpec":
        from core.engine.config.node_config import validate_node_config

        self.node_config = validate_node_config(
            self.node, self.node_config, context=info.context
        )
        return self


class PipelineGraphConfig(StrictModel):
    output_node: str
    nodes: list[NodeSpec]

    @field_validator("output_node")
    @classmethod
    def validate_output_node(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("output_node must not be empty")
        return normalized

    @field_validator("nodes")
    @classmethod
    def validate_nodes_non_empty(cls, value: list[NodeSpec]) -> list[NodeSpec]:
        if not value:
            raise ValueError("nodes must not be empty")
        return value


class DocumentLimitsConfig(StrictModel):
    allowed_extensions: list[str] = Field(default_factory=lambda: [".pdf"])
    max_input_mb: StrictFloat | StrictInt = 100
    max_pdf_pages: StrictInt = 500
    max_zip_members: StrictInt = 1_000
    max_zip_uncompressed_mb: StrictFloat | StrictInt = 500
    max_zip_compression_ratio: StrictFloat | StrictInt = 100


class ResourceBudgetConfig(StrictModel):
    scheduler_max_workers: StrictInt = 8

    @field_validator("scheduler_max_workers")
    @classmethod
    def validate_workers(cls, value: int) -> int:
        if value < 1:
            raise ValueError("scheduler_max_workers must be >= 1")
        if value > 64:
            raise ValueError("scheduler_max_workers must be <= 64")
        return value


class LangfuseConfig(StrictModel):
    on: StrictBool = False


class NativeRuntimeConfig(StrictModel):
    input_dir: str
    output_dir: str
    pricing_file: str | None = Field(
        default=None,
        strict=True,
        description="Optional operator pricing YAML; relative to this config file. Omit for usage only.",
    )
    document_limits: DocumentLimitsConfig = Field(default_factory=DocumentLimitsConfig)
    resource_budget: ResourceBudgetConfig = Field(default_factory=ResourceBudgetConfig)
    langfuse: LangfuseConfig = Field(default_factory=LangfuseConfig)
    pipeline: PipelineGraphConfig
    prompt_policy: dict[str, Any] = Field(default_factory=dict)

    @field_validator("input_dir", "output_dir")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("path must not be empty")
        return value

    @model_validator(mode="after")
    def validate_node_budget(self) -> "NativeRuntimeConfig":
        from core.services.prompt_policy import PromptPolicy, prepare_node_prompts

        prepare_node_prompts(
            self.pipeline.nodes, policy=PromptPolicy.from_mapping(self.prompt_policy)
        )
        budget = self.resource_budget.scheduler_max_workers
        for node in self.pipeline.nodes:
            if node.max_concurrency > budget:
                raise ValueError(
                    f"node {node.id} max_concurrency exceeds resource_budget"
                )
            for key in ("max_workers", "concurrency"):
                value = node.node_config.get(key)
                if isinstance(value, int) and value > budget:
                    raise ValueError(
                        f"node {node.id} node_config.{key} exceeds resource_budget"
                    )
        return self
