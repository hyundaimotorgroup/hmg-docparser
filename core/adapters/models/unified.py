from __future__ import annotations

from core.adapters.models.unified_client import UnifiedLLMClient
from core.interfaces.adapters import ChatModelAdapter, ChatModelRequest


class UnifiedClientChatAdapter(ChatModelAdapter):
    provider: str | None = None

    def invoke(self, payload: object) -> dict[str, object] | str:
        if not isinstance(payload, ChatModelRequest):
            raise TypeError(f"{self.__class__.__name__} expects ChatModelRequest")

        if len(payload.images) > 1:
            raise ValueError("chat model adapters currently accept exactly one image")

        client = UnifiedLLMClient(
            model_name=payload.model_name,
            provider=self.provider,
            base_url=payload.base_url,
            api_key=payload.api_key,
            api_version=payload.api_version,
            project_id=payload.project_id,
            extra_body=payload.extra_body or None,
            usage_callback=payload.usage_callback,
            trace_metadata=payload.trace_metadata,
            timeout_seconds=payload.timeout_seconds,
            api_type=payload.api_type,
            retry_max_attempts=payload.retry_max_attempts,
            strict_response=payload.strict_response,
            deadline_monotonic=payload.deadline_monotonic,
            cancellation_check=payload.cancellation_check,
            reasoning=payload.reasoning,
            deployment=payload.deployment,
            prompt_policy=payload.prompt_policy,
            pricing_snapshot=payload.pricing_snapshot,
            capability_registry=payload.capability_registry,
        )
        image = payload.images[0] if payload.images else None
        return client(
            payload.prompt,
            image,
            schema=payload.schema,
            task_prompt=payload.task_prompt,
            user_prompt=payload.user_prompt,
        )


class ProviderChatAdapter(UnifiedClientChatAdapter):
    """Adapter for providers that share the unified client transport."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
