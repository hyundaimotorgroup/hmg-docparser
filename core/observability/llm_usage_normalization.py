"""Canonical provider accounting. Missing, invalid and reported zero remain distinct."""

from __future__ import annotations
from collections.abc import Mapping
from copy import deepcopy
import math

FIELDS = (
    "input_tokens",
    "regular_input_tokens",
    "output_tokens",
    "response_output_tokens",
    "reasoning_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "total_tokens",
    "unclassified_tokens",
)
_RAW_KEYS = frozenset(
    "prompt_tokens completion_tokens input_tokens output_tokens total_tokens promptTokenCount candidatesTokenCount thoughtsTokenCount totalTokenCount cachedContentTokenCount prompt_token_count candidates_token_count thoughts_token_count total_token_count cached_content_token_count prompt_tokens_details completion_tokens_details input_tokens_details output_tokens_details cache_read_input_tokens cache_creation_input_tokens cache_creation ephemeral_5m_input_tokens ephemeral_1h_input_tokens cached_tokens cache_write_tokens cache_creation_tokens reasoning_tokens cost cost_usd".split()
)


_NORMALIZERS = {}


def register_usage_normalizer(profile, normalizer, *, raw_fields=()):
    """Register a trusted backend semantics profile and numeric usage field names."""
    global _RAW_KEYS
    if (
        profile in _NORMALIZERS
        or profile in {"openai", "anthropic", "gemini"}
        or not callable(normalizer)
    ):
        raise ValueError("duplicate or invalid usage normalizer")
    _NORMALIZERS[profile] = normalizer
    _RAW_KEYS = _RAW_KEYS | frozenset(raw_fields)


def object_to_dict(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_unset=True, exclude_none=False)
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "__dict__"):
        return {k: v for k, v in vars(value).items() if not k.startswith("_")}
    return {}


def safe_raw_usage(value, depth=0, *, errors=None):
    """Bound conversion before traversing nested objects; retain safe siblings."""
    result = {}
    try:
        if depth > 4:
            raise ValueError("usage depth exceeded")
        if isinstance(value, Mapping):
            raw = value
        else:
            raw = object_to_dict(value)
        for index, (key, item) in enumerate(raw.items()):
            if index >= 256:
                raise ValueError("usage size exceeded")
            if not isinstance(key, str) or key not in _RAW_KEYS:
                continue
            if isinstance(item, Mapping) or hasattr(item, "model_dump"):
                result[key] = safe_raw_usage(item, depth + 1, errors=errors)
            elif type(item) is int and not -(2**63) <= item <= 2**63 - 1:
                result[key] = "<invalid>"
            elif item is None or type(item) in (int, float, bool):
                result[key] = (
                    item
                    if type(item) is not float or math.isfinite(item)
                    else "<invalid>"
                )
            elif (
                isinstance(item, str) and key in {"cost", "cost_usd"} and len(item) < 80
            ):
                result[key] = item
            else:
                result[key] = "<invalid>"
    except Exception:
        if errors is not None and "usage_collection_failed" not in errors:
            errors.append("usage_collection_failed")
    return result


def valid_count(value):
    return type(value) is int and 0 <= value <= 2**63 - 1


