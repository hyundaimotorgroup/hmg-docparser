"""One reducer for live observations, persisted JSONL and offline replay."""

from __future__ import annotations
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
import os
import tempfile

from core.observability.llm_usage_normalization import FIELDS
from core.observability.llm_pricing import PricingSnapshot, calculate_cost


class UsageReducer:
    def __init__(self):
        self._events = {}
        self._lock = RLock()

    def add(self, record):
        record = deepcopy(record)
        event_id = record.get("event_id")
        if not event_id:
            raise ValueError("accounting event requires event_id")
        with self._lock:
            if event_id in self._events:
                if self._events[event_id] != record:
                    raise ValueError("conflicting accounting event_id")
                return False
            self._events[event_id] = record
        return True

    def summary(self, *, page_count=None):
        with self._lock:
            events = deepcopy(list(self._events.values()))
        result = _bucket(events, page_count)
        for group, get_key in [
            ("by_model", lambda r: r.get("model_name") or "unknown"),
            (
                "by_node",
                lambda r: (r.get("metadata") or {}).get("node_id") or "unknown",
            ),
            (
                "by_page",
                lambda r: str((r.get("metadata") or {}).get("page_index", "unknown")),
            ),
        ]:
            keys = {get_key(r) for r in events}
            result[group] = {
                k: _bucket([r for r in events if get_key(r) == k]) for k in sorted(keys)
            }
        return result

    def records(self):
        with self._lock:
            return deepcopy(list(self._events.values()))


def _bucket(events, page_count=None):
    totals = dict.fromkeys(FIELDS, 0)
    coverage = {f: {"known": 0, "missing": 0, "invalid": 0} for f in FIELDS}
    sources = {f: {} for f in FIELDS}
    subtotal = Decimal(0)
    has_cost = False
    estimated_input = Decimal(0)
    estimated_total = Decimal(0)
    has_estimate = False
    estimated_calls = 0
    estimate_bases = set()
    complete = bool(events)
    reasons = {}
    for event in events:
        usage = event.get("usage") or {}
        for field in FIELDS:
            value = usage.get(field)
            source = (usage.get("field_sources") or {}).get(field, "missing")
            sources[field][source] = sources[field].get(source, 0) + 1
            state = (
                "known"
                if type(value) is int and value >= 0
                else "invalid"
                if source == "invalid"
                else "missing"
            )
            coverage[field][state] += 1
            if state == "known":
                totals[field] += value
        cost = event.get("cost") or {}
        reason = cost.get("status", "missing_usage")
        reasons[reason] = reasons.get(reason, 0) + 1
        complete &= reason == "complete" and cost.get("amount_usd") is not None
        known = cost.get("known_subtotal_usd")
        if known is not None:
            subtotal += Decimal(str(known))
            has_cost = True
        estimate = cost.get("estimated_subtotal_usd")
        if estimate is not None:
            # Estimated subtotal already contains the event's known components.
            estimated_total += Decimal(str(estimate))
            estimated_input += Decimal(str(cost.get("estimated_input_usd") or 0))
            has_estimate = True
            estimated_calls += 1
            estimate_bases.update(cost.get("estimate_bases") or [])
        elif known is not None:
            estimated_total += Decimal(str(known))
    tokens_complete = (
        bool(events)
        and all(
            coverage[f]["known"] == len(events)
            for f in ("input_tokens", "output_tokens", "total_tokens")
        )
        and all(not (e.get("usage") or {}).get("errors") for e in events)
    )
    status = (
        "not_applicable"
        if not events
        else "complete"
        if complete
        else "partial"
        if has_cost or has_estimate
        else "unknown"
    )
    result = {
        "calls": len({e["call_id"] for e in events}),
        "attempts": len(events),
        "tokens_complete": tokens_complete,
        "cost_status": status,
        "amount_usd": str(subtotal) if complete else None,
        "known_subtotal_usd": str(subtotal) if has_cost else None,
        "estimated_input_usd": str(estimated_input) if has_estimate else None,
        "estimated_subtotal_usd": str(estimated_total) if has_estimate else None,
        "estimate_bases": sorted(estimate_bases),
        "coverage": coverage,
        "field_sources": sources,
        "cost_coverage": reasons,
        "pricing_disabled_attempts": sum(
            "pricing_disabled" in (e.get("cost") or {}).get("missing", [])
            for e in events
        ),
        **{f + "_known_sum": v for f, v in totals.items()},
        "prompt_tokens": totals["input_tokens"],
        "completion_tokens": totals["output_tokens"],
        "total_tokens": totals["total_tokens"],
        "cached_prompt_tokens": totals["cache_read_tokens"],
        "cost_usd": str(subtotal) if complete else None,
        "cost_available": has_cost or has_estimate,
        "estimated_calls": estimated_calls,
        "export_errors": [],
    }
    if page_count is not None:
        result["page_count"] = page_count
        result["average_page_cost_usd"] = (
            str(subtotal / page_count) if complete and page_count else None
        )
        result["estimated_subtotal_average_page_usd"] = (
            str(estimated_total / page_count) if has_estimate and page_count else None
        )
        result["known_subtotal_average_page_usd"] = (
            str(subtotal / page_count) if has_cost and page_count else None
        )
    return result


