from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PIL import Image

from core.interfaces.adapters import ModelAdapter
from core.adapters.triton.dolphin_client import run_batch_inference


@dataclass(slots=True)
class DolphinLayoutRequest:
    images: Sequence[Image.Image]
    server_url: str
    model_name: str
    prompt: str
    max_batch_size: int = 8
    ssl: bool = False
    token: str | None = None
    timeout_seconds: float | None = None
    cancellation_check: Callable[[], bool] | None = None


class DolphinTritonLayoutAdapter(ModelAdapter):
    def invoke(self, payload: object) -> list[str]:
        if not isinstance(payload, DolphinLayoutRequest):
            raise TypeError("DolphinTritonLayoutAdapter expects DolphinLayoutRequest")

        results = run_batch_inference(
            server_url=payload.server_url,
            model_name=payload.model_name,
            images=list(payload.images),
            prompt=payload.prompt,
            max_batch_size=payload.max_batch_size,
            ssl=payload.ssl,
            token=payload.token,
            timeout_seconds=payload.timeout_seconds,
            cancellation_check=payload.cancellation_check,
        )
        if results is None:
            raise RuntimeError("Dolphin Triton layout inference returned None")
        return results
