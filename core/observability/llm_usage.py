from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from core.interfaces.node import NodeContext
from core.observability.progress_tracker import progress_tracker


@dataclass(frozen=True)
class LangfuseSettings:
    enabled: bool = False
    public_key: str | None = None
    secret_key: str | None = None
    host: str | None = None
    trace_name: str = "pdf_parser_trace"

    @classmethod
    def from_config(cls, value: object) -> "LangfuseSettings":
        if not isinstance(value, Mapping):
            return cls()
        enabled = _bool_value(
            value.get("enabled", value.get("on", value.get(True, False)))
        )
        if not enabled:
            return cls()
        return cls(
            enabled=True,
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST"),
            trace_name=os.getenv("LANGFUSE_TRACE_NAME") or "pdf_parser_trace",
        )

    def usable(self) -> bool:
        return bool(self.enabled and self.public_key and self.secret_key and self.host)


class LangfuseSdkExporter:
    def __init__(self, settings: LangfuseSettings) -> None:
        self._settings = settings
        self._disabled_error: str | None = None
        self._client = None
        self._lock = RLock()

    def client(self) -> Any:
        with self._lock:
            if self._client is None:
                from langfuse import Langfuse

                self._client = Langfuse(
                    public_key=self._settings.public_key,
                    secret_key=self._settings.secret_key,
                    base_url=str(self._settings.host).rstrip("/"),
                    timeout=30,
                    flush_at=1,
                    flush_interval=1,
                )
            return self._client

    def record_generation(self, record: dict[str, object]) -> None:
        if not self._settings.usable() or self._disabled_error is not None:
            return

        usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
        metadata = (
            record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        )
        job_id = str(record.get("job_id") or "")
        node_name = str(
            metadata.get("node_id") or metadata.get("node_name") or "llm_call"
        )

        try:
            with self._lock:
                client = self.client()
                cost = record.get("cost") or {}
                complete = cost.get("status") == "complete"
                # Omitting model and usage on partial observations suppresses automatic pricing.
                generation = client.start_observation(
                    name=node_name,
                    as_type="generation",
                    model=_str_value(record.get("model_name")) if complete else None,
                    usage_details={
                        k: v
                        for k, v in {
                            "input": usage.get("input_tokens"),
                            "output": usage.get("output_tokens"),
                            "total": usage.get("total_tokens"),
                        }.items()
                        if type(v) is int
                    }
                    if complete
                    else None,
                    cost_details={"total": float(cost["amount_usd"])}
                    if complete
                    else None,
                    metadata={
                        "job_id": job_id,
                        "model_identity": record.get("model_name"),
                        "cost_status": cost.get("status"),
                        "pricing_fingerprint": cost.get("pricing_fingerprint"),
                        "known_subtotal_usd": cost.get("known_subtotal_usd"),
                        "estimated_input_usd": cost.get("estimated_input_usd"),
                        "estimated_subtotal_usd": cost.get("estimated_subtotal_usd"),
                        "estimate_bases": cost.get("estimate_bases"),
                        "tokens_complete": usage.get("tokens_complete"),
                        "field_sources": usage.get("field_sources"),
                    },
                )
                generation.end()
        except Exception:
            self._disabled_error = "Langfuse export failed"
            raise RuntimeError(self._disabled_error) from None

    def flush(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.flush()

    def shutdown(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.shutdown()


_EXPORTERS: dict[LangfuseSettings, LangfuseSdkExporter] = {}
_EXPORTERS_LOCK = RLock()
_FILE_LOCKS: dict[str, RLock] = {}
_FILE_LOCKS_LOCK = RLock()
_SENSITIVE_METADATA_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "access_token",
        "token",
        "secret",
        "secret_key",
        "password",
    }
)


def langfuse_config_from_raw(raw_config: object) -> dict[str, object]:
    if not isinstance(raw_config, Mapping):
        return {"enabled": False}
    settings = LangfuseSettings.from_config(raw_config.get("langfuse"))
    return {
        "enabled": settings.enabled,
    }


