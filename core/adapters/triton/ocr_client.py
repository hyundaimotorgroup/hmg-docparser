from PIL import ImageOps
import tritonclient.http as httpclient
import numpy as np
import json
import io
from collections.abc import Callable

from core.engine.runtime.cancellation import PipelineCancelled


class OCRInferenceError(RuntimeError):
    """Raised when the OCR provider fails instead of disguising it as empty text."""



def add_padding(pil_img, padding_size=50, color=(255, 255, 255)):
    # RGB 변환 (투명 배경 등 방지)
    if pil_img.mode != 'RGB':
        pil_img = pil_img.convert('RGB')

    # 사방에 padding_size 만큼 흰색 테두리 추가
    # left, top, right, bottom
    border = (padding_size, padding_size, padding_size, padding_size)
    padded_img = ImageOps.expand(pil_img, border=border, fill=color)

    return padded_img


def _build_headers(token: str | None = None) -> dict[str, str] | None:
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


def run_batch_ocr_pipeline(
    target_list,
    triton_url: str | None = None,
    padding=75,
    *,
    model_name: str = "ocr_pipeline",
    ssl: bool = False,
    token: str | None = None,
    concurrency: int = 4,
    timeout_seconds: float | None = None,
    cancellation_check: Callable[[], bool] | None = None,
):
    if not isinstance(triton_url, str) or not triton_url.strip():
        raise ValueError("triton_url is required for OCR inference")

    # 동시 요청 처리를 위한 클라이언트 설정
    client = httpclient.InferenceServerClient(
        url=triton_url.strip(),
        concurrency=max(int(concurrency), 1),
        ssl=ssl,
        connection_timeout=_client_timeout_seconds(timeout_seconds),
        network_timeout=_client_timeout_seconds(timeout_seconds),
    )
    headers = _build_headers(token)

    ocr_results = []
    max_in_flight = max(int(concurrency), 1)
    for batch_start in range(0, len(target_list), max_in_flight):
        futures = []
        for item in target_list[batch_start:batch_start + max_in_flight]:
            _raise_if_cancelled(cancellation_check)
            padded_img = add_padding(item['crop'], padding_size=padding)
            with io.BytesIO() as buffer:
                padded_img.save(buffer, format='PNG')
                image_bytes = buffer.getvalue()
            inputs = [httpclient.InferInput("IMAGE_BYTES", [1], "BYTES")]
            inputs[0].set_data_from_numpy(np.array([image_bytes], dtype=object))
            futures.append(client.async_infer(
                model_name, inputs, headers=headers,
                timeout=_request_timeout_microseconds(timeout_seconds),
            ))

        for offset, future in enumerate(futures):
            try:
                _raise_if_cancelled(cancellation_check)
                response = future.get_result()
                json_str = response.as_numpy("OCR_RESULT")[0]
                ocr_results.append(json.loads(json_str))
            except PipelineCancelled:
                raise
            except Exception as exc:
                raise OCRInferenceError(f"OCR inference failed for crop {batch_start + offset}") from exc

    return ocr_results


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
        raise PipelineCancelled("Paddle OCR request cancelled")
