"""Immutable trusted price snapshot and exact Decimal component calculation."""

from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import yaml


class _PriceLoader(yaml.SafeLoader):
    """Reject duplicate keys and preserve YAML decimal spelling."""


def _price_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        try:
            if key in result:
                raise ValueError("duplicate pricing key")
            result[key] = loader.construct_object(value_node)
        except TypeError:
            raise ValueError("invalid pricing key") from None
    return result


_PriceLoader.add_constructor("tag:yaml.org,2002:map", _price_mapping)
_PriceLoader.add_constructor(
    "tag:yaml.org,2002:float", lambda loader, node: loader.construct_scalar(node)
)


def _canonical_prices(data):
    if not isinstance(data, dict) or not data:
        raise ValueError("pricing must be a nonempty mapping")
    if "entries" in data:
        return data  # Historic canonical evidence remains byte-for-byte stable.
    entries = []
    for provider, models in data.items():
        if (
            not isinstance(provider, str)
            or not provider.strip()
            or not isinstance(models, dict)
            or not models
        ):
            raise ValueError("invalid pricing provider")
        for model, options in models.items():
            if (
                not isinstance(model, str)
                or not model.strip()
                or not isinstance(options, dict)
            ):
                raise ValueError("invalid pricing model")
            if set(options) - {"input", "output", "cache_read", "bands"}:
                raise ValueError("unsupported pricing option")
            if "bands" in options:
                if set(options) & {"input", "output"}:
                    raise ValueError("bands cannot be combined with input/output")
                bands = options["bands"]
                if not isinstance(bands, list) or not bands:
                    raise ValueError("bands must be a nonempty list")
            else:
                bands = [options]
            lower = 0
            for index, band in enumerate(bands):
                if not isinstance(band, dict) or set(band) - {
                    "input",
                    "output",
                    "cache_read",
                    "up_to",
                }:
                    raise ValueError("invalid pricing band")
                rates = {}
                for key in ("input", "output", "cache_read"):
                    value = (
                        band.get(key, options.get(key))
                        if key == "cache_read"
                        else band.get(key)
                    )
                    if (
                        key == "cache_read"
                        and value is None
                        and key not in band
                        and key not in options
                    ):
                        continue
                    rate = _rate(value)
                    if rate is None:
                        raise ValueError("invalid pricing rate")
                    rates[key] = str(rate)
                entry = {
                    "id": f"operator:{provider}:{model}:{index}",
                    "provider": provider,
                    "model": model,
                    "rates": rates,
                    "source": "operator_supplied",
                }
                if "bands" in options:
                    upper = band.get("up_to")
                    if type(upper) is not int or not lower <= upper <= 2**63 - 1:
                        raise ValueError(
                            "pricing bands must have increasing integer bounds"
                        )
                    entry.update(context_min=lower, context_max=upper)
                    lower = upper + 1
                elif "up_to" in band:
                    raise ValueError("up_to requires bands")
                entries.append(entry)
    return {
        "version": 2,
        "pricing_format": "operator_v1",
        "currency": "USD",
        "unit": "per_million_tokens",
        "entries": entries,
    }


def _validate_file_entries(data):
    if data.get("currency") != "USD" or data.get("unit") != "per_million_tokens":
        raise ValueError("pricing currency/unit must be USD/per_million_tokens")
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("pricing entries must be a nonempty list")
    for entry in entries:
        if not isinstance(entry, dict) or any(
            not isinstance(entry.get(k), str) or not entry[k]
            for k in ("provider", "model")
        ):
            raise ValueError("invalid pricing entry identity")
        if not isinstance(entry.get("rates"), dict) or any(
            _rate(v) is None for v in entry["rates"].values()
        ):
            raise ValueError("invalid pricing entry rates")
        if data.get("pricing_format") != "operator_v1":
            if any(
                not isinstance(entry.get(key), str) or not entry[key]
                for key in (
                    "api_type",
                    "source",
                    "verified_on",
                    "effective_from",
                    "effective_until",
                )
            ):
                raise ValueError("invalid legacy pricing contract")
            for key in ("verified_on", "effective_from", "effective_until"):
                date.fromisoformat(entry[key])
            if entry["effective_from"] > entry["effective_until"]:
                raise ValueError("invalid pricing validity interval")
        for key in ("cache_write_supported",):
            if key in entry and type(entry[key]) is not bool:
                raise ValueError("invalid pricing cache contract")
        for key in (
            "deployment",
            "region",
            "service_tier",
            "cache_ttl",
            "cache_policy",
        ):
            if (
                key in entry
                and entry[key] is not None
                and not isinstance(entry[key], str)
            ):
                raise ValueError("invalid pricing selector")
        for key in ("context_min", "context_max"):
            if key in entry and (
                type(entry[key]) is not int or not 0 <= entry[key] <= 2**63 - 1
            ):
                raise ValueError("invalid pricing context bound")
        if entry.get("context_min", 0) > entry.get("context_max", 2**63 - 1):
            raise ValueError("invalid pricing context interval")
        for key in ("aliases", "unsupported_components", "component_calculators"):
            if key in entry and (
                not isinstance(entry[key], list)
                or any(not isinstance(v, str) for v in entry[key])
            ):
                raise ValueError("invalid pricing entry list")


