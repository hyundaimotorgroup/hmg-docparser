from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Sequence

import requests
from PIL import Image


def _pil_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _build_url(server_url: str, path: str, ssl: bool) -> str:
    if server_url.startswith("http://") or server_url.startswith("https://"):
        base = server_url.rstrip("/")
    else:
        scheme = "https" if ssl else "http"
        base = f"{scheme}://{server_url.rstrip('/')}"
    return f"{base}{path}"


def _chunk(items: Sequence[Image.Image], size: int) -> list[list[Image.Image]]:
    if not isinstance(size, int) or size <= 0:
        raise ValueError("max_batch_size must be a positive integer")
    return [items[start:start + size] for start in range(0, len(items), size)]


def _headers(token: str | None) -> dict[str, str] | None:
    return {"Authorization": f"Bearer {token}"} if token else None


def _post_chunk(
    url: str,
    images: list[Image.Image],
    *,
    data: dict[str, str] | None,
    headers: dict[str, str] | None,
    timeout: float,
) -> list[int]:
    files = [
        ("images", (f"{i}.png", _pil_to_png_bytes(img), "image/png"))
        for i, img in enumerate(images)
    ]
    response = requests.post(url, files=files, data=data, headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    levels = payload.get("levels") if isinstance(payload, dict) else None
    if not isinstance(levels, list):
        raise ValueError("router response must contain a list field named 'levels'")
    if len(levels) != len(images):
        raise ValueError(
            "router response level count does not match request image count "
            f"({len(levels)} != {len(images)})"
        )
    if any(isinstance(level, bool) or not isinstance(level, int) for level in levels):
        raise ValueError("router response levels must be integers")
    return levels


def _post_batches(
    url: str,
    images: list[Image.Image],
    *,
    data: dict[str, str] | None,
    token: str | None,
    timeout_seconds: float | None,
    max_batch_size: int,
) -> list[int]:
    chunks = _chunk(images, max_batch_size)
    if not chunks:
        return []
    timeout = timeout_seconds or 600.0
    headers = _headers(token)
    if len(chunks) == 1:
        return _post_chunk(url, chunks[0], data=data, headers=headers, timeout=timeout)

    # Keep request concurrency bounded even when a document produces many chunks.
    with ThreadPoolExecutor(max_workers=min(len(chunks), 4)) as executor:
        chunk_results = list(
            executor.map(
                lambda chunk: _post_chunk(url, chunk, data=data, headers=headers, timeout=timeout),
                chunks,
            )
        )
    levels: list[int] = []
    for result in chunk_results:
        levels.extend(result)
    return levels


def infer_stage1(
    server_url: str,
    images: list[Image.Image],
    *,
    ssl: bool = False,
    token: str | None = None,
    timeout_seconds: float | None = None,
    max_batch_size: int = 16,
) -> list[int]:
    url = _build_url(server_url, "/stage1/infer", ssl)
    return _post_batches(
        url, images, data=None, token=token, timeout_seconds=timeout_seconds, max_batch_size=max_batch_size,
    )


def infer_stage2(
    server_url: str,
    block_type: str,
    images: list[Image.Image],
    *,
    ssl: bool = False,
    token: str | None = None,
    timeout_seconds: float | None = None,
    max_batch_size: int = 16,
) -> list[int]:
    url = _build_url(server_url, "/stage2/infer", ssl)
    return _post_batches(
        url,
        images,
        data={"type": block_type},
        token=token,
        timeout_seconds=timeout_seconds,
        max_batch_size=max_batch_size,
    )
