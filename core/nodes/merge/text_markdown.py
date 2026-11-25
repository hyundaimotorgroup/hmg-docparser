from __future__ import annotations

from core.domain.markdown.models import PageMarkdownDTO
from core.engine.runtime.time_budget import remaining_timeout_seconds
from core.interfaces.node import Node, NodeContext, NodeResult
from core.observability.llm_usage import build_llm_observability
from core.services.model_routing import node_inference_options
from core.services.text_markdown_merge import merge_one_page_markdown


class TextMarkdownLLMMergeNode(Node):
    node_name = "text_markdown_llm_merger"
    input_type = "page_markdown_dto@v1"
    output_type = "page_markdown_dto@v1"
    is_page_parallel = True

    def run(self, context: NodeContext, value: object) -> NodeResult:
        primary, secondary = _coerce_two_pages(value)

        model_name = _str_config(context, "model_name", "llm_model_name", "")
        if not model_name:
            raise ValueError(
                "text_markdown_llm_merger requires model_name or runtime llm_model_name"
            )

        usage_callback, trace_metadata = build_llm_observability(context)
        merged = merge_one_page_markdown(
            primary,
            secondary,
            model_name=model_name,
            provider=_optional_str(context.config.get("provider"))
            or _optional_str(_runtime_config(context).get("llm_provider")),
            base_url=_optional_str(context.config.get("base_url"))
            or _optional_str(_runtime_config(context).get("llm_base_url")),
            api_key=_optional_str(context.config.get("api_key"))
            or _optional_str(_runtime_config(context).get("llm_api_key")),
            api_version=_optional_str(context.config.get("api_version"))
            or _optional_str(_runtime_config(context).get("llm_api_version"))
            or _optional_str(
                _runtime_config(context).get("llm_internal_api_api_version")
            ),
            project_id=_optional_str(context.config.get("project_id"))
            or _optional_str(_runtime_config(context).get("llm_project_id"))
            or _optional_str(
                _runtime_config(context).get("llm_internal_api_project_id")
            ),
            api_type=_optional_str(context.config.get("api_type"))
            or _optional_str(_runtime_config(context).get("llm_api_type")),
            extra_body=_dict_config(context, "extra_body", "llm_extra_body"),
            inference_options=node_inference_options(context),
            usage_callback=usage_callback,
            trace_metadata=trace_metadata,
            timeout_seconds=remaining_timeout_seconds(
                _runtime_config(context), reserve_seconds=5.0
            ),
        )
        return NodeResult(
            value=merged,
            metadata={
                "page_no": merged.page.page_no,
                "markdown_length": len(merged.markdown or ""),
            },
        )


def _coerce_two_pages(value: object) -> tuple[PageMarkdownDTO, PageMarkdownDTO]:
    if (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(v, PageMarkdownDTO) for v in value)
    ):
        return value[0], value[1]
    raise TypeError(
        "text_markdown_llm_merger expects [primary_page, secondary_page] (two PageMarkdownDTO)"
    )


def _runtime_config(context: NodeContext) -> dict[str, object]:
    value = context.metadata.get("runtime_config", {})
    return value if isinstance(value, dict) else {}


def _str_config(
    context: NodeContext, node_key: str, runtime_key: str, default: str
) -> str:
    node_value = _optional_str(context.config.get(node_key))
    if node_value is not None:
        return node_value
    runtime_value = _optional_str(_runtime_config(context).get(runtime_key))
    return runtime_value if runtime_value is not None else default


def _dict_config(
    context: NodeContext, node_key: str, runtime_key: str
) -> dict[str, object]:
    value = context.config.get(node_key, _runtime_config(context).get(runtime_key, {}))
    return value if isinstance(value, dict) else {}


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
