from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
import re

from PIL import Image

from core.domain.artifacts import ArtifactRef
from core.domain.document.models import PageDTO
from core.domain.layout.models import LayoutBlockDTO, PageLayoutDTO
from core.services.pdf_rendering import render_pdf_page
from core.adapters.triton.dolphin_client import (
    parse_layout_string,
    prepare_image,
    process_coordinates,
)


DEFAULT_DOLPHIN_TARGET_SIZE = 2048
DEFAULT_DOLPHIN_V2_TARGET_SIZE = 1600


def render_page_pdf_for_dolphin(
    page: PageDTO,
    *,
    target_size: int = DEFAULT_DOLPHIN_TARGET_SIZE,
) -> Image.Image:
    if page.pdf_artifact is None:
        raise ValueError(f"page has no pdf_artifact: {page.document_id}:{page.page_no}")

    pdf_path = Path(page.pdf_artifact.path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"page PDF not found: {pdf_path}")

    return render_pdf_page(pdf_path, target_size=target_size, require_single_page=True)


def dolphin_layout_text_to_page_layout(
    *,
    page: PageDTO,
    page_image: Image.Image,
    layout_text: str,
    crop_output_dir: str | None = None,
) -> PageLayoutDTO:
    image_width, image_height = page_image.size
    layout_page = replace(page, width=image_width, height=image_height)
    parsed = _validated_layout_items(layout_text, version="v1", page_image=page_image)
    padded_image, dimensions = prepare_image(page_image)

    blocks: list[LayoutBlockDTO] = []
    previous_box = None
    for reading_order, (bbox_norm_896, label) in enumerate(parsed):
        _, _, _, _, x1, y1, x2, y2, previous_box = process_coordinates(
            coords=bbox_norm_896,
            padded_image=padded_image,
            dims=dimensions,
            previous_box=previous_box,
        )
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"layout item {reading_order} resolves to an empty bbox")
        if not (0 <= x1 < x2 <= image_width and 0 <= y1 < y2 <= image_height):
            raise ValueError(f"layout item {reading_order} resolves outside page bounds")

        crop_artifact = _save_crop_artifact(
            page=page,
            page_image=page_image,
            bbox=(x1, y1, x2, y2),
            label=label,
            reading_order=reading_order,
            crop_output_dir=crop_output_dir,
        )
        blocks.append(
            LayoutBlockDTO(
                block_id=f"{page.document_id}:{page.page_no}:{reading_order}",
                label=str(label or ""),
                bbox=(x1, y1, x2, y2),
                reading_order=reading_order,
                crop_artifact=crop_artifact,
                metadata={
                    "dolphin_bbox_norm_896": tuple(float(value) for value in bbox_norm_896),
                    "dolphin_has_crop": crop_artifact is not None,
                    "layout_item_idx": len(blocks),
                },
            )
        )

    _validate_blocks(blocks, expected_count=len(parsed))
    return PageLayoutDTO(page=layout_page, blocks=blocks)


def dolphin_vllm_layout_text_to_page_layout(
    *,
    page: PageDTO,
    page_image: Image.Image,
    layout_text: str,
    crop_output_dir: str | None = None,
) -> PageLayoutDTO:
    """dolphin2(vLLM) 전용 좌표 변환.

    모델 출력 좌표는 smart_resize 이후 패치 해상도 기준이므로
    dolphin2 reference process_coordinates() 로직으로 역변환한다.
    """
    image_width, image_height = page_image.size
    layout_page = replace(page, width=image_width, height=image_height)
    parsed = _validated_layout_items(layout_text, version="v2", page_image=page_image)

    blocks: list[LayoutBlockDTO] = []
    for reading_order, (bbox_model, label) in enumerate(parsed):
        x1, y1, x2, y2 = _vllm_coords_to_pixels(bbox_model, page_image)
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"layout item {reading_order} resolves to an empty bbox")

        crop_artifact = _save_crop_artifact(
            page=page,
            page_image=page_image,
            bbox=(x1, y1, x2, y2),
            label=label,
            reading_order=reading_order,
            crop_output_dir=crop_output_dir,
        )
        blocks.append(
            LayoutBlockDTO(
                block_id=f"{page.document_id}:{page.page_no}:{reading_order}",
                label=str(label or ""),
                bbox=(x1, y1, x2, y2),
                reading_order=reading_order,
                crop_artifact=crop_artifact,
                metadata={
                    "dolphin_bbox_model": tuple(float(v) for v in bbox_model),
                    "dolphin_has_crop": crop_artifact is not None,
                    "layout_item_idx": len(blocks),
                },
            )
        )

    _validate_blocks(blocks, expected_count=len(parsed))
    return PageLayoutDTO(page=layout_page, blocks=blocks)


