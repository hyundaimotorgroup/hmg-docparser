"""Loopback layout service for ByteDance/Dolphin-1.5.

Inference follows the Dolphin 1.5 upstream VisionEncoderDecoderModel demo.
The parser uses only the model's page layout stage.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel, Field
import truststore

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.services.http_limits import RequestLimitsMiddleware
from core.services.input_limits import InputTooLarge, configured_limit, decode_base64, decode_rgb_image

# Use the system CA store for Hugging Face downloads. Avoid the optional Xet
# transfer client so organization certificates also apply to model weights.

MODEL_ID = os.getenv("DOLPHIN_15_MODEL", "ByteDance/Dolphin-1.5")
INSTANCE_ID = os.getenv("DOLPHIN_15_INSTANCE_ID", "manual")
MAX_LENGTH = int(os.getenv("DOLPHIN_15_MAX_LENGTH", "4096"))
MAX_IMAGE_BYTES = configured_limit("DOLPHIN_15_MAX_IMAGE_BYTES", 64 * 1024 * 1024)
MAX_IMAGE_PIXELS = configured_limit("DOLPHIN_15_MAX_IMAGE_PIXELS", 128_000_000)
MAX_PROMPT_CHARS = configured_limit("DOLPHIN_15_MAX_PROMPT_CHARS", 65_536)


class LayoutRequest(BaseModel):
    image_base64: str = Field(min_length=1)
    prompt: str = "Parse the reading order of this document."


class LayoutResponse(BaseModel):
    layout_text: str


class LayoutService:
    def __init__(self) -> None:
        import torch
        import transformers
        from transformers import AutoProcessor, VisionEncoderDecoderModel

        if MAX_LENGTH < 1:
            raise ValueError("DOLPHIN_15_MAX_LENGTH must be positive")
        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(MODEL_ID)
        self.model = VisionEncoderDecoderModel.from_pretrained(MODEL_ID)
        requested_device = os.getenv("DOLPHIN_15_DEVICE", "auto").lower()
        if requested_device not in {"auto", "cpu", "cuda"}:
            raise ValueError("DOLPHIN_15_DEVICE must be auto, cpu, or cuda")
        self.device = ("cuda" if torch.cuda.is_available() else "cpu") if requested_device == "auto" else requested_device
        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is unavailable")
        self.model.to(self.device)
        self.model = self.model.half() if self.device == "cuda" else self.model.float()
        self.model.eval()
        self.tokenizer = self.processor.tokenizer
        self._lock = threading.Lock()
        self.model_provenance = {
            "requested_model": MODEL_ID,
            "resolved_revision": getattr(self.model.config, "_commit_hash", None),
            "device": self.device,
            "torch_version": torch.__version__,
            "transformers_version": transformers.__version__,
            "max_length": MAX_LENGTH,
        }
        print("DOLPHIN_MODEL_PROVENANCE=" + json.dumps(self.model_provenance, sort_keys=True), flush=True)

    def infer(self, image: Image.Image, prompt: str) -> str:
        formatted_prompt = f"<s>{prompt} <Answer/>"
        with self._lock, self.torch.inference_mode():
            pixels = self.processor(image, return_tensors="pt").pixel_values
            pixels = pixels.to(device=self.device, dtype=next(self.model.parameters()).dtype)
            tokens = self.tokenizer(formatted_prompt, add_special_tokens=False, return_tensors="pt")
            outputs = self.model.generate(
                pixel_values=pixels,
                decoder_input_ids=tokens.input_ids.to(self.device),
                decoder_attention_mask=tokens.attention_mask.to(self.device),
                min_length=1,
                max_length=MAX_LENGTH,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                use_cache=True,
                bad_words_ids=[[self.tokenizer.unk_token_id]],
                return_dict_in_generate=True,
                do_sample=False,
                num_beams=2,
            )
            sequence = self.tokenizer.decode(outputs.sequences[0], skip_special_tokens=False)
        return sequence.replace(formatted_prompt, "").replace("<pad>", "").replace("</s>", "").strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    truststore.inject_into_ssl()
    app.state.service = LayoutService()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    RequestLimitsMiddleware, paths={"/v1/layout"},
    max_request_bytes=configured_limit("DOLPHIN_15_MAX_REQUEST_BYTES", 128 * 1024 * 1024),
    max_concurrent_requests=configured_limit("DOLPHIN_15_MAX_CONCURRENT_REQUESTS", 8),
    max_queued_requests=configured_limit("DOLPHIN_15_MAX_QUEUED_REQUESTS", 64),
    read_timeout_seconds=configured_limit("DOLPHIN_15_READ_TIMEOUT_SECONDS", 900),
)


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {"status": "ok", "instance_id": INSTANCE_ID, "model": app.state.service.model_provenance}


@app.post("/v1/layout", response_model=LayoutResponse)
def layout(request: LayoutRequest) -> LayoutResponse:
    if MAX_PROMPT_CHARS and len(request.prompt) > MAX_PROMPT_CHARS:
        raise HTTPException(status_code=413, detail="prompt exceeds the configured character limit")
    try:
        raw = decode_base64(request.image_base64, MAX_IMAGE_BYTES)
        image = decode_rgb_image(raw, MAX_IMAGE_PIXELS)
    except InputTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except (OSError, ValueError, SyntaxError) as exc:
        raise HTTPException(status_code=400, detail="invalid image") from exc
    try:
        text = app.state.service.infer(image, request.prompt)
    finally:
        image.close()
    if not text:
        raise HTTPException(status_code=502, detail="model returned empty layout")
    return LayoutResponse(layout_text=text)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("DOLPHIN_15_PORT", "8200")))