def build_llm_observability(
    context: NodeContext,
    *,
    extra_metadata: dict[str, object] | None = None,
) -> tuple[Any, dict[str, object]]:
    runtime_config = _runtime_config(context)
    settings = LangfuseSettings.from_config(runtime_config.get("langfuse"))
    metadata = {
        "job_id": context.job_id,
        "node_id": context.node_id,
        "node_name": context.node_name,
        "document_id": runtime_config.get("document_id"),
        # The runtime attaches this for page-parallel nodes.  Keep it in the
        # usage record so downstream evaluators can attribute tokens and cost
        # to the page that caused the call.
        "page_index": context.metadata.get("page_index"),
        # This private callable is consumed by UnifiedLLMClient and removed
        # before usage/telemetry serialization.
        "_cancellation_check": context.metadata.get("cancellation_check"),
        "pricing_error": runtime_config.get("_pricing_error"),
        **(extra_metadata or {}),
    }

    output_dir = _str_value(
        runtime_config.get("outputs") or runtime_config.get("output_dir")
    )

    def usage_callback(record: dict[str, object]) -> None:
        record = {**record, "job_id": context.job_id}
        record_metadata = (
            record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        )
        record["metadata"] = persistent_metadata({**metadata, **record_metadata})
        try:
            progress_tracker.add_llm_usage(context.job_id, record)
        except Exception:
            safe_accounting_diagnostic(context.job_id, "accounting tracker failed")
        if output_dir:
            try:
                _append_usage_line(record, output_dir)
            except Exception:
                safe_accounting_diagnostic(
                    context.job_id, "accounting JSONL write failed"
                )
        if settings.usable():
            try:
                _exporter_for(settings).record_generation(record)
            except Exception:
                safe_accounting_diagnostic(context.job_id, "Langfuse export failed")

    return usage_callback, metadata


def make_llm_usage_record(
    *,
    prompt="",
    output=None,
    model_name,
    provider,
    api_type,
    image_count=0,
    schema=None,
    raw_usage=None,
    metadata=None,
    call_id=None,
    attempt_index=1,
    usage_snapshots=(),
    capability=None,
    pricing_snapshot=None,
):
    from uuid import uuid4
    from core.observability.llm_usage_normalization import (
        normalize_usage as canonical,
        safe_raw_usage,
    )
    from core.observability.llm_pricing import calculate_cost

    meta = persistent_metadata(metadata)
    errors = list(meta.get("accounting_errors") or [])
    raw = safe_raw_usage(raw_usage, errors=errors)
    snapshots = [safe_raw_usage(v, errors=errors) for v in usage_snapshots[:4096]]
    if len(usage_snapshots) > 4096:
        errors.append("usage_snapshot_limit")
    try:
        usage = canonical(
            raw,
            api_type=api_type,
            capability=capability,
            metadata=meta,
            snapshots=snapshots,
        )
    except Exception:
        from core.observability.llm_usage_normalization import FIELDS

        usage = {
            **dict.fromkeys(FIELDS),
            "field_sources": dict.fromkeys(FIELDS, "missing"),
            "raw_available": bool(raw),
            "tokens_complete": False,
            "errors": [],
        }
        errors.append("usage_normalization_failed")
    if errors:
        usage["errors"] = list(dict.fromkeys([*usage.get("errors", []), *errors]))
        usage["tokens_complete"] = False
    snapshot = pricing_snapshot
    try:
        cost = calculate_cost(
            usage,
            provider,
            api_type,
            model_name,
            snapshot=snapshot,
            metadata=meta,
            usage_final=meta.get("usage_final") is True and not errors,
        )
    except Exception:
        cost = unavailable_cost("cost_calculation_failed", snapshot)
    if snapshot is None and meta.get("pricing_error"):
        cost = unavailable_cost(meta["pricing_error"])
    call_id = call_id or uuid4().hex
    return {
        "schema_version": 2,
        "call_id": call_id,
        "attempt_index": attempt_index,
        "event_id": f"{call_id}:{attempt_index}",
        "model_name": model_name,
        "provider": provider,
        "api_type": api_type,
        "has_schema": schema is not None,
        "image_count": image_count,
        "usage": {**usage, "cost_usd": cost["amount_usd"]},
        "cost": cost,
        "raw_usage": raw,
        "usage_snapshots": snapshots,
        "pricing_snapshot": snapshot.export() if snapshot is not None else None,
        "metadata": meta,
        "api_reported_cost": _api_reported_cost(raw_usage),
    }


