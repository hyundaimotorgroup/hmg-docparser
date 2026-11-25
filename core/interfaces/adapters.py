from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import TYPE_CHECKING

from core.domain.artifacts import ArtifactRef

if TYPE_CHECKING:
    from PIL import Image


class ModelAdapter(ABC):
    @abstractmethod
    def invoke(self, payload: object) -> object:
        raise NotImplementedError


@dataclass(slots=True)
class ChatModelRequest:
    prompt: str
    model_name: str
    images: list["Image.Image"] = field(default_factory=list)
    schema: dict[str, object] | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_version: str | None = None
    project_id: str | None = None
    extra_body: dict[str, object] = field(default_factory=dict)
    usage_callback: Callable[[dict[str, object]], None] | None = None
    trace_metadata: dict[str, object] = field(default_factory=dict)
    timeout_seconds: float | None = None
    # Explicit transport selection prevents model-name based SDK routing.
    # Existing callers may omit this during the compatibility period.
    api_type: str | None = None
    retry_max_attempts: int = 3
    strict_response: bool = False
    deadline_monotonic: float | None = None
    cancellation_check: Callable[[], bool] | None = None
    task_prompt: object | None = None
    user_prompt: str | None = None
    reasoning: object | None = None
    deployment: str | None = None
    prompt_policy: object | None = None
    pricing_snapshot: object | None = None
    capability_registry: object | None = None

    def __post_init__(self):
        from core.services.prompt_policy import (
            validate_user_prompt,
            validate_extra_body,
            DEFAULT_PROMPT_POLICY,
        )

        if type(self.strict_response) is not bool:
            raise ValueError("strict_response must be a boolean")
        validate_user_prompt(
            self.user_prompt, self.prompt_policy or DEFAULT_PROMPT_POLICY
        )
        validate_extra_body(self.extra_body)


class ChatModelAdapter(ModelAdapter):
    @abstractmethod
    def invoke(self, payload: object) -> dict[str, object] | str:
        raise NotImplementedError


class ArtifactStore(ABC):
    @abstractmethod
    def save(self, artifact: object, *, name: str | None = None) -> ArtifactRef:
        raise NotImplementedError