@dataclass(frozen=True, slots=True)
class PricingSnapshot:
    content: str
    fingerprint: str
    as_of: str

    @classmethod
    def from_mapping(cls, data, *, as_of=None):
        data = _canonical_prices(data)
        if data.get("currency") != "USD" or data.get("unit") != "per_million_tokens":
            raise ValueError("pricing currency/unit must be USD/per_million_tokens")
        content = json.dumps(
            data,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return cls(
            content, sha256(content.encode()).hexdigest(), str(as_of or date.today())
        )

    @classmethod
    def from_path(cls, path=None, *, as_of=None):
        if path is None:
            raise ValueError("pricing path must be explicit")
        if as_of is not None:
            date.fromisoformat(str(as_of))
        data = _canonical_prices(
            yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_PriceLoader)
        )
        _validate_file_entries(data)
        return cls.from_mapping(data, as_of=as_of)

    def export(self):
        return {
            "content": self.content,
            "fingerprint": self.fingerprint,
            "as_of": self.as_of,
        }

    @classmethod
    def verified(cls, value):
        if not isinstance(value, dict) or not isinstance(value.get("content"), str):
            raise ValueError("invalid price snapshot")
        if sha256(value["content"].encode()).hexdigest() != value.get("fingerprint"):
            raise ValueError("price snapshot fingerprint mismatch")
        result = cls.from_mapping(json.loads(value["content"]), as_of=value["as_of"])
        if result.fingerprint != value["fingerprint"]:
            raise ValueError("noncanonical price snapshot")
        date.fromisoformat(result.as_of)
        return result

    def match(self, provider, api_type, model, metadata, usage):
        matches = []
        data = json.loads(self.content)
        operator = data.get("pricing_format") == "operator_v1"
        for entry in data.get("entries", []):
            if entry.get("provider") != provider or (
                not operator and entry.get("api_type") != api_type
            ):
                continue
            if model != entry.get("model") and model not in entry.get("aliases", []):
                continue
            if any(
                entry.get(k) is not None and entry.get(k) != metadata.get(k)
                for k in ("deployment", "region", "service_tier", "cache_ttl")
            ):
                continue
            try:
                if operator:
                    pass
                elif not entry.get("source") or not entry.get("verified_on"):
                    continue
                if not operator:
                    when = date.fromisoformat(self.as_of)
                    if date.fromisoformat(entry["verified_on"]) > when:
                        continue
                    if (
                        not date.fromisoformat(entry["effective_from"])
                        <= when
                        <= date.fromisoformat(entry["effective_until"])
                    ):
                        continue
            except (KeyError, TypeError, ValueError):
                continue
            tokens = usage.get("input_tokens")
            if (
                entry.get("context_min") is not None
                or entry.get("context_max") is not None
            ):
                if (
                    tokens is None
                    or tokens < entry.get("context_min", 0)
                    or tokens > entry.get("context_max", 2**63 - 1)
                ):
                    continue
            matches.append(entry)
        if len(matches) != 1:
            return None, "ambiguous_price" if matches else "unregistered_price"
        return matches[0], None


_COMPONENT_CALCULATORS = {}


def register_cost_component_calculator(name, calculator):
    """Trusted additional billing scope, never a user-selected Python import."""
    if name in _COMPONENT_CALCULATORS or not callable(calculator):
        raise ValueError("duplicate or invalid cost component calculator")
    _COMPONENT_CALCULATORS[name] = calculator


