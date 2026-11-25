"""Strict, public node-configuration schemas for native pipeline YAML."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from core.domain.inference.models import ReasoningConfig

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)


class NodeConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class EmptyConfig(NodeConfigModel):
    pass


class MarkdownLoaderConfig(NodeConfigModel):
    encoding: str = "utf-8"


class SplitConfig(NodeConfigModel):
    keep_page_artifacts: StrictBool = False
    output_dir: str | None = None


class LayoutConfig(NodeConfigModel):
    version: Literal["v1", "v2"]
    v1_transport: Literal["triton", "fastapi"] = "triton"
    v1_server_url: str | None = None
    v1_model_name: str | None = None
    v1_prompt: str | None = None
    v1_max_batch_size: StrictInt | None = None
    v1_ssl: StrictBool | None = None
    v1_token: str | None = None
    v2_server_url: str | None = None
    v2_model_name: str | None = None
    v2_prompt: str | None = None
    v2_ssl: StrictBool | None = None
    v2_token: str | None = None
    target_size: StrictInt | None = None
    skip_levels: list[StrictInt] = Field(default_factory=list)
    crop_output_dir: str | None = None
    keep_page_artifacts: StrictBool = False

    @field_validator("target_size", "v1_max_batch_size")
    @classmethod
    def validate_positive(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("value must be >= 1")
        return value

    @model_validator(mode="after")
    def validate_version_connection(self) -> "LayoutConfig":
        if self.version == "v1" and not self.v1_server_url:
            raise ValueError("v1_server_url is required when version is v1")
        if self.version == "v2" and not self.v2_server_url:
            raise ValueError("v2_server_url is required when version is v2")
        return self


class LabelFilterConfig(NodeConfigModel):
    input_labels: list[str] | None = None
    input_exclude_labels: list[str] | None = None


class OCRConfig(NodeConfigModel):
    transport: Literal["triton", "fastapi"] = "triton"
    server_url: str
    model_name: str = "paddle"
    ssl: StrictBool = False
    token: str | None = None
    padding: StrictInt = 75
    concurrency: StrictInt = 8
    min_score: StrictFloat | StrictInt = 0.9


class PromptedModelConfig(NodeConfigModel):
    user_prompt: StrictStr | None = None

    @field_validator("user_prompt")
    @classmethod
    def validate_prompt(cls, value, info):
        from core.services.prompt_policy import (
            validate_user_prompt,
            DEFAULT_PROMPT_POLICY,
        )

        return validate_user_prompt(
            value, (info.context or {}).get("prompt_policy", DEFAULT_PROMPT_POLICY)
        )


class ModelConfig(PromptedModelConfig):
    provider: StrictStr
    model_name: str
    base_url: str
    api_key: str | None = None
    project_id: str | None = None
    api_type: Literal["openai", "anthropic", "gemini"] | None = None
    api_version: str | None = None
    extra_body: dict[str, Any] = Field(default_factory=dict)
    reasoning: ReasoningConfig | None = None
    deployment: str | None = None
    max_workers: StrictInt | None = None
    progress_weight: StrictFloat | StrictInt | None = None

    @field_validator("extra_body")
    @classmethod
    def validate_extra(cls, value):
        from core.services.prompt_policy import validate_extra_body

        return validate_extra_body(value)


class BlockContextRestoreConfig(ModelConfig):
    """Beta page-local restoration with fixed, verified role/model contracts."""
    block_kind: Literal["text", "table", "image"]
    skip_levels: list[Annotated[StrictInt, Field(ge=0)]] = Field(default_factory=lambda: [1])
    max_workers: Annotated[StrictInt, Field(ge=1)] = 1
    max_processing_attempts_per_block: Annotated[StrictInt, Field(ge=1, le=2)] = 2
    few_shot_examples: list[Annotated[StrictInt, Field(ge=1)]] = Field(default_factory=lambda: [1, 2])
    table_input_max_tokens: Annotated[StrictInt, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def validate_role(self):
        expected = "gpt-6-luna" if self.block_kind == "text" else "gemini-3.8-flash"
        protocol = "openai" if self.block_kind == "text" else "gemini"
        if self.model_name != expected or self.api_type != protocol:
            raise ValueError(f"{self.block_kind} restoration requires {expected} / {protocol}")
        if self.table_input_max_tokens is not None and self.block_kind != "table":
            raise ValueError("table_input_max_tokens is only supported for table restoration")
        if self.block_kind == "table" and self.table_input_max_tokens is None:
            self.table_input_max_tokens = 256
        ids = self.few_shot_examples
        maximum = 5 if self.block_kind == "table" else 3
        if len(ids) > 2 or len(set(ids)) != len(ids) or any(i > maximum for i in ids):
            raise ValueError("select zero to two distinct examples available for the role")
        return self


class GlobalContextConfig(ModelConfig):
    skip_levels: list[Annotated[StrictInt, Field(ge=0)]] = Field(default_factory=list)


class RoutedVLMConfig(ModelConfig):
    level2_model_name: str | None = None
    level2_provider: str | None = None
    level2_base_url: str | None = None
    level2_api_key: str | None = None
    level2_api_version: str | None = None
    level2_project_id: str | None = None
    level2_deployment: str | None = None
    level2_extra_body: dict[str, Any] | None = None
    level2_reasoning: ReasoningConfig | None = None
    level3_model_name: str | None = None
    level3_provider: str | None = None
    level3_base_url: str | None = None
    level3_api_key: str | None = None
    level3_api_version: str | None = None
    level3_project_id: str | None = None
    level3_deployment: str | None = None
    level3_extra_body: dict[str, Any] | None = None
    level3_reasoning: ReasoningConfig | None = None
    level2_api_type: Literal["openai", "anthropic", "gemini"] | None = None
    level3_api_type: Literal["openai", "anthropic", "gemini"] | None = None


class TableConfig(RoutedVLMConfig):
    table_output_format: Literal["markdown", "html", "json", "toon"] = "markdown"


class ImageConfig(RoutedVLMConfig):
    use_vlm_parse: StrictBool = True


class TextMarkdownMergeConfig(ModelConfig):
    primary_node_id: str


class MergeConfig(NodeConfigModel):
    merge_key: Literal["block_id"]
    field_priority: dict[str, list[str]]


class LayoutMarkdownConfig(NodeConfigModel):
    restore_tables: StrictBool = False
    include_page_marker: StrictBool = True
    include_table_crop_images: StrictBool = False


class SaverConfig(NodeConfigModel):
    task_name: str
    save_debug_artifacts: StrictBool = False


class AssemblerConfig(SaverConfig):
    save_suffix: str = ""


class RouterConfig(NodeConfigModel):
    enabled: StrictBool = True
    server_url: str
    ssl: StrictBool = False
    token: str | None = None
    timeout_seconds: StrictFloat | StrictInt | None = None
    max_batch_size: StrictInt = 16
    target_size: StrictInt | None = None
    route_report_path: str | None = None


class WholePageConfig(ModelConfig):
    trigger_levels: list[StrictInt]
    prompt: StrictStr
    dpi: StrictInt = 300
    disable_text_only_gate: StrictBool = False


class ConfluenceUploadConfig(NodeConfigModel):
    token: str
    space_id: str
    parent_id: str
    base_url: str
    email: str | None = None
    title: str | None = None
    update_existing: StrictBool = True
    timeout: StrictFloat | StrictInt | None = None
    page_split_size: StrictInt | None = 50
    split_title_template: str = "{title}_part_{part:02d}"
    vlm_caption_start_tag: str = "(VLM image caption)"
    vlm_caption_end_tag: str = "(/VLM image caption)"
    vlm_caption_extract_output_only: StrictBool = True
    vlm_caption_format_mode: str = "panel_markdown"
    vlm_caption_panel_title: str = "Image description"
    vlm_caption_expand_title: str = "Show image description"
    vlm_caption_custom_template: str | None = None

    @field_validator("token", "space_id", "parent_id", "base_url")
    @classmethod
    def validate_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()

    @field_validator("base_url")
    @classmethod
    def validate_https_base_url(cls, value: str) -> str:
        from urllib.parse import urlparse

        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "base_url must be an absolute HTTPS URL without query or fragment"
            )
        return value.rstrip("/")

    @field_validator("timeout", "page_split_size")
    @classmethod
    def validate_positive(cls, value: int | float | None) -> int | float | None:
        if value is not None and value < 1:
            raise ValueError("value must be >= 1")
        return value


NODE_CONFIG_SCHEMAS: dict[str, type[NodeConfigModel]] = {
    "markdown_document_loader": MarkdownLoaderConfig,
    "pdf_page_split_loader": SplitConfig,
    "pdfplumber_extractor": EmptyConfig,
    "dolphin_layout_parser": LayoutConfig,
    "dolphin_vllm_layout_parser": LayoutConfig,
    "layout.label_filter": LabelFilterConfig,
    "paddle_triton_ocr": OCRConfig,
    "table_vlm_caption_maker": TableConfig,
    "image_vlm_processor": ImageConfig,
    "layout.merge_page_enrichments": MergeConfig,
    "layout.block_context_restorer": BlockContextRestoreConfig,
    "layout_markdown_formatter": LayoutMarkdownConfig,
    "markdown_document_saver": SaverConfig,
    "markdown_document_assembler": AssemblerConfig,
    "text_markdown_llm_merger": TextMarkdownMergeConfig,
    "text_image_vlm_merger": ModelConfig,
    "global_context_extraction_vlm_merger": GlobalContextConfig,
    "whole_page_llm_processor": WholePageConfig,
    "stage1_page_router": RouterConfig,
    "stage2_element_router": RouterConfig,
    "confluence_uploader": ConfluenceUploadConfig,
}


def validate_node_config(
    node_name: str, value: dict[str, Any], *, context=None
) -> dict[str, Any]:
    schema = NODE_CONFIG_SCHEMAS.get(node_name)
    if schema is None:
        raise ValueError(f"no public node config schema registered: {node_name}")
    return schema.model_validate(value, context=context).model_dump(exclude_none=True)
