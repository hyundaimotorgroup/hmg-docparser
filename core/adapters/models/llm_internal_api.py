from __future__ import annotations

from core.adapters.models.unified import UnifiedClientChatAdapter


class LLMInternalAPIModelAdapter(UnifiedClientChatAdapter):
    provider = "llm_internal_api"
