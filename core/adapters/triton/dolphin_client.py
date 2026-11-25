import io
import re
from dataclasses import dataclass
from collections.abc import Callable
from typing import List, Tuple, Union

import numpy as np
from PIL import Image
import tritonclient.http as httpclient

from core.engine.runtime.cancellation import PipelineCancelled
from core.services.pdf_rendering import render_pdf_pages


def convert_pdf_to_images(pdf_path, target_size=2048):
    """Convert PDF pages to detached RGB images with the given long-edge size."""
    try:
        images = render_pdf_pages(pdf_path, target_size=target_size)
        print(f"Successfully converted {len(images)} pages from PDF")
        return images
    except Exception as e:
        print(f"Error converting PDF to images: {str(e)}")
        return []


def pil_to_bytes(pil_image: Image.Image, image_format: str = 'PNG') -> bytes:
    """PIL(Pillow) 이미지 객체를 bytes로 변환"""
    with io.BytesIO() as buffer:
        pil_image.save(buffer, format=image_format)
        image_bytes = buffer.getvalue()
    return image_bytes


def run_batch_inference(
    server_url: str,
    model_name: str,
    images: Union[Image.Image, List[Image.Image], str, List[str]],
    prompt: str = "Parse the reading order of this document.",
    max_batch_size: int = 8,
    *,
    ssl: bool = False,
    token: str | None = None,
    timeout_seconds: float | None = None,
    cancellation_check: Callable[[], bool] | None = None,
) -> Union[List[str], None]:
    try:
        _raise_if_cancelled(cancellation_check)
        network_timeout = _client_timeout_seconds(timeout_seconds)
        client = httpclient.InferenceServerClient(
            url=server_url,
            ssl=ssl,
            connection_timeout=network_timeout,
            network_timeout=network_timeout,
        )
        headers = {"Authorization": f"Bearer {token}"} if token else None

        # 1) 입력 정규화
        image_list = images if isinstance(images, list) else [images]
        image_bytes_list = []
        for img in image_list:
            _raise_if_cancelled(cancellation_check)
            if isinstance(img, str):
                with open(img, "rb") as f:
                    image_bytes_list.append(f.read())
            elif isinstance(img, Image.Image):
                image_bytes_list.append(pil_to_bytes(img))
            else:
                raise TypeError(f"지원하지 않는 이미지 타입입니다: {type(img)}")

        total = len(image_bytes_list)
        if total == 0:
            print("[WARN] 처리할 이미지가 없습니다.")
            return []

        # 2) chunk 단위로 infer
        if max_batch_size <= 0:
            max_batch_size = 1

        all_results: List[str] = []
        for start in range(0, total, max_batch_size):
            _raise_if_cancelled(cancellation_check)
            chunk = image_bytes_list[start:start + max_batch_size]
            batch_size = len(chunk)

            prompts = [prompt.encode("utf-8")] * batch_size
            text_data = np.array(prompts, dtype=np.object_).reshape(batch_size, 1)
            text_input = httpclient.InferInput("input_text", text_data.shape, "BYTES")
            text_input.set_data_from_numpy(text_data)

            image_data = np.array(chunk, dtype=np.object_).reshape(batch_size, 1)
            image_input = httpclient.InferInput("input_image", image_data.shape, "BYTES")
            image_input.set_data_from_numpy(image_data)

            response = client.infer(
                model_name=model_name,
                inputs=[text_input, image_input],
                outputs=[httpclient.InferRequestedOutput("output_text")],
                headers=headers,
                timeout=_request_timeout_microseconds(timeout_seconds),
            )

            raw_output = response.as_numpy("output_text")
            chunk_results = _decode_output_tensor(raw_output)
            if len(chunk_results) != batch_size:
                chunk_results = _infer_chunk_one_by_one(
                    client=client,
                    model_name=model_name,
                    image_bytes_list=chunk,
                    prompt=prompt,
                    headers=headers,
                    timeout_seconds=timeout_seconds,
                    cancellation_check=cancellation_check,
                )
            all_results.extend(chunk_results)

        return all_results

    except PipelineCancelled:
        raise
    except Exception as exc:
        raise RuntimeError("Dolphin Triton layout inference failed") from exc


def _infer_chunk_one_by_one(
    *,
    client: httpclient.InferenceServerClient,
    model_name: str,
    image_bytes_list: list[bytes],
    prompt: str,
    headers: dict[str, str] | None,
    timeout_seconds: float | None,
    cancellation_check: Callable[[], bool] | None,
) -> list[str]:
    results: list[str] = []
    for image_bytes in image_bytes_list:
        _raise_if_cancelled(cancellation_check)
        text_data = np.array([[prompt.encode("utf-8")]], dtype=np.object_)
        text_input = httpclient.InferInput("input_text", text_data.shape, "BYTES")
        text_input.set_data_from_numpy(text_data)

        image_data = np.array([[image_bytes]], dtype=np.object_)
        image_input = httpclient.InferInput("input_image", image_data.shape, "BYTES")
        image_input.set_data_from_numpy(image_data)

        response = client.infer(
            model_name=model_name,
            inputs=[text_input, image_input],
            outputs=[httpclient.InferRequestedOutput("output_text")],
            headers=headers,
            timeout=_request_timeout_microseconds(timeout_seconds),
        )
        decoded = _decode_output_tensor(response.as_numpy("output_text"))
        if len(decoded) != 1:
            raise ValueError(f"unexpected dolphin output count for single infer: {len(decoded)}")
        results.append(decoded[0])
    return results


