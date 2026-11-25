"""Resolve intent once, validate capability, then serialize through registered backends."""

from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
from core.domain.inference.models import ReasoningConfig
from core.adapters.models.capabilities import DEFAULT_CAPABILITIES
from core.services.prompt_policy import validate_extra_body

POLICY_VERSION = "oss-low-1"
LEGACY_KEYS = frozenset(
    {
        "reasoning_effort",
        "thinking",
        "thinking_config",
        "thinkingConfig",
        "output_config",
    }
)
_SERIALIZERS = {}


def register_reasoning_serializer(name, serializer):
    if name in _SERIALIZERS:
        raise ValueError("duplicate reasoning serializer")
    _SERIALIZERS[name] = serializer


def strip_legacy_reasoning(extra):
    result = deepcopy(extra or {})
    for key in LEGACY_KEYS:
        result.pop(key, None)
    for key in ("generationConfig", "generation_config"):
        if isinstance(result.get(key), dict):
            result[key] = strip_legacy_reasoning(result[key])
    return result


def legacy_reasoning(extra):
    roots = [extra or {}]
    for key in ("generationConfig", "generation_config"):
        if key in roots[0]:
            if not isinstance(roots[0][key], dict):
                raise ValueError("invalid legacy generation configuration")
            roots.append(roots[0][key])
    found = []
    for options in roots:
        if "reasoning_effort" in options:
            found.append(
                ReasoningConfig(mode="effort", effort=options["reasoning_effort"])
            )
        for key in ("thinking_config", "thinkingConfig"):
            if key not in options:
                continue
            thinking = options[key]
            allowed = {
                "thinkingLevel",
                "thinking_level",
                "thinkingBudget",
                "thinking_budget",
            }
            if (
                not isinstance(thinking, dict)
                or not thinking
                or set(thinking) - allowed
            ):
                raise ValueError("unsupported legacy thinking configuration")
            # Alias duplicates and mixed budget/level are ambiguous declarations.
            if len(thinking) != 1:
                raise ValueError("conflicting legacy reasoning options")
            field, value = next(iter(thinking.items()))
            if field in {"thinkingLevel", "thinking_level"}:
                found.append(
                    ReasoningConfig(
                        mode="effort",
                        effort=value.lower() if isinstance(value, str) else value,
                    )
                )
            else:
                found.append(
                    ReasoningConfig(mode="disabled")
                    if type(value) is int and value == 0
                    else ReasoningConfig(mode="budget", budget_tokens=value)
                )
        output = options.get("output_config")
        if "output_config" in options:
            if not isinstance(output, dict) or set(output) != {"effort"}:
                raise ValueError("unsupported legacy output configuration")
            if "thinking" not in options:
                raise ValueError("legacy output effort requires adaptive thinking")
        if "thinking" in options:
            thinking = options["thinking"]
            if not isinstance(thinking, dict) or set(thinking) - {
                "type",
                "budget_tokens",
            }:
                raise ValueError("unsupported legacy thinking configuration")
            mode = {
                "enabled": "budget",
                "disabled": "disabled",
                "adaptive": "adaptive",
            }.get(thinking.get("type"))
            if mode is None:
                raise ValueError("unsupported legacy thinking type")
            found.append(
                ReasoningConfig(
                    mode=mode,
                    budget_tokens=thinking.get("budget_tokens"),
                    effort=output["effort"] if output is not None else None,
                )
            )
    if len(found) > 1:
        raise ValueError("conflicting legacy reasoning options")
    return found[0] if found else None


@dataclass(frozen=True, slots=True)
class ResolvedReasoning:
    request_model: str
    requested: ReasoningConfig | None
    effective: ReasoningConfig | None
    source: str
    capability: object

    # Serialized dictionaries are generated fresh, never stored in mutable telemetry.
    def serialize(self):
        if self.effective is None or self.effective.mode == "provider_default":
            return {}
        return deepcopy(
            validate_extra_body(
                _SERIALIZERS[self.capability.serializer](self.effective)
            )
        )

    def metadata(self):
        return {
            "requested": self.requested.model_dump() if self.requested else None,
            "effective": self.effective.model_dump() if self.effective else None,
            "sent_options": self.serialize(),
            "source": self.source,
            "policy_version": POLICY_VERSION,
            "capability_version": self.capability.version if self.capability else None,
            "request_model": self.request_model,
            "actual_server_effort": "unknown",
        }


