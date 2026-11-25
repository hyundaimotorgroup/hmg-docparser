"""Local-only FastAPI wrapper around PaddleOCR's Korean PP-OCRv5 mobile models."""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
import numpy as np
from PIL import Image
from pydantic import BaseModel, Field
import yaml

# PaddleX downloads first-run assets through requests. On managed macOS
# devices, include trusted certificates from the system Keychain, such as an
# organization proxy CA, rather than relying only on certifi's public roots.
import truststore

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.services.http_limits import RequestLimitsMiddleware
from core.services.input_limits import InputTooLarge, configured_limit, decode_base64, decode_rgb_image

MAX_IMAGE_BYTES = configured_limit("PADDLE_OCR_MAX_IMAGE_BYTES", 64 * 1024 * 1024)
MAX_IMAGE_PIXELS = configured_limit("PADDLE_OCR_MAX_IMAGE_PIXELS", 128_000_000)
TEXT_DETECTION_MODEL = "PP-OCRv5_mobile_det"
TEXT_RECOGNITION_MODEL = "korean_PP-OCRv5_mobile_rec"
KOREAN_RECOGNITION_REPOSITORY = "PaddlePaddle/korean_PP-OCRv5_mobile_rec"
MODEL_ROOT = os.getenv("PADDLE_OCR_MODEL_ROOT")
LOCAL_MODEL_ROOT = Path(MODEL_ROOT).expanduser().resolve() if MODEL_ROOT else None
TEXT_DETECTION_DIRECTORY = LOCAL_MODEL_ROOT / TEXT_DETECTION_MODEL if LOCAL_MODEL_ROOT else None
KOREAN_RECOGNITION_DIRECTORY = (
    LOCAL_MODEL_ROOT / TEXT_RECOGNITION_MODEL if LOCAL_MODEL_ROOT else
    Path(__file__).with_name(".cache") / "korean_PP-OCRv5_mobile_rec_infer"
)
KOREAN_DICTIONARY_FILE = KOREAN_RECOGNITION_DIRECTORY / "ppocrv5_korean_dict.txt"
KOREAN_DICTIONARY_URL = (
    "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/"
    "ppocr/utils/dict/ppocrv5_korean_dict.txt"
)
INSTANCE_ID = os.getenv("PADDLE_OCR_INSTANCE_ID", "manual")


class OCRRequest(BaseModel):
    """A single image encoded as standard base64 (without a data-URL prefix)."""

    image_base64: str = Field(min_length=1)


class OCRLine(BaseModel):
    text: str
    score: float | None = None


class OCRResponse(BaseModel):
    lines: list[OCRLine]


class OCRService:
    def __init__(self) -> None:
        if TEXT_DETECTION_DIRECTORY is not None:
            _validate_model_files(TEXT_DETECTION_DIRECTORY)
            print(f"Using local Paddle detection model: {TEXT_DETECTION_DIRECTORY}", flush=True)
        _download_korean_recognition_assets()
        from paddleocr import PaddleOCR

        self._predict_lock = threading.Lock()
        print("Loading Paddle detection and Korean recognition models...", flush=True)
        self._pipeline = PaddleOCR(
            text_detection_model_name=TEXT_DETECTION_MODEL,
            text_detection_model_dir=str(TEXT_DETECTION_DIRECTORY) if TEXT_DETECTION_DIRECTORY else None,
            text_recognition_model_name=TEXT_RECOGNITION_MODEL,
            text_recognition_model_dir=str(KOREAN_RECOGNITION_DIRECTORY),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device=os.getenv("PADDLE_OCR_DEVICE", "cpu"),
        )
        self.model_provenance = _model_provenance(self._pipeline)
        print(
            "PADDLE_OCR_MODEL_PROVENANCE="
            + json.dumps(self.model_provenance, ensure_ascii=False, sort_keys=True),
            flush=True,
        )

    def recognize(self, image: Image.Image) -> list[OCRLine]:
        image_array = np.asarray(image.convert("RGB"))
        with self._predict_lock:
            results = self._pipeline.predict(image_array)
        return _extract_lines(results)


