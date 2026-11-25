from __future__ import annotations
from threading import RLock

from core.adapters.models.azure_openai import AzureOpenAIChatAdapter
from core.adapters.models.llm_internal_api import LLMInternalAPIModelAdapter
from core.adapters.models.unified import ProviderChatAdapter
from core.adapters.models.unified_client import normalize_provider
from core.interfaces.adapters import ChatModelAdapter


SUPPORTED_CHAT_PROVIDERS = frozenset(
    {
        "llm_internal_api",
        "internal-api",
        "azure",
        "openai-compatible",
        "vllm",
        "openai",
        "anthropic",
        "gemini",
    }
)


_CUSTOM_PROVIDERS = {}
_PROVIDER_LOCK = RLock()


def register_chat_provider(name, factory):
    if not isinstance(name, str) or not name.strip() or not callable(factory):
        raise ValueError("provider registration requires a name and trusted factory")
    name = name.strip().lower()
    with _PROVIDER_LOCK:
        if name in SUPPORTED_CHAT_PROVIDERS or name in _CUSTOM_PROVIDERS:
            raise ValueError("duplicate chat provider registration")
        _CUSTOM_PROVIDERS[name] = factory


def build_chat_model_adapter(provider: str | None) -> ChatModelAdapter:
    configured_provider = (provider or "openai-compatible").strip().lower()
    if not configured_provider:
        raise ValueError(
            f"unsupported chat model provider: {provider}; supported providers: "
            f"{', '.join(sorted(SUPPORTED_CHAT_PROVIDERS))}"
        )
    with _PROVIDER_LOCK:
        factory = _CUSTOM_PROVIDERS.get(configured_provider)
    if factory:
        return factory()
    normalized = normalize_provider(configured_provider)
    if normalized == "llm_internal_api":
        return LLMInternalAPIModelAdapter()
    if normalized == "azure":
        return AzureOpenAIChatAdapter()
    if normalized in {"vllm", "openai-compatible"}:
        return ProviderChatAdapter(normalized)
    if normalized == "openai":
        return ProviderChatAdapter("openai")
    if normalized in {"anthropic", "gemini"}:
        return ProviderChatAdapter(normalized)
    raise ValueError(
        f"unsupported chat model provider: {provider}; supported providers: "
        f"{', '.join(sorted(SUPPORTED_CHAT_PROVIDERS))}"
    )
