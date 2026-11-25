"""Per-attempt collector and bounded incremental JSON/SSE/NDJSON decoder."""

from __future__ import annotations
import codecs
import json
from copy import deepcopy
from core.observability.llm_usage_normalization import safe_raw_usage


class UsageCollector:
    def __init__(self, api_type):
        self.api_type = api_type
        self.raw = {}
        self.snapshots = []
        self.response_complete = False
        self.usage_final = False
        self.finish_reason = None
        self.request_started = False
        self.response_metadata = {}
        self.accounting_errors = []
        self.collection_stopped = False

    def observe(self, usage):
        if usage is None or self.collection_stopped:
            return
        if len(self.snapshots) >= 4096:
            self.accounting_errors.append("usage_snapshot_limit")
            self.collection_stopped = True
            self.usage_final = False
            return
        raw = safe_raw_usage(usage, errors=self.accounting_errors)
        self.snapshots.append(deepcopy(raw))
        if self.api_type == "anthropic":
            self.raw.update(raw)
        else:
            self.raw = raw
        if self.response_complete:
            self.usage_final = bool(self.snapshots) and not self.accounting_errors

    def finish(self, reason, *, terminal=True):
        self.finish_reason = (
            str(getattr(reason, "value", reason)) if reason is not None else None
        )
        normal = {
            "openai": {"stop", "tool_calls"},
            "anthropic": {"end_turn", "tool_use", "stop_sequence"},
            "gemini": {"STOP"},
        }
        self.response_complete = terminal and self.finish_reason in normal.get(
            self.api_type, set()
        )
        self.usage_final = (
            self.response_complete
            and bool(self.snapshots)
            and not self.accounting_errors
        )

    def metadata(self, outcome):
        return {
            "response_complete": self.response_complete,
            "usage_final": self.usage_final,
            "finish_reason": self.finish_reason,
            "request_outcome": outcome,
            "accounting_errors": list(self.accounting_errors),
        }


def json_stream(chunks, *, max_buffer_bytes=4 * 1024 * 1024):
    decoder = codecs.getincrementaldecoder("utf-8")()
    parser = json.JSONDecoder()
    buffer = ""
    array_open = False
    array_expect_value = False
    array_empty = True

    def parse_available(final=False):
        nonlocal buffer, array_open, array_expect_value, array_empty
        while buffer:
            buffer = buffer.lstrip()
            if buffer.startswith(("event:", "id:", "retry:", ":")):
                end = buffer.find("\n")
                if end < 0:
                    return
                buffer = buffer[end + 1 :]
                continue
            if buffer.startswith("data:"):
                buffer = buffer[5:].lstrip()

            if buffer.startswith("[DONE]"):
                buffer = buffer[6:]

                continue
            # Prefixes may be split between packets, including the SSE terminal marker.
            if any(
                p.startswith(buffer)
                for p in ("data:", "event:", "id:", "retry:", "[DONE]")
            ):
                if final and buffer.strip():
                    raise ValueError("incomplete provider stream prefix")
                return
            if buffer.startswith("[") and not array_open:
                array_open = True
                array_expect_value = True
                array_empty = True
                buffer = buffer[1:]
                continue
            if buffer.startswith("]"):
                if not array_open or (array_expect_value and not array_empty):
                    raise ValueError("invalid provider stream array")
                array_open = False
                buffer = buffer[1:]
                continue
            if buffer.startswith(","):
                if not array_open or array_expect_value:
                    raise ValueError("invalid provider stream array")
                array_expect_value = True
                buffer = buffer[1:]
                continue
            if array_open and not array_expect_value:
                raise ValueError("missing provider stream array separator")
            try:
                value, end = parser.raw_decode(buffer)
            except json.JSONDecodeError:
                if final and buffer.strip():
                    raise ValueError(
                        "incomplete or invalid provider JSON stream"
                    ) from None
                return
            buffer = buffer[end:]
            if array_open:
                array_expect_value = False
                array_empty = False
            if isinstance(value, dict):
                yield value
            elif isinstance(value, list):
                yield from (v for v in value if isinstance(v, dict))

    for chunk in chunks:
        buffer += decoder.decode(chunk) if isinstance(chunk, bytes) else chunk
        if len(buffer.encode("utf-8")) > max_buffer_bytes:
            raise ValueError("provider stream exceeds buffer budget")
        yield from parse_available()
    buffer += decoder.decode(b"", final=True)
    yield from parse_available(final=True)
    if array_open:
        raise ValueError("incomplete provider stream array")