def _validate_model_files(directory: Path) -> None:
    missing = [
        name for name in ("inference.json", "inference.pdiparams", "inference.yml")
        if not (directory / name).is_file() or (directory / name).stat().st_size == 0
    ]
    if missing:
        raise RuntimeError(f"Paddle model is incomplete: {directory}; missing or empty: " + ", ".join(missing))


def _download_korean_recognition_assets() -> None:
    """Fetch the Korean PP-OCRv5 inference export and its decoder dictionary."""

    required_model_files = ("inference.json", "inference.pdiparams", "inference.yml")
    if LOCAL_MODEL_ROOT is None and not all(
        (KOREAN_RECOGNITION_DIRECTORY / name).is_file() for name in required_model_files
    ):
        from huggingface_hub import snapshot_download

        print(f"Downloading Korean Paddle recognition model: {KOREAN_RECOGNITION_REPOSITORY}", flush=True)
        KOREAN_RECOGNITION_DIRECTORY.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=KOREAN_RECOGNITION_REPOSITORY,
            local_dir=KOREAN_RECOGNITION_DIRECTORY,
        )

    _validate_model_files(KOREAN_RECOGNITION_DIRECTORY)

    if not KOREAN_DICTIONARY_FILE.is_file():
        if LOCAL_MODEL_ROOT is not None:
            raise RuntimeError(f"Local Paddle dictionary is missing: {KOREAN_DICTIONARY_FILE}")
        print("Downloading Korean Paddle decoder dictionary...", flush=True)
        urllib.request.urlretrieve(KOREAN_DICTIONARY_URL, KOREAN_DICTIONARY_FILE)

    print(f"Using Paddle recognition model: {KOREAN_RECOGNITION_DIRECTORY}", flush=True)

    dictionary = KOREAN_DICTIONARY_FILE.read_text(encoding="utf-8").splitlines()
    if len(dictionary) < 3000 or not any("가" <= character <= "힣" for character in dictionary):
        raise RuntimeError(f"Korean PP-OCRv5 dictionary is invalid: {KOREAN_DICTIONARY_FILE}")

    # PaddleX 3.x decodes local recognition models from inference.yml.  Bind
    # the upstream Korean dictionary here rather than accepting the generic
    # Chinese dictionary that may be present in another cached v5 model.
    config_path = KOREAN_RECOGNITION_DIRECTORY / "inference.yml"
    model_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(model_config, dict) or not isinstance(model_config.get("PostProcess"), dict):
        raise RuntimeError(f"Korean PP-OCRv5 inference config is invalid: {config_path}")
    postprocess = model_config["PostProcess"]
    if postprocess.get("character_dict") != dictionary:
        postprocess["character_dict"] = dictionary
        config_path.write_text(
            yaml.safe_dump(model_config, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> Iterator[None]:
    truststore.inject_into_ssl()
    pid_file = os.getenv("PADDLE_OCR_PID_FILE")
    if pid_file:
        Path(pid_file).write_text(str(os.getpid()), encoding="utf-8")
    try:
        app.state.ocr_service = OCRService()
        yield
    finally:
        if pid_file:
            Path(pid_file).unlink(missing_ok=True)


app = FastAPI(title="Local PaddleOCR", version="0.1.0", docs_url="/docs", redoc_url=None, lifespan=lifespan)
app.add_middleware(
    RequestLimitsMiddleware, paths={"/v1/ocr"},
    max_request_bytes=configured_limit("PADDLE_OCR_MAX_REQUEST_BYTES", 128 * 1024 * 1024),
    max_concurrent_requests=configured_limit("PADDLE_OCR_MAX_CONCURRENT_REQUESTS", 8),
    max_queued_requests=configured_limit("PADDLE_OCR_MAX_QUEUED_REQUESTS", 64),
    read_timeout_seconds=configured_limit("PADDLE_OCR_READ_TIMEOUT_SECONDS", 900),
)


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    service: OCRService = app.state.ocr_service
    return {"status": "ok", "instance_id": INSTANCE_ID, "models": service.model_provenance}


@app.post("/v1/ocr", response_model=OCRResponse)
def ocr(request: OCRRequest) -> OCRResponse:
    image = _decode_image(request.image_base64)
    try:
        service: OCRService = app.state.ocr_service
        return OCRResponse(lines=service.recognize(image))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="PaddleOCR inference failed") from exc
    finally:
        image.close()


def _decode_image(value: str) -> Image.Image:
    try:
        decoded = decode_base64(value, MAX_IMAGE_BYTES)
    except InputTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="image_base64 must be valid base64") from exc
    try:
        return decode_rgb_image(decoded, MAX_IMAGE_PIXELS)
    except InputTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except (OSError, ValueError, SyntaxError) as exc:
        raise HTTPException(status_code=422, detail="image_base64 does not contain a valid image") from exc


