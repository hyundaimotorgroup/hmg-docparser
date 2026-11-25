"""Chat-model adapter entrypoints.

Use ``factory.py`` to select a provider. ``unified.py`` converts the common
request DTO. Azure, internal API, and OpenAI-compatible entrypoints are in
``azure_openai.py``, ``llm_internal_api.py``, and ``openai_compatible.py``. Anthropic,
Gemini, and shared transport are in ``unified_client.py``; Gemini option-name
conversion is in ``gemini_config.py``.
"""

from core.adapters.models.azure_openai import AzureOpenAIChatAdapter
from core.adapters.models.factory import build_chat_model_adapter
from core.adapters.models.llm_internal_api import LLMInternalAPIModelAdapter
from core.adapters.models.openai_compatible import OpenAICompatibleChatAdapter
from core.adapters.models.unified import ProviderChatAdapter

__all__ = [
    "AzureOpenAIChatAdapter",
    "LLMInternalAPIModelAdapter",
    "OpenAICompatibleChatAdapter",
    "ProviderChatAdapter",
    "build_chat_model_adapter",
]