def _decode_output_tensor(raw_output: np.ndarray) -> list[str]:
    values: list[str] = []
    for item in raw_output.flat:
        if isinstance(item, bytes):
            values.append(item.decode("utf-8"))
        elif isinstance(item, str):
            values.append(item)
    return values


def _client_timeout_seconds(timeout_seconds: float | None) -> float:
    if timeout_seconds is None:
        return 600.0
    return max(float(timeout_seconds), 1.0)


def _request_timeout_microseconds(timeout_seconds: float | None) -> int | None:
    if timeout_seconds is None:
        return None
    return max(int(max(float(timeout_seconds), 1.0) * 1_000_000), 1)


def _raise_if_cancelled(cancellation_check: Callable[[], bool] | None) -> None:
    if cancellation_check is not None and cancellation_check():
        raise PipelineCancelled("Dolphin Triton request cancelled")


def parse_layout_string(bbox_str):
    """
    Dolphin-V1.5 layout string parsing function
    Parse layout string to extract bbox and category information
    Supports multiple formats:
    1. Original format: [x1,y1,x2,y2] label
    2. New format: [x1,y1,x2,y2][label][PAIR_SEP] or [x1,y1,x2,y2][label][meta_info][PAIR_SEP]
    """
    parsed_results = []

    segments = bbox_str.split('[PAIR_SEP]')
    new_segments = []
    for seg in segments:
        new_segments.extend(seg.split('[RELATION_SEP]'))
    segments = new_segments
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        number_pattern = r'(?:\d+(?:\.\d+)?|\.\d+)'
        coord_pattern = (
            rf'\[({number_pattern}),({number_pattern}),'
            rf'({number_pattern}),({number_pattern})\]'
        )
        label_pattern = r'\]\[([^\]]+)\]'

        coord_match = re.search(coord_pattern, segment)
        label_matches = re.findall(label_pattern, segment)

        if coord_match and label_matches:
            coords = [float(coord_match.group(i)) for i in range(1, 5)]
            label = label_matches[0].strip()
            parsed_results.append((coords, label))

    return parsed_results


@dataclass
class ImageDimensions:
    """Class to store image dimensions"""

    original_w: int
    original_h: int
    padded_w: int
    padded_h: int


def prepare_image(image) -> Tuple[np.ndarray, ImageDimensions]:
    """Load and prepare image with padding while maintaining aspect ratio

    Args:
        image: PIL image

    Returns:
        tuple: (padded_image, image_dimensions)
    """
    import cv2

    try:
        # Convert PIL image to OpenCV format
        image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        original_h, original_w = image.shape[:2]

        # Calculate padding to make square image
        max_size = max(original_h, original_w)
        top = (max_size - original_h) // 2
        bottom = max_size - original_h - top
        left = (max_size - original_w) // 2
        right = max_size - original_w - left

        # Apply padding
        padded_image = cv2.copyMakeBorder(image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(0, 0, 0))

        padded_h, padded_w = padded_image.shape[:2]

        dimensions = ImageDimensions(original_w=original_w, original_h=original_h, padded_w=padded_w, padded_h=padded_h)

        return padded_image, dimensions
    except Exception as e:
        print(f"prepare_image error: {str(e)}")
        # Create a minimal valid image and dimensions
        h, w = image.height, image.width
        dimensions = ImageDimensions(original_w=w, original_h=h, padded_w=w, padded_h=h)
        # Return a black image of the same size
        return np.zeros((h, w, 3), dtype=np.uint8), dimensions


def map_to_original_coordinates(x1, y1, x2, y2, dims: ImageDimensions) -> Tuple[int, int, int, int]:
    """Map coordinates from padded image back to original image

    Args:
        x1, y1, x2, y2: Coordinates in padded image
        dims: Image dimensions object

    Returns:
        tuple: (x1, y1, x2, y2) coordinates in original image
    """
    try:
        # Calculate padding offsets
        top = (dims.padded_h - dims.original_h) // 2
        left = (dims.padded_w - dims.original_w) // 2

        # Map back to original coordinates
        orig_x1 = max(0, x1 - left)
        orig_y1 = max(0, y1 - top)
        orig_x2 = min(dims.original_w, x2 - left)
        orig_y2 = min(dims.original_h, y2 - top)

        # Ensure we have a valid box (width and height > 0)
        if orig_x2 <= orig_x1:
            orig_x2 = min(orig_x1 + 1, dims.original_w)
        if orig_y2 <= orig_y1:
            orig_y2 = min(orig_y1 + 1, dims.original_h)

        return int(orig_x1), int(orig_y1), int(orig_x2), int(orig_y2)
    except Exception as e:
        print(f"map_to_original_coordinates error: {str(e)}")
        # Return safe coordinates
        return 0, 0, min(100, dims.original_w), min(100, dims.original_h)


