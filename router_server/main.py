"""Local-only FastAPI application for router model inference.

This package intentionally has no public deployment configuration. Run it through
``python tools/serve_router.py``; that entrypoint only permits loopback binding.
"""

from __future__ import annotations

import os

import torch
import torch.nn as nn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image
from torchvision import models, transforms

from router_server.settings import checkpoint_paths
from core.services.http_limits import RequestLimitsMiddleware
from core.services.input_limits import InputTooLarge, configured_limit, decode_rgb_image

MAX_IMAGE_BYTES = configured_limit("ROUTER_MAX_IMAGE_BYTES", 64 * 1024 * 1024)
MAX_IMAGES = configured_limit("ROUTER_MAX_IMAGES", 128)
MAX_IMAGE_PIXELS = configured_limit("ROUTER_MAX_IMAGE_PIXELS", 128_000_000)
MAX_BATCH_PIXELS = configured_limit("ROUTER_MAX_BATCH_PIXELS", 256_000_000)


DEVICE = torch.device(os.getenv("ROUTER_DEVICE", "cpu"))
_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])
_MODELS: dict[str, nn.Module] = {}


def _load_model(checkpoint: str, device: torch.device) -> nn.Module:
    model = models.efficientnet_b0(weights=None)
    state = torch.load(checkpoint, map_location=device)
    state_dict = state["model"]
    num_classes = state_dict[next(key for key in reversed(state_dict) if "weight" in key)].shape[0]
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
    model.load_state_dict(state_dict)
    return model.eval().to(device)


def _classify_batch(images: list[Image.Image], model: nn.Module, device: torch.device) -> list[int]:
    tensors = torch.stack([_TRANSFORM(image.convert("RGB")) for image in images]).to(device)
    with torch.no_grad():
        logits = model(tensors)
    return [int(value) for value in logits.argmax(1).tolist()]


async def _load_images(images: list[UploadFile]) -> list[Image.Image]:
    if not images:
        raise HTTPException(status_code=400, detail="images field must not be empty")
    if MAX_IMAGES and len(images) > MAX_IMAGES:
        raise HTTPException(status_code=413, detail="image count exceeds the configured limit")
    result: list[Image.Image] = []
    pixels = 0
    try:
        for upload in images:
            content = bytearray()
            while chunk := await upload.read(1024 * 1024):
                if MAX_IMAGE_BYTES and len(content) + len(chunk) > MAX_IMAGE_BYTES:
                    raise InputTooLarge("image bytes exceed the configured limit")
                content.extend(chunk)
            remaining = MAX_BATCH_PIXELS - pixels if MAX_BATCH_PIXELS else 0
            if MAX_BATCH_PIXELS and remaining <= 0:
                raise InputTooLarge("batch pixels exceed the configured limit")
            budgets = [limit for limit in (MAX_IMAGE_PIXELS, remaining) if limit]
            image = await run_in_threadpool(decode_rgb_image, bytes(content), min(budgets) if budgets else 0)
            result.append(image)
            pixels += image.width * image.height
    except BaseException as exc:
        for image in result:
            image.close()
        if isinstance(exc, InputTooLarge):
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        if isinstance(exc, (OSError, ValueError, SyntaxError)):
            raise HTTPException(status_code=400, detail="each upload must be a readable image") from exc
        raise
    return result


def create_app() -> FastAPI:
    app = FastAPI(title="Local router server", docs_url=None, redoc_url=None)
    app.add_middleware(
        RequestLimitsMiddleware, paths={"/stage1/infer", "/stage2/infer"},
        max_request_bytes=configured_limit("ROUTER_MAX_REQUEST_BYTES", 512 * 1024 * 1024),
        max_concurrent_requests=configured_limit("ROUTER_MAX_CONCURRENT_REQUESTS", 8),
        max_queued_requests=configured_limit("ROUTER_MAX_QUEUED_REQUESTS", 64),
        read_timeout_seconds=configured_limit("ROUTER_READ_TIMEOUT_SECONDS", 900),
    )

    @app.on_event("startup")
    def load_models() -> None:
        _MODELS.clear()
        for name, checkpoint in checkpoint_paths().items():
            if not checkpoint.is_file():
                raise RuntimeError(f"router checkpoint is missing: {checkpoint}")
            _MODELS[name] = _load_model(str(checkpoint), DEVICE)

    @app.get("/health")
    def health() -> dict[str, object]:
        payload = {"status": "ok", "device": str(DEVICE), "models_loaded": list(_MODELS)}
        if os.getenv("ROUTER_INSTANCE_ID"):
            payload["instance_id"] = os.environ["ROUTER_INSTANCE_ID"]
        return payload

    @app.post("/stage1/infer")
    async def infer_stage1(images: list[UploadFile] = File(...)) -> dict[str, list[int]]:
        pil_images = await _load_images(images)
        try:
            predictions = await run_in_threadpool(_classify_batch, pil_images, _MODELS["binary"], DEVICE)
        finally:
            for image in pil_images:
                image.close()
        return {"levels": [prediction + 1 for prediction in predictions]}

    @app.post("/stage2/infer")
    async def infer_stage2(
        type: str = Form(...),
        images: list[UploadFile] = File(...),
    ) -> dict[str, list[int]]:
        block_type = type.strip().lower()
        if block_type not in {"fig", "tab"}:
            raise HTTPException(status_code=400, detail="type must be 'fig' or 'tab'")
        pil_images = await _load_images(images)
        offset = 1 if block_type == "fig" else 2
        try:
            predictions = await run_in_threadpool(_classify_batch, pil_images, _MODELS[block_type], DEVICE)
        finally:
            for image in pil_images:
                image.close()
        return {"levels": [prediction + offset for prediction in predictions]}

    return app


app = create_app()