def minimal_usage_record(
    *, call_id, attempt_index, provider, api_type, model_name, outcome
):
    """Last-resort event identity when accounting construction itself fails."""
    from core.observability.llm_usage_normalization import FIELDS

    return {
        "schema_version": 2,
        "call_id": call_id,
        "attempt_index": attempt_index,
        "event_id": f"{call_id}:{attempt_index}",
        "provider": provider,
        "api_type": api_type,
        "model_name": model_name,
        "usage": {
            **dict.fromkeys(FIELDS),
            "cost_usd": None,
            "field_sources": dict.fromkeys(FIELDS, "missing"),
            "tokens_complete": False,
            "raw_available": False,
            "errors": ["accounting_record_failed"],
        },
        "cost": unavailable_cost("accounting_record_failed"),
        "raw_usage": {},
        "usage_snapshots": [],
        "pricing_snapshot": None,
        "metadata": {"request_outcome": outcome},
        "api_reported_cost": None,
    }


def unavailable_cost(reason, snapshot=None):
    return {
        "status": "unpriced",
        "amount_usd": None,
        "known_subtotal_usd": None,
        "estimated_subtotal_usd": None,
        "estimated_input_usd": None,
        "components": {},
        "estimated_components": {},
        "estimate_bases": [],
        "missing": [reason],
        "currency": "USD",
        "scope": "token_generation",
        "pricing_fingerprint": getattr(snapshot, "fingerprint", None),
    }


def safe_accounting_diagnostic(job_id, message):
    try:
        progress_tracker.add_llm_usage_export_error(job_id, message[:256])
    except Exception:
        pass


_METADATA_KEYS = frozenset(
    {
        "job_id",
        "node_id",
        "node_name",
        "document_id",
        "page_index",
        "page_no",
        "block_id",
        "block_kind",
        "prompt_version",
        "few_shot_examples",
        "processing_attempt",
        "restoration_model",
        "input_tokens_estimate",
        "token_count_method",
        "task_name",
        "task_version",
        "user_prompt_bytes",
        "reasoning",
        "response_complete",
        "usage_final",
        "finish_reason",
        "request_outcome",
        "request_error",
        "processing_outcome",
        "deployment",
        "region",
        "service_tier",
        "cache_ttl",
        "legacy",
        "accounting_errors",
        "pricing_error",
    }
)


def persistent_metadata(value):
    if not isinstance(value, Mapping):
        return {}
    clean = {}
    for key, item in value.items():
        if key not in _METADATA_KEYS or callable(item):
            continue
        if key == "few_shot_examples" and isinstance(item, list):
            clean[key] = [v for v in item[:2] if type(v) is int and 1 <= v <= 5]
        elif key == "accounting_errors" and isinstance(item, list):
            clean[key] = [
                v
                for v in item[:10]
                if isinstance(v, str) and re.fullmatch(r"[a-z_]{1,80}", v)
            ]
        elif key == "reasoning" and isinstance(item, dict):
            clean[key] = redact_telemetry_metadata(item)
        elif key == "request_error" and isinstance(item, dict):
            clean[key] = {
                name: value
                for name, value in item.items()
                if (name == "http_status" and type(value) is int)
                or (
                    name in {"exception_type", "code", "param", "type"}
                    and isinstance(value, str)
                    and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value)
                )
            }
        elif type(item) is float and not math.isfinite(item):
            continue
        elif item is None or type(item) in (str, int, float, bool):
            clean[key] = item if not isinstance(item, str) else item[:256]
    return clean


