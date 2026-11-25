from __future__ import annotations

from core.adapters.models.unified import UnifiedClientChatAdapter


class AzureOpenAIChatAdapter(UnifiedClientChatAdapter):
    provider = "azure"
