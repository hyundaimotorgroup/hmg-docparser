"""HTTP clients for user-operated, loopback model tutorials."""

from __future__ import annotations

import base64
import io
from collections.abc import Callable, Sequence

import requests
from PIL import Image, ImageOps

from core.domain.inference.models import OCRResultDTO, OCRTextLineDTO
from core.engine.runtime.cancellation import PipelineCancelled


def _image_base64(image: Image.Image) -> str:
    with io.BytesIO() as buffer:
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")


def _request_json(
    url: str,
    image: Image.Image,
    *,
    timeout_seconds: float | None,
    cancellation_check: Callable[[], bool] | None,
    prompt: str | None = None,
) -> dict:
    if cancellation_check is not None and cancellation_check():
        raise PipelineCancelled("Local model request cancelled")
    payload = {"image_base64": _image_base64(image)}
    if prompt is not None:
        payload["prompt"] = prompt
    try:
        response = requests.post(url, json=payload, timeout=timeout_seconds or 600.0)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.Timeout as exc:
        raise RuntimeError("Local model request timed out") from exc
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        raise RuntimeError(f"Local model request failed (HTTP {status})") from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError("Local model request failed") from exc
    if not isinstance(data, dict):
        raise ValueError("Local model returned a non-object JSON response")
    return data


def infer_local_dolphin_layout(
    images: Sequence[Image.Image], server_url: str, prompt: str,
    *, timeout_seconds: float | None, cancellation_check: Callable[[], bool] | None,
) -> list[str]:
    url = server_url.rstrip("/") + "/v1/layout"
    results = []
    for image in images:
        data = _request_json(url, image, prompt=prompt, timeout_seconds=timeout_seconds,
                             cancellation_check=cancellation_check)
        layout_text = data.get("layout_text")
        if not isinstance(layout_text, str) or not layout_text.strip():
            raise ValueError("Local Dolphin returned empty layout_text")
        results.append(layout_text)
    return results


def infer_local_paddle_ocr(
    images: Sequence[Image.Image], server_url: str,
    *, padding: int, timeout_seconds: float | None,
    cancellation_check: Callable[[], bool] | None,
) -> list[OCRResultDTO]:
    url = server_url.rstrip("/") + "/v1/ocr"
    results = []
    for image in images:
        padded = ImageOps.expand(image.convert("RGB"), border=padding, fill=(255, 255, 255))
        data = _request_json(url, padded, timeout_seconds=timeout_seconds,
                             cancellation_check=cancellation_check)
        lines = data.get("lines")
        if not isinstance(lines, list):
            raise ValueError("Local Paddle returned invalid lines")
        parsed = []
        for line in lines:
            if not isinstance(line, dict) or not isinstance(line.get("text"), str):
                raise ValueError("Local Paddle returned an invalid OCR line")
            score = line.get("score")
            if score is not None and (not isinstance(score, (int, float)) or isinstance(score, bool)):
                raise ValueError("Local Paddle returned an invalid OCR score")
            parsed.append(OCRTextLineDTO(text=line["text"], score=float(score) if score is not None else None))
        scores = [line.score for line in parsed if line.score is not None]
        results.append(OCRResultDTO(lines=parsed, average_score=sum(scores) / len(scores) if scores else None))
    return results