def process_coordinates(coords, padded_image, dims: ImageDimensions, previous_box=None):
    """Process and adjust coordinates

    Args:
        coords: Normalized coordinates [x1, y1, x2, y2]
        padded_image: Padded image
        dims: Image dimensions object
        previous_box: Previous box coordinates for overlap adjustment

    Returns:
        tuple: (x1, y1, x2, y2, orig_x1, orig_y1, orig_x2, orig_y2, new_previous_box)
    """
    try:
        # Convert normalized coordinates to absolute coordinates
        x1, y1 = round(coords[0] / 896. * dims.padded_w), round(coords[1] / 896. * dims.padded_h)
        x2, y2 = round(coords[2] / 896. * dims.padded_w) + 1, round(coords[3] / 896. * dims.padded_h) + 1

        # Ensure coordinates are within image bounds before adjustment
        x1 = max(0, min(x1, dims.padded_w - 1))
        y1 = max(0, min(y1, dims.padded_h - 1))
        x2 = max(0, min(x2, dims.padded_w))
        y2 = max(0, min(y2, dims.padded_h))

        # Ensure width and height are at least 1 pixel
        if x2 <= x1:
            x2 = min(x1 + 1, dims.padded_w)
        if y2 <= y1:
            y2 = min(y1 + 1, dims.padded_h)

        # Ensure coordinates are still within image bounds after adjustment
        x1 = max(0, min(x1, dims.padded_w - 1))
        y1 = max(0, min(y1, dims.padded_h - 1))
        x2 = max(0, min(x2, dims.padded_w))
        y2 = max(0, min(y2, dims.padded_h))

        # Ensure width and height are at least 1 pixel after adjustment
        if x2 <= x1:
            x2 = min(x1 + 1, dims.padded_w)
        if y2 <= y1:
            y2 = min(y1 + 1, dims.padded_h)

        # Check for overlap with previous box and adjust
        if previous_box is not None:
            prev_x1, prev_y1, prev_x2, prev_y2 = previous_box
            if (x1 < prev_x2 and x2 > prev_x1) and (y1 < prev_y2 and y2 > prev_y1):
                y1 = prev_y2
                # Ensure y1 is still valid
                y1 = min(y1, dims.padded_h - 1)
                # Make sure y2 is still greater than y1
                if y2 <= y1:
                    y2 = min(y1 + 1, dims.padded_h)

        # Update previous box
        new_previous_box = [x1, y1, x2, y2]

        # Map to original coordinates
        orig_x1, orig_y1, orig_x2, orig_y2 = map_to_original_coordinates(x1, y1, x2, y2, dims)

        return x1, y1, x2, y2, orig_x1, orig_y1, orig_x2, orig_y2, new_previous_box
    except Exception as e:
        print(f"process_coordinates error: {str(e)}")
        # Return safe values
        orig_x1, orig_y1, orig_x2, orig_y2 = 0, 0, min(100, dims.original_w), min(100, dims.original_h)
        return 0, 0, 100, 100, orig_x1, orig_y1, orig_x2, orig_y2, [0, 0, 100, 100]


def draw_annotations_on_page(image: Image.Image, page_meta: dict):
    """하나의 페이지에 bbox와 텍스트를 그려 반환한다."""
    import cv2

    # 1. PIL → numpy(BGR)
    RECT_COLOR = (0, 255, 0)  # BGR
    RECT_THICK = 1
    FONT = cv2.FONT_HERSHEY_SIMPLEX
    FONT_SCALE = 0.5
    FONT_THICK = 1
    FONT_COLOR = (255, 0, 0)  # BGR

    padded_img, dims = prepare_image(image)

    # 3. draw each element
    for reading_order, el in enumerate(page_meta):
        # _, _, _, _, x1, y1, x2, y2, _ = process_coordinates(el[0], padded_image, dims, previous_box=None)
        x1, y1, x2, y2,_, _, _, _,  _ = process_coordinates(el[0], padded_img, dims, previous_box=None)
        # x1, y1, x2, y2 = el[0]

        cv2.rectangle(padded_img, (x1, y1), (x2, y2), RECT_COLOR, RECT_THICK)

        label_text = f'{reading_order}) {el[1]}'
        # 텍스트가 박스 안을 벗어나지 않도록 y 좌표 clamp
        text_y = max(y1 - 4, 0)
        cv2.putText(padded_img, label_text, (x1, text_y), FONT,
                    FONT_SCALE, FONT_COLOR, FONT_THICK, cv2.LINE_AA)

    # 4. numpy(BGR) → PIL(RGB)
    annotated_pil = Image.fromarray(cv2.cvtColor(padded_img, cv2.COLOR_BGR2RGB))
    return annotated_pil