def resolve_reasoning(
    provider,
    api_type,
    model,
    reasoning=None,
    extra_body=None,
    *,
    registry=DEFAULT_CAPABILITIES,
    deployment=None,
    schema=None,
    max_output_tokens=32000,
):
    validate_extra_body(extra_body)
    explicit = (
        ReasoningConfig.model_validate(reasoning) if reasoning is not None else None
    )
    legacy = legacy_reasoning(extra_body)
    actual_model = model
    suffix_intent = None
    # Only remove an exact registered model suffix, never guess based on a substring.
    if registry.get(provider, api_type, model, deployment) is None:
        for sep in ("-", "_"):
            base, _, suffix = model.rpartition(sep)
            cap = registry.get(provider, api_type, base, deployment)
            if cap and suffix in cap.efforts:
                actual_model = base
                suffix_intent = ReasoningConfig(mode="effort", effort=suffix)
                break
    cap = registry.get(provider, api_type, actual_model, deployment)
    effective = explicit or legacy or suffix_intent
    source = (
        "explicit"
        if explicit
        else "legacy"
        if legacy
        else "suffix"
        if suffix_intent
        else "omitted"
    )
    if effective is None and cap and cap.default_low:
        effective = ReasoningConfig(mode="effort", effort="low")
        source = "default_low"
    if schema and cap and not cap.schema:
        raise ValueError("structured response schema unsupported for this model")
    if (
        cap
        and not cap.sampling
        and any(k in (extra_body or {}) for k in ("temperature", "top_p"))
    ):
        raise ValueError("sampling parameters unsupported for this model")
    max_output_tokens = configured_output_budget(
        extra_body, api_type, cap, max_output_tokens
    )
    if effective and effective.mode != "provider_default":
        if cap is None or effective.mode not in cap.modes:
            raise ValueError("reasoning mode unsupported for configured model identity; remove reasoning or use provider_default, or supply a verified capability extension")
        if effective.effort is not None and effective.effort not in cap.efforts:
            raise ValueError(
                "reasoning effort unsupported for configured model identity"
            )
        if cap.serializer not in _SERIALIZERS:
            raise ValueError("reasoning serializer is not registered")
        if effective.mode == "budget":
            if effective.budget_tokens < cap.budget_min or (
                cap.budget_max and effective.budget_tokens > cap.budget_max
            ):
                raise ValueError("reasoning budget outside model capability")
            if api_type == "anthropic" and effective.budget_tokens >= max_output_tokens:
                raise ValueError("thinking budget must be below max output tokens")
        if (
            schema
            and api_type == "anthropic"
            and effective.mode in {"budget", "adaptive"}
            and not cap.forced_tool_with_thinking
        ):
            raise ValueError(
                "forced structured-output tool is incompatible with thinking for this model"
            )
    return ResolvedReasoning(actual_model, explicit, effective, source, cap)


def configured_output_budget(extra, api_type, capability=None, default=32000):
    """Validate native output limits without guessing unknown model limits."""
    extra = extra or {}
    roots = [extra]
    if api_type == "gemini":
        roots += [
            extra[k]
            for k in ("generationConfig", "generation_config")
            if isinstance(extra.get(k), dict)
        ]
    names = {
        "max_tokens",
        "max_completion_tokens",
        "max_output_tokens",
        "maxOutputTokens",
    }
    supplied = [(k, v) for root in roots for k, v in root.items() if k in names]
    if len(supplied) > 1:
        raise ValueError("conflicting output token limits")
    if not supplied:
        return default
    key, value = supplied[0]
    allowed = {
        "openai": {"max_tokens", "max_completion_tokens"},
        "anthropic": {"max_tokens"},
        "gemini": {"max_output_tokens", "maxOutputTokens"},
    }[api_type]
    parameter = getattr(capability, "output_token_parameter", None)
    if key not in allowed or (parameter and key != parameter):
        raise ValueError("output token parameter unsupported for this model/API")
    if type(value) is not int or value < 1:
        raise ValueError("output token limit must be a positive integer")
    limit = getattr(capability, "max_output_tokens", None)
    if limit is not None and value > limit:
        raise ValueError("output token limit exceeds model capability")
    return value


def _openai(r):
    return {"reasoning_effort": r.effort if r.mode == "effort" else "none"}


def _gemini(r):
    return (
        {"thinking_config": {"thinking_level": r.effort}}
        if r.mode == "effort"
        else {
            "thinking_config": {
                "thinking_budget": 0 if r.mode == "disabled" else r.budget_tokens
            }
        }
    )


def _anthropic(r):
    if r.mode == "budget":
        return {"thinking": {"type": "enabled", "budget_tokens": r.budget_tokens}}
    if r.mode == "disabled":
        return {"thinking": {"type": "disabled"}}
    result = {"thinking": {"type": "adaptive"}}
    if r.effort:
        result["output_config"] = {"effort": r.effort}
    return result


for _name, _fn in [("openai", _openai), ("gemini", _gemini), ("anthropic", _anthropic)]:
    register_reasoning_serializer(_name, _fn)