def display_output_tokens(summary):
    for field in ("response_output_tokens", "output_tokens"):
        if summary.get("coverage", {}).get(field, {}).get("known", 0):
            return summary.get(field + "_known_sum"), field
    return None, None


def format_usage_summary(summary):
    output, _ = display_output_tokens(summary)
    badge = (
        "tokens complete"
        if summary.get("tokens_complete")
        else "tokens partially reported"
        if summary.get("attempts")
        else "no calls"
    )
    amount = summary.get("amount_usd")
    known = summary.get("known_subtotal_usd")
    estimated = summary.get("estimated_subtotal_usd")
    cost = (
        "$" + amount
        if amount is not None
        else "$"
        + estimated
        + " estimated subtotal (partial; includes input/cache assumptions)"
        if estimated is not None
        else "$" + known + " known components (partial)"
        if known is not None
        else "—"
    )
    disabled = (
        bool(summary.get("attempts"))
        and summary.get("pricing_disabled_attempts") == summary["attempts"]
    )
    incomplete = sum(
        v for k, v in summary.get("cost_coverage", {}).items() if k != "complete"
    )
    if disabled:
        cost = "disabled (usage recorded)"
    return f"[accounting] {badge}; output={output if output is not None else '—'}; cost={cost}; status={summary.get('cost_status')}; incomplete_cost_attempts={incomplete}; currency=USD"