def normalize_usage(
    raw_usage, *, api_type=None, capability=None, metadata=None, snapshots=()
):
    raw = safe_raw_usage(raw_usage)
    metadata = metadata or {}
    values = dict.fromkeys(FIELDS)
    sources = dict.fromkeys(FIELDS, "missing")
    errors = []
    write_breakdown = {}

    def pick(field, data, *keys):
        present = [(k, data[k]) for k in keys if k in data]
        if not present:
            return
        vals = [v for _, v in present]
        if any(v != vals[0] for v in vals[1:]):
            errors.append(field + ": conflicting aliases")
            sources[field] = "invalid"
            return
        v = vals[0]
        if v is None:
            sources[field] = "null"
        elif valid_count(v):
            values[field] = v
            sources[field] = "reported"
        else:
            sources[field] = "invalid"
            errors.append(field + ": invalid count")

    def derive(field, value):
        values[field] = value
        sources[field] = "derived"

    semantics = getattr(capability, "usage_semantics", None) or api_type
    if semantics in _NORMALIZERS:
        result = _NORMALIZERS[semantics](
            deepcopy(raw), deepcopy(metadata), deepcopy(snapshots)
        )
        canonical = {field: result.get(field) for field in FIELDS}
        invalid = [
            field + ": invalid custom count"
            for field, value in canonical.items()
            if value is not None and not valid_count(value)
        ]
        for field in FIELDS:
            if canonical[field] is not None and not valid_count(canonical[field]):
                canonical[field] = None
        a, b, total = (
            canonical[f] for f in ("input_tokens", "output_tokens", "total_tokens")
        )
        if a is not None and b is not None and total is not None and total < a + b:
            invalid.append("total below input plus output")
        for f in ("reasoning_tokens", "response_output_tokens"):
            if canonical[f] is not None and b is not None and canonical[f] > b:
                invalid.append(f + ": exceeds output")
        caches = [canonical[f] for f in ("cache_read_tokens", "cache_write_tokens")]
        if a is not None and sum(v for v in caches if v is not None) > a:
            invalid.append("cache exceeds input")
        field_sources = {
            field: "reported" if canonical[field] is not None else "missing"
            for field in FIELDS
        }
        field_sources.update(
            {
                field: "invalid"
                for field in FIELDS
                if any(e.startswith(field + ":") for e in invalid)
            }
        )
        return {
            **canonical,
            "field_sources": field_sources,
            "errors": invalid,
            "raw_available": bool(raw),
            "tokens_complete": not invalid
            and all(
                canonical[f] is not None
                for f in ("input_tokens", "output_tokens", "total_tokens")
            ),
            "prompt_tokens": canonical["input_tokens"],
            "completion_tokens": canonical["output_tokens"],
            "cached_prompt_tokens": canonical["cache_read_tokens"],
            "estimated": False,
        }

    if semantics == "gemini":
        pick("input_tokens", raw, "promptTokenCount", "prompt_token_count")
        pick(
            "response_output_tokens",
            raw,
            "candidatesTokenCount",
            "candidates_token_count",
        )
        pick("reasoning_tokens", raw, "thoughtsTokenCount", "thoughts_token_count")
        pick(
            "cache_read_tokens",
            raw,
            "cachedContentTokenCount",
            "cached_content_token_count",
        )
        pick("total_tokens", raw, "totalTokenCount", "total_token_count")
        a, b, total = (
            values["input_tokens"],
            values["response_output_tokens"],
            values["total_tokens"],
        )
        previous_positive = any(
            any(
                valid_count(s.get(k)) and s[k] > 0
                for k in ("thoughtsTokenCount", "thoughts_token_count")
            )
            for s in snapshots
        )
        finish = str(metadata.get("finish_reason", "")).split(".")[-1].upper()
        omitted = not any(
            k in raw for k in ("thoughtsTokenCount", "thoughts_token_count")
        )
        if (
            omitted
            and getattr(capability, "omitted_thinking_is_zero", False)
            and a is not None
            and b is not None
            and metadata.get("response_complete") is True
            and metadata.get("usage_final") is True
            and metadata.get("request_outcome") == "success"
            and finish in {"STOP", "FINISH_REASON_STOP"}
            and (total is None or total >= a + b)
            and not previous_positive
            and not errors
        ):
            derive("reasoning_tokens", 0)
        elif omitted and previous_positive:
            errors.append("reasoning_tokens: earlier positive snapshot lost")
        if values["reasoning_tokens"] is not None and b is not None:
            derive("output_tokens", b + values["reasoning_tokens"])
    elif semantics == "anthropic":
        pick("input_tokens", raw, "input_tokens")
        pick("regular_input_tokens", raw, "input_tokens")
        pick("output_tokens", raw, "output_tokens")
        pick("cache_read_tokens", raw, "cache_read_input_tokens")
        pick("cache_write_tokens", raw, "cache_creation_input_tokens")
        for ttl, key in (
            ("5m", "ephemeral_5m_input_tokens"),
            ("1h", "ephemeral_1h_input_tokens"),
        ):
            creation = raw.get("cache_creation") or {}
            if isinstance(creation, Mapping) and key in creation:
                write_breakdown[ttl] = creation[key]
                if not valid_count(creation[key]):
                    errors.append("cache_write_breakdown: invalid count")
        if write_breakdown and all(valid_count(v) for v in write_breakdown.values()):
            if (
                values["cache_write_tokens"] is None
                and len(write_breakdown) == 2
                and sources["cache_write_tokens"] == "missing"
            ):
                derive("cache_write_tokens", sum(write_breakdown.values()))
            elif (
                values["cache_write_tokens"] is not None
                and sum(write_breakdown.values()) > values["cache_write_tokens"]
            ):
                errors.append("cache_write_breakdown: exceeds cache write")
        pick("reasoning_tokens", raw, "reasoning_tokens")
        parts = [
            values[k]
            for k in ("input_tokens", "cache_read_tokens", "cache_write_tokens")
        ]
        if all(v is not None for v in parts):
            derive("input_tokens", sum(parts))
        else:
            values["input_tokens"] = None
            sources["input_tokens"] = "missing"
        if (
            values["output_tokens"] is not None
            and values["reasoning_tokens"] is not None
        ):
            if values["reasoning_tokens"] <= values["output_tokens"]:
                derive(
                    "response_output_tokens",
                    values["output_tokens"] - values["reasoning_tokens"],
                )
            else:
                errors.append("reasoning exceeds output")
    else:
        pick("input_tokens", raw, "prompt_tokens", "input_tokens")
        pick("output_tokens", raw, "completion_tokens", "output_tokens")
        pick("total_tokens", raw, "total_tokens")
        details = object_to_dict(
            raw.get("prompt_tokens_details", raw.get("input_tokens_details"))
        )
        pick("cache_read_tokens", details, "cached_tokens")
        pick(
            "cache_write_tokens", details, "cache_write_tokens", "cache_creation_tokens"
        )
        details = object_to_dict(
            raw.get("completion_tokens_details", raw.get("output_tokens_details"))
        )
        pick("reasoning_tokens", details, "reasoning_tokens")
        if (
            semantics == "openai"
            and values["reasoning_tokens"] is not None
            and values["output_tokens"] is not None
        ):
            if values["reasoning_tokens"] <= values["output_tokens"]:
                derive(
                    "response_output_tokens",
                    values["output_tokens"] - values["reasoning_tokens"],
                )
            else:
                errors.append("reasoning exceeds output")
    a, b, total = (
        values["input_tokens"],
        values["output_tokens"],
        values["total_tokens"],
    )
    if a is not None and b is not None:
        if sources["total_tokens"] == "missing":
            derive("total_tokens", a + b)
        elif total is not None:
            if total < a + b:
                errors.append("total below input plus output")
            else:
                derive("unclassified_tokens", total - a - b)
    for key in ("cache_read_tokens", "cache_write_tokens"):
        if values[key] is not None and a is not None and values[key] > a:
            errors.append(key + ": exceeds input")
    if (
        a is not None
        and all(
            values[k] is not None for k in ("cache_read_tokens", "cache_write_tokens")
        )
        and values["cache_read_tokens"] + values["cache_write_tokens"] > a
    ):
        errors.append("cache exceeds input")
    return {
        **values,
        "field_sources": sources,
        "errors": errors,
        "raw_available": bool(raw),
        "cache_write_breakdown": write_breakdown,
        "tokens_complete": not errors
        and all(
            values[k] is not None
            for k in ("input_tokens", "output_tokens", "total_tokens")
        ),
        "prompt_tokens": a,
        "completion_tokens": b,
        "cached_prompt_tokens": values["cache_read_tokens"],
        "estimated": False,
    }
