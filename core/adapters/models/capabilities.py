"""Trusted exact-identity capability registry, independent of pricing."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from importlib import resources
import logging
from pathlib import Path
import re
from threading import RLock
import yaml

logger = logging.getLogger(__name__)


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(
            f"{field} must be a nonempty string without surrounding whitespace"
        )


@dataclass(frozen=True, slots=True)
class ModelCapability:
    provider: str
    api_type: str
    model: str
    deployment: str | None = None
    version: str = "1"
    efforts: tuple[str, ...] = ()
    modes: tuple[str, ...] = ()
    default_low: bool = False
    sampling: bool = True
    output_token_parameter: str | None = None
    max_output_tokens: int | None = None
    schema: bool = True
    forced_tool_with_thinking: bool = False
    budget_min: int = 1
    budget_max: int | None = None
    serializer: str | None = None
    omitted_thinking_is_zero: bool = False
    usage_semantics: str | None = None
    source: str | None = None
    verified_on: str | None = None

    def __post_init__(self):
        for field in ("provider", "api_type", "model", "version"):
            _text(getattr(self, field), field)
        for field in (
            "deployment",
            "output_token_parameter",
            "serializer",
            "usage_semantics",
            "source",
            "verified_on",
        ):
            value = getattr(self, field)
            if value is not None:
                _text(value, field)
        for field in (
            "default_low",
            "sampling",
            "schema",
            "forced_tool_with_thinking",
            "omitted_thinking_is_zero",
        ):
            if type(getattr(self, field)) is not bool:
                raise ValueError(f"{field} must be a boolean")
        for field in ("efforts", "modes"):
            value = getattr(self, field)
            if not isinstance(value, (list, tuple)) or any(
                not isinstance(item, str) for item in value
            ):
                raise ValueError(f"{field} must be a list of strings")
            if len(value) != len(set(value)):
                raise ValueError(f"{field} contains duplicates")
            object.__setattr__(self, field, tuple(value))
        if any(
            not re.fullmatch(r"[a-z][a-z0-9_\-]{0,31}", effort)
            for effort in self.efforts
        ):
            raise ValueError("invalid effort identifier")
        if set(self.modes) - {
            "effort",
            "budget",
            "disabled",
            "adaptive",
            "provider_default",
        }:
            raise ValueError("unsupported reasoning mode")
        if "effort" in self.modes and not self.efforts:
            raise ValueError("effort mode requires supported efforts")
        if self.efforts and not set(self.modes) & {"effort", "adaptive"}:
            raise ValueError("efforts require effort or adaptive mode")
        if set(self.modes) - {"provider_default"} and self.serializer is None:
            raise ValueError("reasoning modes require a serializer")
        for field in ("budget_min", "budget_max", "max_output_tokens"):
            value = getattr(self, field)
            if value is None and field != "budget_min":
                continue
            if type(value) is not int or not 1 <= value <= 2**63 - 1:
                raise ValueError(f"{field} must be a positive integer")
        if self.budget_max is not None and self.budget_max < self.budget_min:
            raise ValueError("invalid reasoning budget interval")
        if self.default_low and (
            "low" not in self.efforts or "effort" not in self.modes
        ):
            raise ValueError("default_low requires confirmed low effort support")
        if self.verified_on is not None:
            date.fromisoformat(self.verified_on)
        if self.omitted_thinking_is_zero and (not self.source or not self.verified_on):
            raise ValueError("omission policy requires documented verification")


class _CapabilityLoader(yaml.SafeLoader):
    """Never overwrite duplicate YAML keys or identities silently."""


def _unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError("duplicate or invalid capability key")
        result[key] = loader.construct_object(value_node)
    return result


_CapabilityLoader.add_constructor("tag:yaml.org,2002:map", _unique_mapping)


class CapabilityRegistry:
    def __init__(self, *, _default_path=None, _default_resource=False, fallback=None):
        self._entries = {}
        self._lock = RLock()
        self._default_path = _default_path
        self._default_resource = _default_resource
        self._initialized = _default_path is None and not _default_resource
        self._load_error = None
        self._fallback = fallback

    def _ensure_loaded(self):
        with self._lock:
            if self._initialized:
                return
            try:
                loaded = (self.from_text(_read_default_resource())
                          if self._default_resource else self.from_path(self._default_path))
                self._entries = loaded._entries
                self._initialized = True
            except Exception:
                self._initialized = True
                # Reject the entire table; never apply partially validated rules.
                self._load_error = "default_capabilities_unavailable"
                try:
                    logger.warning(
                        "default_capabilities_unavailable; unverified optional model rules will be omitted"
                    )
                except Exception:
                    pass

    @property
    def load_error(self):
        self._ensure_loaded()
        return self._load_error or (
            self._fallback.load_error if self._fallback else None
        )

    def register(self, entry):
        if not isinstance(entry, ModelCapability):
            raise ValueError("capability entry must be a ModelCapability")
        self._ensure_loaded()
        key = (entry.provider, entry.api_type, entry.model, entry.deployment)
        with self._lock:
            if key in self._entries:
                raise ValueError("duplicate capability identity")
            self._entries[key] = entry
        return entry

    def get(self, provider, api_type, model, deployment=None):
        self._ensure_loaded()
        with self._lock:
            entry = self._entries.get((provider, api_type, model, deployment))
        if entry is None and self._fallback is not None:
            return self._fallback.get(provider, api_type, model, deployment)
        return entry

    @classmethod
    def from_path(cls, path, *, include_defaults=False):
        """Explicit operator files fail strictly; optionally retain built-in rules."""
        if type(include_defaults) is not bool:
            raise ValueError("include_defaults must be a boolean")
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError:
            raise ValueError("model capability file could not be loaded or validated") from None
        return cls.from_text(content, include_defaults=include_defaults)

    @classmethod
    def from_text(cls, content, *, include_defaults=False):
        if type(include_defaults) is not bool:
            raise ValueError("include_defaults must be a boolean")
        registry = cls(fallback=DEFAULT_CAPABILITIES if include_defaults else None)
        try:
            data = yaml.load(content, Loader=_CapabilityLoader)
            if not isinstance(data, dict) or set(data) - {"version", "models"}:
                raise ValueError("invalid capability document")
            if type(data.get("version", 1)) is not int or data.get("version", 1) != 1:
                raise ValueError("unsupported capability version")
            models = data.get("models")
            if not isinstance(models, list) or not models:
                raise ValueError("models must be a nonempty list")
            for item in models:
                if not isinstance(item, dict):
                    raise ValueError("invalid capability entry")
                registry.register(ModelCapability(**item))
        except (OSError, ValueError, TypeError, yaml.YAMLError, RecursionError):
            raise ValueError(
                "model capability file could not be loaded or validated"
            ) from None
        return registry


def _read_default_resource():
    return resources.files("core.adapters.models.resources").joinpath(
        "model_capabilities.yaml"
    ).read_text(encoding="utf-8")


# Import is independent of resource availability; first lookup loads once.
DEFAULT_CAPABILITIES = CapabilityRegistry(_default_resource=True)
