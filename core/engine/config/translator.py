from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.engine.config.models import NativeRuntimeConfig, PipelineGraphConfig
from core.services.prompt_policy import PromptPolicy


def load_pipeline_graph_config(raw_config: Mapping[str, Any]) -> PipelineGraphConfig:
    """Validate the sole public configuration format and return its DAG."""
    return NativeRuntimeConfig.model_validate(
        raw_config,
        context={
            "prompt_policy": PromptPolicy.from_mapping(raw_config.get("prompt_policy"))
        },
    ).pipeline


def load_native_runtime_config(raw_config: Mapping[str, Any]) -> NativeRuntimeConfig:
    """Validate the complete public YAML contract without legacy translation."""
    return NativeRuntimeConfig.model_validate(
        raw_config,
        context={
            "prompt_policy": PromptPolicy.from_mapping(raw_config.get("prompt_policy"))
        },
    )
