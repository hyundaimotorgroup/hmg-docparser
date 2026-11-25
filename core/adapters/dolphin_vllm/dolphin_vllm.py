from __future__ import annotations

import base64
import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PIL import Image
from openai import OpenAI

from core.engine.runtime.cancellation import PipelineCancelled


@dataclass
class DolphinVLLMLayoutRequest:
    images: Sequence[Image.Image]
    server_url: str
    model_name: str
    prompt: str = "Parse the reading order of this document."
    ssl: bool = False
    token: str | None = None
    timeout_seconds: float | None = None
    cancellation_check: Callable[[], bool] | None = None


class DolphinVLLMLayoutAdapter:
    def invoke(self, request: DolphinVLLMLayoutRequest) -> list[str]:
        _raise_if_cancelled(request.cancellation_check)
        base_url = _normalize_base_url(request.server_url, request.ssl)
        client = OpenAI(
            base_url=base_url,
            api_key=request.token or "EMPTY",
            timeout=request.timeout_seconds or 600.0,
            max_retries=0,
        )
        return [
            _infer_one(client, image, request.model_name, request.prompt, request.cancellation_check)
            for image in request.images
        ]


def _infer_one(
    client: OpenAI,
    image: Image.Image,
    model_name: str,
    prompt: str,
    cancellation_check: Callable[[], bool] | None,
) -> str:
    _raise_if_cancelled(cancellation_check)
    b64 = _pil_to_base64(image)
    stream = client.chat.completions.create(
        model=model_name,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
        temperature=0.0,
        max_tokens=4096,
        stream=True,
    )
    text = ""
    for chunk in stream:
        _raise_if_cancelled(cancellation_check)
        if chunk.choices and chunk.choices[0].delta.content:
            text += chunk.choices[0].delta.content
    return text


def _raise_if_cancelled(cancellation_check: Callable[[], bool] | None) -> None:
    if cancellation_check is not None and cancellation_check():
        raise PipelineCancelled("Dolphin vLLM request cancelled")


def _pil_to_base64(image: Image.Image) -> str:
    image = _resize_for_model(image)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _resize_for_model(image: Image.Image, max_size: int = 1600) -> Image.Image:
    """dolphin2 reference resize_img(max_size=1600) 동일 로직."""
    w, h = image.size
    if max(w, h) < max_size and min(w, h) >= 28:
        return image
    if w >= h:
        new_w, new_h = max_size, int(h * max_size / w)
    else:
        new_h, new_w = max_size, int(w * max_size / h)
    return image.resize((new_w, new_h), Image.LANCZOS)


def _normalize_base_url(server_url: str, ssl: bool) -> str:
    if not server_url.startswith(("http://", "https://")):
        scheme = "https" if ssl else "http"
        server_url = f"{scheme}://{server_url}"
    # A bare host uses the OpenAI-compatible default. An explicit path is a
    # provider contract and must not be silently rewritten to a different API.
    scheme_end = server_url.find("://") + 3
    path_start = server_url.find("/", scheme_end)
    if path_start == -1:
        return server_url.rstrip("/") + "/v1"
    return server_url.rstrip("/")
