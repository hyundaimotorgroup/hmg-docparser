# Local PaddleOCR FastAPI tutorial

This standalone, loopback-only OCR service does not modify or replace any
parser `core/` adapter. It uses PaddleOCR's public PP-OCRv5 mobile model pair:

- `PP-OCRv5_mobile_det`
- `korean_PP-OCRv5_mobile_rec` (downloaded locally as
  `korean_PP-OCRv5_mobile_rec_infer`)

On first start the service downloads the Korean recognizer from
[`PaddlePaddle/korean_PP-OCRv5_mobile_rec`](https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec)
and its decoder dictionary from PaddleOCR's
[`ppocrv5_korean_dict.txt`](https://github.com/PaddlePaddle/PaddleOCR/blob/main/ppocr/utils/dict/ppocrv5_korean_dict.txt).
They are cached under `tutorial/paddle_ocr_fastapi/.cache/`, which is ignored
by Git. The server binds that dictionary to the local inference configuration;
it must not use the generic `PP-OCRv5_mobile_rec` dictionary, which is
Chinese-oriented and cannot recognize Korean reliably.

## Install (CPU)

Use a separate environment so the Paddle runtime does not affect the parser
environment.

```bash
conda create -n paddle-ocr-cpu python=3.11 -y
conda activate paddle-ocr-cpu
python -m pip install --upgrade pip
python -m pip install paddlepaddle==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install -r tutorial/paddle_ocr_fastapi/requirements.txt
```

The requirements pin PaddleOCR and PaddleX together at 3.1.0. Do not let pip
resolve a newer PaddleX release with this PaddleOCR version: PaddleX 3.7 has
an incompatible predictor-option API.

Validate the Korean PP-OCRv5 model's quality against the target documents
before production use. In particular, its recognition output may omit Korean
word spaces even when they are visible in the source image.

## Fresh-environment smoke test

From the repository root, run the following script. It creates a new Conda
environment named `paddle-ocr-cpu-smoke`, installs the pinned CPU dependencies,
starts the loopback server, submits `paddle_test.png`, validates that text lines
were returned, and stops the server. The first run downloads the models and can
take several minutes.

```bash
bash tutorial/paddle_ocr_fastapi/run_cpu_smoke.sh
```

When its named environment already exists, the script removes that environment
and recreates it so the result remains a fresh-environment check. To use another
name, set `PADDLE_OCR_ENV_NAME`.
It leaves the successful JSON response at
`tutorial/paddle_ocr_fastapi/paddle_test.response.json` and the full server
log at `tutorial/paddle_ocr_fastapi/paddle_test.server.log` (both ignored by
Git).
On success it also prints `PADDLE_OCR_MODEL_PROVENANCE` from the initialized
PaddleX pipeline. Confirm that `requested_detection_model` is
`PP-OCRv5_mobile_det` and `requested_recognition_model` is
`korean_PP-OCRv5_mobile_rec`; when PaddleX exposes them, its local cache paths
are included under `reported_models`.
Each smoke run also uses a unique `instance_id`; it refuses to use a port that
is already serving HTTP, preventing a stale server from being mistaken for the
new v5 process. Choose another unused port if needed:

```bash
PADDLE_OCR_PORT=18101 bash tutorial/paddle_ocr_fastapi/run_cpu_smoke.sh
```
While the models initialize, the script prints the recent server log every 30
seconds so that a download or network problem is visible.

The smoke script prevents PaddleX from downloading its import-time
visualization fonts. On macOS it automatically uses
`/System/Library/Fonts/AppleSDGothicNeo.ttc`; this does not affect OCR model
output. On another platform, set `PADDLE_PDX_LOCAL_FONT_FILE_PATH` to an
installed TTF or TTC before running the script:

```bash
PADDLE_PDX_LOCAL_FONT_FILE_PATH=/path/to/installed-font.ttf \
  bash tutorial/paddle_ocr_fastapi/run_cpu_smoke.sh
```

PaddleX still downloads its OCR models over HTTPS on first startup. The
tutorial uses the operating system trust store so that an organization CA in
the macOS Keychain is trusted. If the CA is supplied as a PEM file instead,
pass its path without disabling TLS verification:

```bash
REQUESTS_CA_BUNDLE=/path/to/organization-ca.pem \
  bash tutorial/paddle_ocr_fastapi/run_cpu_smoke.sh
```

## Start

From the repository root:

```bash
PADDLE_PDX_LOCAL_FONT_FILE_PATH=/System/Library/Fonts/AppleSDGothicNeo.ttc \
  python tutorial/paddle_ocr_fastapi/server.py
```

The server listens on `127.0.0.1:8100` unless `PADDLE_OCR_HOST` or
`PADDLE_OCR_PORT` is explicitly set. On a non-macOS system, replace the font
path above with an installed TTF or TTC.

```bash
curl http://127.0.0.1:8100/healthz
```

## Request contract

`POST /v1/ocr` accepts one base64-encoded image (not a data URL) and returns
recognized text lines and confidence scores.

```bash
IMAGE_B64="$(base64 < crop.png | tr -d '\n')"
curl -X POST http://127.0.0.1:8100/v1/ocr \
  -H 'Content-Type: application/json' \
  -d "{\"image_base64\":\"${IMAGE_B64}\"}"
```

Expected response shape:

```json
{"lines": [{"text": "Example", "score": 0.98}]}
```

The service accepts images up to 64 MiB after base64 decoding by default.
See [configurable HTTP input limits](../../docs/http-input-limits.md) for request,
pixel, and queue limits. It does not
write request images to disk and does not expose a non-loopback host by
default.

`PADDLE_OCR_HOST` accepts only `127.0.0.1`, `::1`, or `localhost`.

## Licenses and shared samples

Review [model/data assets](../../docs/model-and-data-assets.md),
[third-party notices](../../THIRD_PARTY_NOTICES), and
[HTTP input limits](../../docs/http-input-limits.md). Record model revisions and
applicable licenses before repackaging models or dictionaries. The bundled smoke
image has a separate rights record; use an authorized sample when sharing results.
See [data handling](../../docs/privacy-and-data-handling.md) for downloads, caches,
outputs, and provider transfers in a full parser run.


For the full [local quickstart](../../docs/quickstart.md), also start the CPU router in the parser environment. Local keeps Dolphin 1.5/Paddle FastAPI with concurrency 2 and uses the same 15-node graph as default; earlier model-only or three-page runs do not validate the updated full graph.