def _validated_layout_items(
    layout_text: str,
    *,
    version: str,
    page_image: Image.Image,
) -> list[tuple[list[float], str]]:
    if not isinstance(layout_text, str) or not layout_text.strip():
        raise ValueError("layout provider returned an empty response")
    parsed = parse_layout_string(layout_text)
    if not parsed:
        raise ValueError("layout provider returned no valid layout items")

    if version == "v1":
        max_x = max_y = 896.0
    else:
        resized = _resize_for_model(page_image)
        max_y, max_x = _smart_resize(resized.height, resized.width)

    validated: list[tuple[list[float], str]] = []
    for index, (coords, label) in enumerate(parsed):
        if len(coords) != 4 or not all(math.isfinite(value) for value in coords):
            raise ValueError(f"layout item {index} has invalid bbox coordinates")
        x1, y1, x2, y2 = coords
        if not (0 <= x1 < x2 <= max_x and 0 <= y1 < y2 <= max_y):
            raise ValueError(f"layout item {index} has out-of-range bbox coordinates")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"layout item {index} has an empty label")
        validated.append((coords, label.strip()))
    return validated


def _validate_blocks(blocks: list[LayoutBlockDTO], *, expected_count: int) -> None:
    if len(blocks) != expected_count:
        raise ValueError("layout block coverage does not match provider response")
    block_ids = [block.block_id for block in blocks]
    if len(block_ids) != len(set(block_ids)):
        raise ValueError("layout provider produced duplicate block IDs")
    orders = [block.reading_order for block in blocks]
    if orders != list(range(expected_count)):
        raise ValueError("layout provider produced invalid reading order")


def _vllm_coords_to_pixels(
    coords: list[float],
    original_image: Image.Image,
) -> tuple[int, int, int, int]:
    """dolphin2 reference process_coordinates() 포팅.

    모델이 본 해상도(resize_img → smart_resize)와 원본 이미지의
    비율로 좌표를 원본 픽셀 공간으로 역변환한다.
    """
    orig_w, orig_h = original_image.size
    resized = _resize_for_model(original_image)
    rw, rh = resized.size
    model_h, model_w = _smart_resize(rh, rw)

    w_ratio = orig_w / model_w
    h_ratio = orig_h / model_h
    x1 = max(0, min(int(coords[0] * w_ratio), orig_w - 1))
    y1 = max(0, min(int(coords[1] * h_ratio), orig_h - 1))
    x2 = max(x1 + 1, min(int(coords[2] * w_ratio), orig_w))
    y2 = max(y1 + 1, min(int(coords[3] * h_ratio), orig_h))
    return x1, y1, x2, y2


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


def _smart_resize(
    height: int,
    width: int,
    factor: int = 28,
    min_pixels: int = 784,
    max_pixels: int = 2_560_000,
) -> tuple[int, int]:
    """qwen_vl_utils.smart_resize 동일 로직."""
    h_bar = round(height / factor) * factor
    w_bar = round(width / factor) * factor
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = math.floor(height / beta / factor) * factor
        w_bar = math.floor(width / beta / factor) * factor
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = math.ceil(height * beta / factor) * factor
        w_bar = math.ceil(width * beta / factor) * factor
    return h_bar, w_bar


def _save_crop_artifact(
    *,
    page: PageDTO,
    page_image: Image.Image,
    bbox: tuple[int, int, int, int],
    label: str,
    reading_order: int,
    crop_output_dir: str | None,
) -> ArtifactRef | None:
    if not crop_output_dir:
        return None

    output_dir = Path(crop_output_dir) / page.document_id
    output_dir.mkdir(parents=True, exist_ok=True)
    crop = page_image.crop(bbox)
    label_slug = _slug(label) or "block"
    crop_path = output_dir / f"p{page.page_no:04d}_{reading_order:04d}_{label_slug}.png"
    crop.save(crop_path)
    return ArtifactRef(
        path=str(crop_path),
        media_type="image/png",
        description="dolphin layout crop",
    )


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip()).strip("_")