def _model_provenance(pipeline: Any) -> dict[str, Any]:
    """Return the model identifiers and cache paths reported by PaddleX."""

    implementation = getattr(getattr(pipeline, "paddlex_pipeline", None), "_pipeline", None)
    if implementation is None:
        return {
            "requested_detection_model": TEXT_DETECTION_MODEL,
            "requested_recognition_model": TEXT_RECOGNITION_MODEL,
            "reported_models": {},
        }

    return {
        "requested_detection_model": TEXT_DETECTION_MODEL,
        "requested_recognition_model": TEXT_RECOGNITION_MODEL,
        "reported_models": {
            "detection": _reported_model_metadata(getattr(implementation, "text_det_model", None)),
            "recognition": _reported_model_metadata(getattr(implementation, "text_rec_model", None)),
        },
    }


def _reported_model_metadata(model: Any) -> dict[str, str]:
    if model is None:
        return {}

    metadata: dict[str, str] = {}
    for attribute in ("model_name", "model_dir", "model_path", "model_root"):
        value = getattr(model, attribute, None)
        if isinstance(value, (str, os.PathLike)):
            metadata[attribute] = os.fspath(value)

    config = getattr(model, "config", None)
    if isinstance(config, dict):
        for values in (config, config.get("Global")):
            if not isinstance(values, dict):
                continue
            for key in ("model_name", "model_dir", "model_path", "model_root"):
                value = values.get(key)
                if isinstance(value, (str, os.PathLike)):
                    metadata.setdefault(key, os.fspath(value))
    return metadata


def _extract_lines(results: Any) -> list[OCRLine]:
    lines: list[OCRLine] = []
    for result in results:
        payload = _result_to_dict(result)
        response = payload.get("res", payload)
        texts = response.get("rec_texts", []) if isinstance(response, dict) else []
        scores = response.get("rec_scores", []) if isinstance(response, dict) else []
        if not isinstance(texts, (list, tuple)):
            continue
        for index, text in enumerate(texts):
            normalized_text = str(text).strip()
            if not normalized_text:
                continue
            score = scores[index] if isinstance(scores, (list, tuple)) and index < len(scores) else None
            lines.append(OCRLine(text=normalized_text, score=_as_float(score)))
    return lines


def _result_to_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    json_value = getattr(result, "json", None)
    if callable(json_value):
        json_value = json_value()
    if isinstance(json_value, str):
        parsed = json.loads(json_value)
        if isinstance(parsed, dict):
            return parsed
    if isinstance(json_value, dict):
        return json_value
    to_dict = getattr(result, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        if isinstance(value, dict):
            return value
    raise TypeError("unexpected PaddleOCR result type")


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    import uvicorn

    bind_host = os.getenv("PADDLE_OCR_HOST", "127.0.0.1")
    if bind_host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("Paddle tutorial is local-only; PADDLE_OCR_HOST must be loopback")
    uvicorn.run(
        app,
        host=bind_host,
        port=int(os.getenv("PADDLE_OCR_PORT", "8100")),
        reload=False,
    )