def write_atomic_summary(path, summary):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(
                summary, stream, ensure_ascii=False, sort_keys=True, allow_nan=False
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_summary(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def replay_jsonl(path, *, snapshot=None, repair=False):
    data = Path(path).read_bytes()
    source_hash = sha256(data).hexdigest()
    reducer = UsageReducer()
    for index, line in enumerate(data.splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("schema_version") != 2:
            # Occurrence identity preserves identical legacy calls on separate lines.
            from core.observability.llm_usage import make_llm_usage_record

            raw = {
                k: record[k]
                for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                if k in record and not record.get("estimated")
            }
            record = make_llm_usage_record(
                prompt="",
                output=None,
                model_name=record.get("model_name", "unknown"),
                provider=record.get("provider"),
                api_type=record.get("api_type") or "unknown",
                raw_usage=raw,
                metadata={
                    "node_id": record.get("node_id"),
                    "page_index": record.get("page_index"),
                    "legacy": True,
                },
                call_id=f"legacy:{source_hash}:{index}",
                pricing_snapshot=snapshot,
            )
        elif repair:
            record = repair_record(record)
        if snapshot is not None:
            record = deepcopy(record)
            from core.observability.llm_usage_normalization import normalize_usage

            normalized = normalize_usage(
                record.get("raw_usage"), api_type=record.get("api_type")
            )
            for f in ("regular_input_tokens", "cache_write_breakdown"):
                if f not in record["usage"]:
                    record["usage"][f] = deepcopy(normalized.get(f))
                    if f in FIELDS:
                        record["usage"].setdefault("field_sources", {})[f] = normalized[
                            "field_sources"
                        ][f]
            record["cost"] = calculate_cost(
                record["usage"],
                record.get("provider"),
                record.get("api_type"),
                record.get("model_name"),
                snapshot=snapshot,
                metadata=record.get("metadata"),
                usage_final=(record.get("metadata") or {}).get("usage_final") is True,
            )
            record["usage"]["cost_usd"] = record["cost"]["amount_usd"]
            record["pricing_snapshot"] = snapshot.export()
        reducer.add(record)
    return reducer


def repair_record(record):
    """Verified historic v2 enrichment on a memory copy; stored prices and raw stay intact."""
    from core.adapters.models.capabilities import DEFAULT_CAPABILITIES
    from core.observability.llm_usage_normalization import normalize_usage

    result = deepcopy(record)
    try:
        snapshot = PricingSnapshot.verified(record["pricing_snapshot"])
    except (KeyError, TypeError, ValueError):
        return result
    metadata = result.get("metadata") or {}
    cap = DEFAULT_CAPABILITIES.get(
        result.get("provider"),
        result.get("api_type"),
        result.get("model_name"),
        metadata.get("deployment"),
    )
    normalized = normalize_usage(
        result.get("raw_usage"),
        api_type=result.get("api_type"),
        capability=cap,
        metadata=metadata,
        snapshots=result.get("usage_snapshots", []),
    )
    old = result.get("usage") or {}
    # Refuse enrichment when independently reported input/body/total disagrees.
    if any(
        old.get(f) is not None and old.get(f) != normalized.get(f)
        for f in ("input_tokens", "response_output_tokens", "total_tokens")
    ):
        return result
    for f in FIELDS:
        if old.get(f) is not None:
            normalized[f] = old[f]
            normalized["field_sources"][f] = old.get("field_sources", {}).get(
                f, "reported"
            )
    cost = calculate_cost(
        normalized,
        result.get("provider"),
        result.get("api_type"),
        result.get("model_name"),
        snapshot=snapshot,
        metadata=metadata,
        usage_final=metadata.get("usage_final") is True,
    )
    previous_cost = result.get("cost") or {}
    if previous_cost.get(
        "pricing_fingerprint"
    ) != snapshot.fingerprint or previous_cost.get("price_entry") != cost.get(
        "price_entry"
    ):
        return result
    old_components = previous_cost.get("components") or {}
    if any(
        cost.get("components", {}).get(k) != v
        for k, v in old_components.items()
        if k != "response_output"
    ):
        return result
    if (
        old.get("reasoning_tokens") is None
        and normalized["field_sources"]["reasoning_tokens"] == "derived"
    ):
        for f in (
            "reasoning_tokens",
            "output_tokens",
            "total_tokens",
            "unclassified_tokens",
        ):
            result["usage"][f] = normalized[f]
            result["usage"].setdefault("field_sources", {})[f] = normalized[
                "field_sources"
            ][f]
        result["usage"]["tokens_complete"] = normalized["tokens_complete"]
    for f in ("regular_input_tokens", "cache_write_breakdown"):
        if f not in old:
            result["usage"][f] = deepcopy(normalized.get(f))
            if f in FIELDS:
                result["usage"].setdefault("field_sources", {})[f] = normalized[
                    "field_sources"
                ][f]
    if previous_cost.get("amount_usd") is None and (
        cost.get("components") or cost.get("estimated_components")
    ):
        result["cost"] = cost
        result["usage"]["cost_usd"] = cost["amount_usd"]
    return result
