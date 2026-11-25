"""Select immutable connection/level options without leaking legacy thinking."""

from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
from core.adapters.models.reasoning import strip_legacy_reasoning
from core.services.prompt_policy import node_user_prompt, PromptPolicy


@dataclass(frozen=True, slots=True)
class ModelConnection:
    model_name: str
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_version: str | None = None
    project_id: str | None = None
    api_type: str | None = None
    deployment: str | None = None

    def identity(self):
        from core.adapters.models.unified_client import (
            normalize_provider,
            _resolve_api_type,
        )

        provider = normalize_provider(self.provider)
        return (
            self.model_name,
            provider,
            _resolve_api_type(provider, self.api_type),
            self.base_url,
            self.api_version,
            self.deployment,
        )


@dataclass(frozen=True, slots=True)
class ModelRoute:
    connection: ModelConnection
    reasoning: object
    extra_body: dict

    def kwargs(self):
        return {
            **{
                k: getattr(self.connection, k)
                for k in self.connection.__dataclass_fields__
            },
            "reasoning": deepcopy(self.reasoning),
            "extra_body": deepcopy(self.extra_body),
        }


def select_model_route(config, *, level=None, defaults=None):
    defaults = defaults or {}
    keys = ModelConnection.__dataclass_fields__
    base = {k: config.get(k) or defaults.get(k) for k in keys}
    root = ModelConnection(**base)
    prefix = f"level{level}_" if level in (2, 3) else ""
    connection = (
        ModelConnection(**{k: config.get(prefix + k) or v for k, v in base.items()})
        if prefix
        else root
    )
    same = root.identity() == connection.identity()
    extra = deepcopy(config.get("extra_body", defaults.get("extra_body")) or {})
    if prefix and config.get(prefix + "extra_body") is not None:
        extra = deepcopy(config[prefix + "extra_body"])
    elif prefix and not same:
        extra = strip_legacy_reasoning(extra)
    reasoning = config.get(prefix + "reasoning") if prefix else config.get("reasoning")
    if prefix and reasoning is None and same:
        reasoning = config.get("reasoning")
    return ModelRoute(connection, reasoning, extra)


def node_model_options(context, level=None):
    runtime = context.metadata.get("runtime_config") or {}
    return {
        **select_model_route(context.config, level=level).kwargs(),
        "user_prompt": node_user_prompt(context),
        "prompt_policy": PromptPolicy.from_mapping(runtime.get("_host_prompt_policy")),
        "pricing_snapshot": runtime.get("_pricing_snapshot"),
        "capability_registry": runtime.get("_capability_registry"),
    }


def node_inference_options(context):
    options = node_model_options(context)
    return {
        k: v
        for k, v in options.items()
        if k
        in {
            "user_prompt",
            "reasoning",
            "deployment",
            "prompt_policy",
            "pricing_snapshot",
            "capability_registry",
        }
    }


def validate_model_routes(nodes, *, registry=None):
    """Validate all final configured routes before any pipeline provider call."""
    from core.engine.config.node_config import ModelConfig, NODE_CONFIG_SCHEMAS
    from core.adapters.models.capabilities import DEFAULT_CAPABILITIES
    from core.adapters.models.reasoning import resolve_reasoning
    from core.adapters.models.unified_client import (
        normalize_provider,
        _resolve_api_type,
    )
    from core.prompts.vlm import get_schema_vlm
    from core.prompts.llm import get_schema_llm

    for node in nodes:
        if not issubclass(NODE_CONFIG_SCHEMAS[node.node], ModelConfig):
            continue
        config = node.node_config
        if node.node == "layout.block_context_restorer":
            from core.prompts.block_context import RESPONSE_SCHEMA
            schema = RESPONSE_SCHEMA
        elif node.node == "whole_page_llm_processor":
            schema = get_schema_vlm("WHOLE_PAGE")
        elif node.node == "text_markdown_llm_merger":
            schema = get_schema_llm("COMBINE_TEXT")
        else:
            task = {
                "image_vlm_processor": "IMAGE_PARSE",
                "table_vlm_caption_maker": "TABLE_PARSE",
                "text_image_vlm_merger": "COMBINE_TEXT",
                "global_context_extraction_vlm_merger": "GLOBAL_CONTEXT_EXTRACTION",
            }.get(node.node)
            schema = get_schema_vlm(task) if task else None
        for level in (None, 2, 3):
            route = select_model_route(config, level=level)
            connection = route.connection
            provider = normalize_provider(connection.provider)
            api_type = _resolve_api_type(provider, connection.api_type)
            resolve_reasoning(
                provider,
                api_type,
                connection.model_name,
                route.reasoning,
                route.extra_body,
                registry=registry or DEFAULT_CAPABILITIES,
                deployment=connection.deployment,
                schema=schema,
                max_output_tokens=route.extra_body.get(
                    "max_tokens", route.extra_body.get("max_output_tokens", 32000)
                ),
            )
