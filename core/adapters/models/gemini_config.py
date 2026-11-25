from __future__ import annotations

from typing import Literal


_GEMINI_CONFIG_ALIASES: dict[str, tuple[str, ...]] = {
    "temperature": ("temperature",),
    "max_output_tokens": ("max_output_tokens", "maxOutputTokens"),
    "top_p": ("top_p", "topP"),
    "top_k": ("top_k", "topK"),
    "candidate_count": ("candidate_count", "candidateCount"),
    "stop_sequences": ("stop_sequences", "stopSequences"),
    "presence_penalty": ("presence_penalty", "presencePenalty"),
    "frequency_penalty": ("frequency_penalty", "frequencyPenalty"),
    "seed": ("seed",),
}

_REST_KEY_BY_NORMALIZED = {
    "temperature": "temperature",
    "max_output_tokens": "maxOutputTokens",
    "top_p": "topP",
    "top_k": "topK",
    "candidate_count": "candidateCount",
    "stop_sequences": "stopSequences",
    "presence_penalty": "presencePenalty",
    "frequency_penalty": "frequencyPenalty",
    "seed": "seed",
}


def merge_gemini_generation_config(
    base_config: dict[str, object],
    extra_body: dict[str, object] | None,
    *,
    target: Literal["sdk", "rest"],
) -> dict[str, object]:
    merged = dict(base_config)
    if not isinstance(extra_body, dict) or not extra_body:
        return merged

    allowed = {a for aliases in _GEMINI_CONFIG_ALIASES.values() for a in aliases} | {
        "generation_config",
        "generationConfig",
    }
    if any(set(source) - allowed for source in _gemini_config_sources(extra_body)):
        raise ValueError("unsupported Gemini generation option")
    for normalized_key, value in _collect_gemini_config_values(extra_body).items():
        if target == "rest":
            merged[_REST_KEY_BY_NORMALIZED[normalized_key]] = value
            continue
        merged[normalized_key] = value
    return merged


def _collect_gemini_config_values(extra_body: dict[str, object]) -> dict[str, object]:
    collected: dict[str, object] = {}
    for source in _gemini_config_sources(extra_body):
        for normalized_key, aliases in _GEMINI_CONFIG_ALIASES.items():
            value = _first_present_value(source, aliases)
            if value is not None:
                collected[normalized_key] = value
    return collected


def _gemini_config_sources(extra_body: dict[str, object]) -> list[dict[str, object]]:
    sources = [extra_body]
    for key in ("generation_config", "generationConfig"):
        nested = extra_body.get(key)
        if isinstance(nested, dict):
            sources.append(nested)
    return sources


def _first_present_value(
    source: dict[str, object], aliases: tuple[str, ...]
) -> object | None:
    for alias in aliases:
        if alias in source and source[alias] is not None:
            return source[alias]
    return None