def _rate(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return rate if rate.is_finite() and rate >= 0 else None


def calculate_cost(
    usage, provider, api_type, model, *, snapshot=None, metadata=None, usage_final=False
):
    base = {
        "amount_usd": None,
        "known_subtotal_usd": None,
        "components": {},
        "estimated_components": {},
        "estimated_input_usd": None,
        "estimated_subtotal_usd": None,
        "estimate_basis": None,
        "estimate_bases": [],
        "missing": [],
        "currency": "USD",
        "pricing_fingerprint": snapshot.fingerprint if snapshot is not None else None,
        "scope": "token_generation",
    }
    if not usage.get("raw_available"):
        return {
            **base,
            "status": "missing_usage",
            "missing": [
                "provider_usage",
                *(["pricing_disabled"] if snapshot is None else []),
            ],
        }
    if snapshot is None:
        return {**base, "status": "unpriced", "missing": ["pricing_disabled"]}
    match_usage = usage
    context_assumed = False
    regular = usage.get("regular_input_tokens")
    if (
        json.loads(snapshot.content).get("pricing_format") != "operator_v1"
        and usage.get("input_tokens") is None
        and type(regular) is int
        and regular >= 0
    ):
        # Select a context band from collected input when total inclusive input is
        # unavailable; preserve this tariff assumption rather than omit costs.
        match_usage = deepcopy(usage)
        match_usage["input_tokens"] = regular + sum(
            v
            for key in ("cache_read_tokens", "cache_write_tokens")
            if type(v := usage.get(key)) is int and v >= 0
        )
        context_assumed = True
    entry, reason = snapshot.match(
        provider, api_type, model, metadata or {}, match_usage
    )
    if entry is None:
        return {**base, "status": "unpriced", "missing": [reason]}
    rates = {k: _rate(v) for k, v in entry.get("rates", {}).items()}
    components = {}
    estimated_components = {}
    missing = list(usage.get("errors") or [])
    bases = []
    meta = metadata or {}
    ttl = meta.get("cache_ttl")
    if ttl is not None and rates.get("cache_write_" + str(ttl)) is not None:
        rates["cache_write"] = rates["cache_write_" + str(ttl)]

    def count(name):
        value = usage.get(name)
        if (usage.get("field_sources") or {}).get(name) in {"invalid", "estimated"}:
            return None
        return value if type(value) is int and value >= 0 else None

    def add(name, tokens, *, rate=None, estimate=None):
        rate = rates.get(name) if rate is None else rate
        if type(tokens) is not int or tokens < 0 or rate is None:
            missing.append(name)
            return
        amount = str(Decimal(tokens) * rate / Decimal(1000000))
        if estimate:
            estimated_components[name] = amount
            bases.append(estimate)
        else:
            components[name] = amount

    input_count, regular, read, write = (
        count(k)
        for k in (
            "input_tokens",
            "regular_input_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
        )
    )
    inclusive_covered = False
    operator = json.loads(snapshot.content).get("pricing_format") == "operator_v1"
    no_cache = entry.get("cache_policy") == "none" or (
        operator and read == 0 and write == 0
    )
    no_write = entry.get("cache_write_supported") is False
    if (
        input_count is not None
        and regular is None
        and (
            (read is not None and read > input_count)
            or (write is not None and write > input_count)
            or (read is not None and write is not None and read + write > input_count)
        )
    ):
        missing.append("cache_exceeds_input")
        read = write = None  # Do not bill inconsistent overlapping counts twice.

    if no_write and write:
        missing.append("unexpected_cache_write_usage")
    if no_cache and not read and not write:
        add("input", input_count if input_count is not None else regular)
    else:
        if no_cache and (read or write):
            missing.append("unexpected_cache_usage")
        if regular is not None:
            # Anthropic reports noncached input independently of cache usage.
            add("input", regular)
        elif input_count is not None:
            remainder = input_count - (read or 0) - (write or 0)
            if read is not None and (write is not None or no_write):
                add("input", remainder)
            elif (
                rates.get("input") is not None
                and rates.get("input") == rates.get("cache_read")
                and (no_write or rates.get("input") == rates.get("cache_write"))
            ):
                add("input", input_count)
                read = write = (
                    None  # This equal-rate component already covers all input.
                )
                inclusive_covered = True
            else:
                # Price every reported input token, retaining unknown cache values.
                add(
                    "input",
                    remainder,
                    estimate="unreported_cache_at_regular_input_rate",
                )
                missing.append("input_cache_breakdown")
        else:
            missing.append("input")
        if read == 0 and operator and rates.get("cache_read") is None:
            pass
        elif read is not None:
            if rates.get("cache_read") is not None:
                add("cache_read", read)
            else:
                add(
                    "cache_read",
                    read,
                    rate=rates.get("input"),
                    estimate="cache_read_at_regular_input_rate",
                )
                missing.append("cache_read_rate")
        elif not no_cache and not inclusive_covered:
            missing.append("cache_read")
        if write == 0 and operator and rates.get("cache_write") is None:
            pass
        elif write is not None and (not no_write or write > 0):
            breakdown = usage.get("cache_write_breakdown") or {}
            known_ttl_tokens = 0
            for duration, tokens in breakdown.items():
                if type(tokens) is int and 0 <= tokens <= write - known_ttl_tokens:
                    rate = rates.get("cache_write_" + str(duration))
                    if rate is not None:
                        add("cache_write_" + str(duration), tokens, rate=rate)
                        known_ttl_tokens += tokens
            remaining = write - known_ttl_tokens
            if remaining or not breakdown:
                if rates.get("cache_write") is not None:
                    add("cache_write", remaining)
                else:
                    write_rates = [
                        v
                        for k, v in rates.items()
                        if k.startswith("cache_write_") and v is not None
                    ]
                    if remaining == 0 and write_rates:
                        add("cache_write", 0, rate=write_rates[0])
                    else:
                        # Explicit assumption, not an invented TTL or a zero-priced omission.
                        add(
                            "cache_write",
                            remaining,
                            rate=max(write_rates)
                            if write_rates
                            else rates.get("input"),
                            estimate="cache_write_at_max_registered_ttl_rate"
                            if write_rates
                            else "cache_write_at_regular_input_rate",
                        )
                        missing.append("cache_write_rate_or_ttl")
        elif write is None and not no_write and not no_cache and not inclusive_covered:
            missing.append("cache_write")

    if count("output_tokens") is not None:
        add("output", count("output_tokens"))
    else:
        body = count("response_output_tokens")
        thought = count("reasoning_tokens")
        body_rate = rates.get("response_output")
        if body_rate is None:
            body_rate = rates.get("output")
        add("response_output", body, rate=body_rate)
        if thought is not None and body is None:
            add("reasoning_output", thought, rate=rates.get("output"))
        missing.append("total_output")
    if count("unclassified_tokens"):
        generation_rates = [
            rates[k] for k in ("input", "output") if rates.get(k) is not None
        ]
        add(
            "unclassified",
            count("unclassified_tokens"),
            rate=max(generation_rates) if generation_rates else None,
            estimate="unclassified_tokens_at_max_input_output_rate",
        )
        missing.append("unclassified_tokens")
    if not usage_final:
        missing.append("final_usage")
    missing.extend(entry.get("unsupported_components", []))
    for name in entry.get("component_calculators", []):
        calculator = _COMPONENT_CALCULATORS.get(name)
        if calculator is None:
            missing.append("unsupported_calculator:" + name)
            continue
        extension = calculator(deepcopy(usage), deepcopy(entry), deepcopy(meta))
        extra = extension.get("components", {})
        if set(extra) & (set(components) | set(estimated_components)) or any(
            _rate(v) is None for v in extra.values()
        ):
            return {
                **base,
                "status": "invalid",
                "missing": ["invalid_extension_components"],
            }
        components.update({k: str(_rate(v)) for k, v in extra.items()})
        missing.extend(extension.get("missing", []))

    if context_assumed and any(
        entry.get(k) is not None for k in ("context_min", "context_max")
    ):
        estimated_components.update(components)
        components = {}
        bases.append("incomplete_input_at_collected_context_rate")
        missing.append("total_input_context")
    subtotal = (
        sum((Decimal(v) for v in components.values()), Decimal(0))
        if components
        else None
    )
    estimated_sum = (
        sum((Decimal(v) for v in estimated_components.values()), Decimal(0))
        if estimated_components
        else None
    )
    estimated_subtotal = (
        (subtotal or Decimal(0)) + estimated_sum if estimated_sum is not None else None
    )
    invalid = bool(usage.get("errors")) or "cache_exceeds_input" in missing
    return {
        **base,
        "status": "invalid" if invalid else "partial" if missing else "complete",
        "components": components,
        "estimated_components": estimated_components,
        "estimated_input_usd": estimated_components.get("input"),
        "estimated_subtotal_usd": str(estimated_subtotal)
        if estimated_subtotal is not None
        else None,
        "estimate_basis": bases[0]
        if len(set(bases)) == 1
        else "multiple_assumptions"
        if bases
        else None,
        "estimate_bases": sorted(set(bases)),
        "known_subtotal_usd": str(subtotal) if subtotal is not None else None,
        "amount_usd": str(subtotal)
        if not missing and not invalid and subtotal is not None
        else None,
        "missing": missing,
        "price_entry": entry.get("id"),
        "price_source": entry["source"],
    }
