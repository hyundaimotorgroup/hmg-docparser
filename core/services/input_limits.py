"""Configurable input budgets shared by the optional HTTP servers."""

from __future__ import annotations

import base64
import io
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image


class InputTooLarge(ValueError):
    """An otherwise readable request exceeds a configured input budget."""


def configured_limit(name: str, default: int) -> int:
    """Read a non-negative integer; zero disables this additional budget."""
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def decode_base64(value: str, max_bytes: int) -> bytes:
    # Bound the allocation before decoding, including Paddle's previous decode-first path.
    if max_bytes and len(value) > 4 * ((max_bytes + 2) // 3):
        raise InputTooLarge("image bytes exceed the configured limit")
    raw = base64.b64decode(value, validate=True)
    if max_bytes and len(raw) > max_bytes:
        raise InputTooLarge("image bytes exceed the configured limit")
    return raw


def image_pixels(image: Image.Image, max_pixels: int) -> int:
    pixels = image.width * image.height
    if max_pixels and pixels > max_pixels:
        raise InputTooLarge("image pixels exceed the configured limit")
    return pixels


def decode_rgb_image(raw: bytes, max_pixels: int) -> Image.Image:
    """Validate metadata and file integrity before allocating a detached RGB image."""
    from PIL import Image

    try:
        with Image.open(io.BytesIO(raw)) as source:
            image_pixels(source, max_pixels)
            source.verify()
        with Image.open(io.BytesIO(raw)) as source:
            image_pixels(source, max_pixels)
            source.load()
            return source.convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        # Preserve Pillow's protection even when the application pixel budget is disabled.
        raise InputTooLarge("image exceeds Pillow's safe pixel limit") from exc
