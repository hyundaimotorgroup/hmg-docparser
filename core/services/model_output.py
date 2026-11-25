"""Bounded structured response validation and non-executable Markdown output."""

from __future__ import annotations
import json
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from core.services.prompt_policy import DEFAULT_PROMPT_POLICY
from core.services.markdown_safety import sanitize_output_markdown
from core.domain.model_errors import EmptyModelResponse


def validate_model_output(value, schema=None, *, policy=DEFAULT_PROMPT_POLICY):
    if schema is None:
        if not isinstance(value, str):
            raise ValueError("provider returned non-text output")
        if not value.strip():
            raise EmptyModelResponse()
        if len(value.encode("utf-8")) > policy.max_output_bytes:
            raise ValueError("provider output exceeds host budget")
        sanitized = sanitize_output_markdown(value)
        if not sanitized.strip():
            raise ValueError("model output empty after safety processing")
        return sanitized
    if not isinstance(value, dict):
        raise ValueError("provider returned non-object structured output")
    try:
        size = len(
            json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        )
        if size > policy.max_output_bytes:
            raise ValueError("provider output exceeds host budget")
        Draft202012Validator.check_schema(schema)
        errors = Draft202012Validator(schema).iter_errors(value)
        if next(errors, None) is not None:
            raise ValueError("provider output violates response schema")
    except (TypeError, SchemaError, UnicodeError, RecursionError):
        raise ValueError("invalid structured provider output") from None
    if "output" in schema.get("properties", {}):
        required_output = "output" in schema.get("required", [])
        if "output" not in value and not required_output:
            return value
        if not isinstance(value.get("output"), str):
            raise ValueError("provider returned non-text structured output")
        if required_output and not value["output"].strip():
            raise EmptyModelResponse("empty_structured_output")
        sanitized = sanitize_output_markdown(value["output"])
        if required_output and not sanitized.strip():
            raise ValueError("model output empty after safety processing")
        return {**value, "output": sanitized}
    return value
