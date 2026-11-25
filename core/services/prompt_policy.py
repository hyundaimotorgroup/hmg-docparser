"""Deterministic input boundaries. Host policy is never read from user overrides."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class PromptPolicy:
    max_codepoints: int = 8192
    max_bytes: int = 32768
    max_run_bytes: int = 131072
    max_context_bytes: int = 4 * 1024 * 1024
    max_output_bytes: int = 4 * 1024 * 1024

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError("prompt policy limits must be positive integers")

    @classmethod
    def from_mapping(cls, value):
        if value is None:
            return cls()
        if not isinstance(value, Mapping) or set(value) - set(cls.__dataclass_fields__):
            raise ValueError("invalid host prompt_policy")
        return cls(**value)


DEFAULT_PROMPT_POLICY = PromptPolicy()
_BIDI = (
    frozenset(range(0x202A, 0x202F))
    | frozenset(range(0x2066, 0x206A))
    | {0x200E, 0x200F, 0x061C}
)


def validate_user_prompt(value, policy=DEFAULT_PROMPT_POLICY):
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError("user_prompt must be a string or null")
    if len(value) > policy.max_codepoints:
        raise ValueError(
            f"user_prompt exceeds {policy.max_codepoints} Unicode code points"
        )
    if any(
        (ord(c) < 32 and c not in "\n\r\t")
        or 0x7F <= ord(c) <= 0x9F
        or 0xD800 <= ord(c) <= 0xDFFF
        or ord(c) in _BIDI
        for c in value
    ):
        raise ValueError("user_prompt contains prohibited control characters")
    if len(value.encode("utf-8")) > policy.max_bytes:
        raise ValueError(f"user_prompt exceeds {policy.max_bytes} UTF-8 bytes")
    return value if value.strip() else None


def prepare_node_prompts(nodes, overrides=None, policy=DEFAULT_PROMPT_POLICY):
    from core.engine.config.node_config import PromptedModelConfig, NODE_CONFIG_SCHEMAS

    if overrides is None:
        overrides = {}
    if not isinstance(overrides, Mapping):
        raise ValueError("node_overrides must be a mapping")
    eligible = {
        n.id: n
        for n in nodes
        if issubclass(NODE_CONFIG_SCHEMAS[n.node], PromptedModelConfig)
    }
    if set(overrides) - set(eligible):
        raise ValueError("node_overrides contains unknown or non-prompted node IDs")
    for data in overrides.values():
        if not isinstance(data, Mapping) or set(data) - {"user_prompt"}:
            raise ValueError("node_overrides accepts only user_prompt")
        if "user_prompt" in data:
            validate_user_prompt(data["user_prompt"], policy)
    resolved = {}
    for node_id, node in eligible.items():
        original = validate_user_prompt(node.node_config.get("user_prompt"), policy)
        data = overrides.get(node_id, {})
        resolved[node_id] = (
            validate_user_prompt(data["user_prompt"], policy)
            if "user_prompt" in data
            else original
        )
    if (
        sum(len((p or "").encode("utf-8")) for p in resolved.values())
        > policy.max_run_bytes
    ):
        raise ValueError(
            f"final user_prompt total exceeds {policy.max_run_bytes} UTF-8 bytes"
        )
    return resolved


def node_user_prompt(context):
    runtime = context.metadata.get("runtime_config") or {}
    policy = PromptPolicy.from_mapping(runtime.get("_host_prompt_policy"))
    override = (runtime.get("node_overrides") or {}).get(context.node_id, {})
    if not isinstance(override, Mapping) or set(override) - {"user_prompt"}:
        raise ValueError("node_overrides accepts only user_prompt")
    return validate_user_prompt(
        override.get("user_prompt")
        if "user_prompt" in override
        else context.config.get("user_prompt"),
        policy,
    )


ENGINE_FIELDS = frozenset(
    {
        "model",
        "messages",
        "system",
        "systeminstruction",
        "system_instruction",
        "contents",
        "tools",
        "tool_choice",
        "response_format",
        "response_schema",
        "responseschema",
        "response_mime_type",
        "responsemimetype",
        "stream",
        "stream_options",
        "auth",
        "authorization",
        "api_key",
        "base_url",
        "headers",
        "extra_headers",
        "endpoint",
        "extra_body",
        "input",
    }
)


def validate_extra_body(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("extra_body must be a mapping")
    for key, item in value.items():
        if str(key).lower() in ENGINE_FIELDS:
            raise ValueError("extra_body cannot replace engine-owned request fields")
        if isinstance(item, dict):
            validate_extra_body(item)
        elif isinstance(item, list):
            for nested in item:
                if isinstance(nested, dict):
                    validate_extra_body(nested)
    return value


def safe_validation_details(exc):
    if not hasattr(exc, "errors"):
        return []
    details = []
    for error in exc.errors(include_input=False, include_context=False):
        message = "invalid configuration value"
        public = error.get("msg", "")
        if public.startswith(
            (
                "Value error, user_prompt ",
                "Value error, final user_prompt ",
                "Value error, extra_body ",
                "Value error, reasoning ",
                "Value error, effort mode ",
                "Value error, budget mode ",
            )
        ):
            message = public.removeprefix("Value error, ")
        elif error["type"] == "string_type":
            message = "value must be a strict string or null where allowed"
        details.append(
            {"loc": list(error["loc"]), "type": error["type"], "msg": message}
        )
    return details
