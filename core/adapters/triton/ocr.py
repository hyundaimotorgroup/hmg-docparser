from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PIL import Image

from core.domain.inference.models import OCRResultDTO, OCRTextLineDTO
from core.interfaces.adapters import ModelAdapter
from core.adapters.triton.ocr_client import run_batch_ocr_pipeline


@dataclass(slots=True)
class PaddleOCRRequest:
    images: Sequence[Image.Image]
    server_url: str
    model_name: str = "paddle"
    padding: int = 75
    ssl: bool = False
    token: str | None = None
    concurrency: int = 4
    timeout_seconds: float | None = None
    cancellation_check: Callable[[], bool] | None = None


class PaddleTritonOCRAdapter(ModelAdapter):
    def invoke(self, payload: object) -> list[OCRResultDTO]:
        if not isinstance(payload, PaddleOCRRequest):
            raise TypeError("PaddleTritonOCRAdapter expects PaddleOCRRequest")

        raw_results = run_batch_ocr_pipeline(
            [{"crop": image} for image in payload.images],
            triton_url=payload.server_url,
            padding=payload.padding,
            model_name=payload.model_name,
            ssl=payload.ssl,
            token=payload.token,
            concurrency=payload.concurrency,
            timeout_seconds=payload.timeout_seconds,
            cancellation_check=payload.cancellation_check,
        )
        return [_raw_ocr_result_to_dto(raw_result) for raw_result in raw_results]


def _raw_ocr_result_to_dto(raw_result: object) -> OCRResultDTO:
    lines: list[OCRTextLineDTO] = []
    if isinstance(raw_result, list):
        for item in raw_result:
            if not isinstance(item, (list, tuple)) or not item:
                continue
            text = str(item[0])
            score = _safe_float(item[1]) if len(item) > 1 else None
            lines.append(OCRTextLineDTO(text=text, score=score))

    scores = [line.score for line in lines if line.score is not None]
    average_score = sum(scores) / len(scores) if scores else None
    return OCRResultDTO(lines=lines, average_score=average_score)


def _safe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