def redact_telemetry_metadata(value: object) -> object:
    """Drop credential values before records can reach logs or exporters."""
    if isinstance(value, Mapping):
        redacted: dict[object, object] = {}
        for key, item in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            if normalized_key in _SENSITIVE_METADATA_KEYS or normalized_key.endswith(
                ("_api_key", "_token", "_secret", "_password")
            ):
                continue
            redacted[key] = redact_telemetry_metadata(item)
        return redacted
    if isinstance(value, list):
        return [redact_telemetry_metadata(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_telemetry_metadata(item) for item in value)
    return value


def normalize_usage(raw_usage, *, api_type=None, capability=None, metadata=None):
    from core.observability.llm_usage_normalization import normalize_usage as canonical

    return canonical(
        raw_usage, api_type=api_type, capability=capability, metadata=metadata
    )


def estimate_usage(
    *, prompt: str, output: object, image_count: int = 0
) -> dict[str, object]:
    prompt_tokens = _estimate_text_tokens(prompt) + max(int(image_count), 0) * 1000
    completion_tokens = _estimate_text_tokens(_output_text(output))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cached_prompt_tokens": 0,
        "estimated": True,
    }


def _runtime_config(context: NodeContext) -> dict[str, object]:
    value = context.metadata.get("runtime_config", {})
    return value if isinstance(value, dict) else {}


def flush_langfuse_exporters() -> None:
    with _EXPORTERS_LOCK:
        exporters = list(_EXPORTERS.values())
    for exporter in exporters:
        try:
            exporter.flush()
        except Exception:
            pass


def _append_usage_line(record: dict[str, object], output_dir: str) -> None:
    file_path = str(Path(output_dir) / "_llm_usage.jsonl")
    with _file_lock(file_path):
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        with open(file_path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def _file_lock(path: str) -> RLock:
    with _FILE_LOCKS_LOCK:
        if path not in _FILE_LOCKS:
            _FILE_LOCKS[path] = RLock()
        return _FILE_LOCKS[path]


def _exporter_for(settings: LangfuseSettings) -> LangfuseSdkExporter:
    with _EXPORTERS_LOCK:
        if settings not in _EXPORTERS:
            _EXPORTERS[settings] = LangfuseSdkExporter(settings)
        return _EXPORTERS[settings]


def _estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _output_text(output: object) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    return str(output)


def _object_to_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    result: dict[str, object] = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "input_tokens",
        "output_tokens",
        "prompt_token_count",
        "candidates_token_count",
        "total_token_count",
        "cached_content_token_count",
        "promptTokenCount",
        "candidatesTokenCount",
        "totalTokenCount",
        "cachedContentTokenCount",
        "prompt_tokens_details",
        "usage_metadata",
        "cache_read_input_tokens",
        "cost",
        "cost_usd",
    ):
        if hasattr(value, key):
            result[key] = getattr(value, key)
    usage_metadata = result.get("usage_metadata")
    if usage_metadata is not None:
        result.update(_object_to_dict(usage_metadata))
    return result


def _extract_cost(raw_usage: object) -> float | None:
    usage = _object_to_dict(raw_usage)
    value = usage.get("cost_usd", usage.get("cost"))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _str_value(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _api_reported_cost(raw_usage):
    from decimal import Decimal, InvalidOperation
    from core.observability.llm_usage_normalization import safe_raw_usage

    raw = safe_raw_usage(raw_usage)
    value = raw.get("cost_usd")
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return {
        "amount": str(amount),
        "currency": "USD",
        "source": "reported_cost_usd",
        "scope": "provider_reported",
    }
