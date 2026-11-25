# Local Dolphin 1.5 layout server

This tutorial runs the layout stage of
[`ByteDance/Dolphin-1.5`](https://huggingface.co/ByteDance/Dolphin-1.5)
on your own machine and exposes a loopback API for `configs/local_quickstart.yaml`.
Its model loading and generation settings follow the
[Dolphin 1.5 upstream demo](https://github.com/bytedance/Dolphin/blob/b6c7978ffd/demo_page.py).
The server returns the raw reading-order layout string; the parser maps its
896-space boxes to PDF page coordinates.

## Hardware and software

For an initial **Dolphin-only** Linux/NVIDIA setup, budget at least 8 GiB of
GPU VRAM, 16 GiB of system RAM, and 10 GiB of free disk. These are conservative
planning values, **not measured minimums**. The upstream model is about 0.3B
parameters and its published inference demo uses CUDA half precision or CPU
float precision. The local LLM and vision model require additional memory;
size their servers independently. Python 3.11 and a CUDA 12.1-compatible
NVIDIA driver are the documented starting platform. Check `nvidia-smi` and
your installed PyTorch CUDA runtime before starting. CPU model inference may
be slow. The recorded macOS arm64 CPU server was used successfully in
three local_quickstart parser runs; this does not establish Linux/NVIDIA support.

## Install and start

### Fresh CPU smoke (real model)

From the repository root, run:

```bash
bash tutorial/dolphin_15_fastapi/run_cpu_smoke.sh
```

The script creates a fresh, dedicated Python 3.12 environment with `uv`,
installs CPU PyTorch and the pinned tutorial dependencies, downloads Dolphin
1.5 on first use, renders page 1 of the approved sample PDF, starts the
loopback FastAPI server, and sends that page to `POST /v1/layout`. It requires
`uv`, `curl`, network access for the initial packages/model, and enough RAM and
disk for the model. CPU inference can be slow. If the default port is occupied,
set `DOLPHIN_15_PORT=18201` before the command.

Evidence remains in `tutorial/dolphin_15_fastapi/`:

- `layout_smoke_page.png`: rendered source page;
- `layout_smoke.overlay.png`: returned boxes on a square-padded page for
  visual review;
- `layout_smoke.response.json`: raw layout response (also retained on HTTP
  failure);
- `layout_smoke.server.log`: startup, model provenance, and inference log.

The script checks that the response contains at least one valid Dolphin 1.5
box in 896-space. This is a model/API smoke, not a full parser quickstart.
On 2026-10-20, the macOS arm64 CPU smoke succeeded with 15 parseable boxes
from page 1 of `dp_evalset_general_3p.pdf` (SHA-256
`96e9abc68f717c7b2c3223fce2d757c5e7de6df9698face41d554957958f12b7`).
The downloaded model revision was
`0fe42a93fa2a8f7b537606710ea45ad8b2b0f349`; PyTorch was 2.2.2 and
Transformers was 4.47.0. This establishes a CPU smoke on that machine, not
a minimum RAM requirement or a Linux/NVIDIA result.
The dedicated `.venv-smoke/` directory is replaced on each run and is ignored
by Git. The model cache is reused. `DOLPHIN_15_SMOKE_MAX_LENGTH` changes the
generation cap (default 1024 for the smoke), and `DOLPHIN_15_MODEL` can point
to an already downloaded model directory. `uv` and the model downloader use
the operating system certificate store, so an approved organization CA can be
trusted without disabling certificate verification.

### Manual GPU server

From the repository root, in a dedicated environment:

```bash
conda create -n dolphin-15 python=3.11 -y
conda activate dolphin-15
python -m pip install --upgrade pip
python -m pip install torch==2.1.0 torchvision==0.16.0 --index-url https://download.pytorch.org/whl/cu121
python -m pip install -r tutorial/dolphin_15_fastapi/requirements.txt
python tutorial/dolphin_15_fastapi/server.py
```

The first start downloads the model from Hugging Face to its normal local
cache. To use an already downloaded model directory, set
`DOLPHIN_15_MODEL=/absolute/path/to/model` before starting. The manual
Linux/NVIDIA installation and GPU footprint remain unverified. The separate
macOS CPU local_quickstart parser runs passed; see [provider evidence](../../docs/providers.md#local-dolphin-and-paddle-with-openai).

In another terminal:

```bash
curl --fail http://127.0.0.1:8200/healthz
```

The response contains `status`, a run `instance_id`, and model provenance
including its device, package versions, and resolved model revision when
available. The server listens on
`127.0.0.1:8200` by default. Set `DOLPHIN_15_PORT` to change the port and
also update `LOCAL_DOLPHIN_URL` in `.env`. Do not expose this unauthenticated
tutorial server on an external network.

`POST /v1/layout` accepts JSON with `image_base64` (PNG/JPEG bytes encoded as
standard base64, without a data-URL prefix) and optional `prompt`. It responds
with `{ "layout_text": "..." }`. Requests allow up to 64 MiB decoded image
bytes by default. See [configurable HTTP input limits](../../docs/http-input-limits.md)
for request, pixel, prompt, and queue limits. The parser sends one rendered PDF page at a time, with the prompt
`Parse the reading order of this document.`

## Licenses and shared samples

Review [model/data assets](../../docs/model-and-data-assets.md),
[third-party notices](../../THIRD_PARTY_NOTICES), and
[HTTP input limits](../../docs/http-input-limits.md). Record model revisions and
applicable licenses before repackaging models or dictionaries. The bundled smoke
image has a separate rights record; use an authorized sample when sharing results.
See [data handling](../../docs/privacy-and-data-handling.md) for downloads, caches,
outputs, and provider transfers in a full parser run.


For the full [local quickstart](../../docs/quickstart.md), also start the CPU router in the parser environment. Local keeps Dolphin 1.5/Paddle FastAPI with concurrency 2 and uses the same 15-node graph as default; earlier model-only or three-page runs do not validate the updated full graph.
