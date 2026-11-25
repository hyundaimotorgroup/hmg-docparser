# Quickstart: start services and parse a PDF

[kor](kor/quickstart.md)

For environment setup, see [installation](installation.md). The
[recommended model combination and Dolphin v2 hardware](../README.md#recommended-settings)
describe the target setup; the examples below follow the supplied YAML defaults.

This guide assumes your Python environments, dependencies, model files, router
checkpoints, and provider access are already configured. Run every command from
the repository root. Activate the appropriate existing environment in each
terminal before starting its app. Conda environment names below are examples;
replace them with your own names or environment paths.

The parser CLI does not start provider servers. Keep each required server
running in its own terminal until parsing finishes.

## Choose the pipeline

| Config | Apps to start on your machine | Other services that must be available | Default output directory |
| --- | --- | --- | --- |
| `configs/local_quickstart.yaml` | Router, Dolphin 1.5 FastAPI, Paddle OCR FastAPI, parser CLI | OpenAI-compatible text/vision API | `tmp/local_quickstart` |
| `configs/default.yaml` | Router, parser CLI | Dolphin v2, Paddle Triton, OpenAI-compatible vision API | `tmp/default` |
| `configs/managed_endpoints.yaml` | Router, parser CLI | Your running Dolphin v2/vLLM, Paddle Triton, and OpenAI-compatible vision services | `tmp/managed_endpoints` |
| `configs/group_internal.yaml` | Router, parser CLI | Private Dolphin v2, Paddle Triton, and internal vision API | `tmp/group_internal` |
| `configs/beta.yaml` | Router and parser CLI; group/internal extraction endpoints | Internal Luna/OpenAI and Flash/Gemini; under performance validation | `tmp/beta` |

Start operator-managed services using your existing deployment commands. This
repository provides local Dolphin 1.5 and Paddle FastAPI entrypoints, plus the
router entrypoint. The v2/vLLM and Triton contracts are in the
[provider guide](providers.md#self-managed-model-endpoints).

## Fill in `.env`

Edit the repository-root `.env`, using [`.env.example`](../.env.example) as a
reference. Fill only the values for your selected profile; add variables shown
below if they are absent from the example. Keep credentials in `.env`.

The parser reads `.env` automatically when loading YAML `${NAME}` references.
Already exported shell variables take precedence over `.env`. The standalone
router, Dolphin, and Paddle entrypoints read their options from the process
environment, so set their options inline or with `export` in the server terminal.
You do not need to `source .env`.

### Local Dolphin 1.5 + Paddle FastAPI

For `configs/local_quickstart.yaml`:

```dotenv
LOCAL_DOLPHIN_URL=http://127.0.0.1:8200
LOCAL_PADDLE_URL=http://127.0.0.1:8100

LOCAL_LLM_BASE_URL=https://api.openai.com/v1
LOCAL_LLM_API_KEY=replace-with-your-api-key
LOCAL_LIGHT_VLM_MODEL=gpt-6-luna
LOCAL_MEDIUM_VLM_MODEL=gpt-6-luna
LOCAL_HEAVY_VLM_MODEL=gpt-6.1-sol
```

Light handles L1 whole pages and L2 elements, medium handles L3 elements, and heavy handles L2 global-context. All must support images and structured responses. Native-text L1 bypasses whole-page/global-context calls. Also set `ROUTER_SERVER_URL=http://127.0.0.1:8001`.

### Router + Dolphin v2 + Paddle Triton

For `default` or `managed_endpoints`, use:

```dotenv
ROUTER_SERVER_URL=http://127.0.0.1:8001
DOLPHIN_SERVER_URL=http://127.0.0.1:8000/v1
DOLPHIN_MODEL=dolphinv2
PADDLE_SERVER_URL=127.0.0.1:8002
PADDLE_MODEL=paddle
PADDLE_TOKEN=

LOCAL_LLM_BASE_URL=https://api.openai.com/v1
LOCAL_LLM_API_KEY=replace-with-your-api-key
LOCAL_LLM_MODEL=gpt-6-luna
LOCAL_LIGHT_VLM_MODEL=gpt-6-luna
LOCAL_MEDIUM_VLM_MODEL=gpt-6-luna
LOCAL_HEAVY_VLM_MODEL=gpt-6.1-sol
```

Replace the Dolphin/Paddle addresses and model IDs with those of your running
services. `DOLPHIN_SERVER_URL` includes the OpenAI-compatible `/v1` base path;
`PADDLE_SERVER_URL` is Triton `host:port`, without a URL scheme. Set
`PADDLE_TOKEN` if the service requires bearer authentication.

Match OCR TLS to your Triton endpoint. Default, managed_endpoints and
group_internal use `${PADDLE_SSL:-true}`: set `PADDLE_SSL=false` in `.env`
for the example plain-HTTP Paddle address above. See
[endpoint contracts](providers.md#paddle-ocr-through-triton).

`default` and `managed_endpoints` use the heavy model for global-context vision
on pages outside `skip_levels: [1]`;
Choose image-capable models for all VLM roles.

Default, local_quickstart, managed_endpoints and group_internal skip only the additional Global
Context request on Stage 1 L1 pages. Existing light VLM calls for pages with
images or no native text remain. Keep the configured heavy model and credentials
for other pages. Set `global_context_page.node_config.skip_levels: []` to restore
all-page refinement; see [the policy](configuration.md#skipping-global-context-on-simple-pages).
Use a new output directory when comparing policies: an existing final Markdown
causes that input to be skipped.

### Group/internal API

For `configs/group_internal.yaml`, fill the same router/Dolphin/Paddle
connection variables above, then use this API block:

```dotenv
LLM_INTERNAL_API_BASE_URL=https://your-internal-api.example
LLM_INTERNAL_API_KEY=replace-with-your-internal-api-key
LLM_INTERNAL_API_PROJECT_ID=
LLM_INTERNAL_API_LIGHT_VLM_MODEL=gpt-6-luna
LLM_INTERNAL_API_MEDIUM_VLM_MODEL=gemini-3.8-flash
LLM_INTERNAL_API_HEAVY_VLM_MODEL=gemini-3.8-flash
```

Use the base URL, model IDs, and project ID supplied for your internal service.
The project ID may be empty if your service does not require it. This profile
uses the internal API credentials for vision calls. Its light tier uses
`api_type: openai`; medium/heavy tiers use `api_type: gemini`. The Paddle OCR
node defaults to `ssl: true`; adjust it if your endpoint uses plain HTTP.

## Run the local FastAPI profile

This is the manual execution path corresponding to
[`verify_local_quickstart_clean_conda.sh`](../scripts/verify_local_quickstart_clean_conda.sh),
using your existing environments. Start the router and both model servers before the parser.

### Terminal 1: Dolphin 1.5

```bash
conda activate dolphin-15
DOLPHIN_15_DEVICE=cpu DOLPHIN_15_PORT=8200 \
  python tutorial/dolphin_15_fastapi/server.py
```

This uses the verification script's CPU mode. For an already configured CUDA
environment, use `DOLPHIN_15_DEVICE=cuda`. The default model is
`ByteDance/Dolphin-1.5`; to use a local model directory, export
`DOLPHIN_15_MODEL=/absolute/path/to/model` before starting. The server binds to
`127.0.0.1`. If you change its port, update `LOCAL_DOLPHIN_URL` in `.env` too.

### Terminal 2: Paddle OCR

```bash
conda activate paddle-ocr-cpu
PADDLE_OCR_DEVICE=cpu PADDLE_OCR_HOST=127.0.0.1 PADDLE_OCR_PORT=8100 \
  PADDLE_PDX_LOCAL_FONT_FILE_PATH=/System/Library/Fonts/AppleSDGothicNeo.ttc \
  python tutorial/paddle_ocr_fastapi/server.py
```

The font path above is for macOS. On Linux, replace it with an installed TTF/TTC,
for example `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`. This supplies
PaddleX's visualization font locally. If you change the port, update
`LOCAL_PADDLE_URL` in `.env` too.

Both servers may download models on first startup. Wait for initialization and
successful health responses before running the parser; CPU startup/inference
can take several minutes. Details are in the
[Dolphin tutorial](../tutorial/dolphin_15_fastapi/README.md) and
[Paddle tutorial](../tutorial/paddle_ocr_fastapi/README.md).

### Terminal 3: router

```bash
conda activate pdf-parser
python tools/serve_router.py --check && \
  ROUTER_DEVICE=cpu python tools/serve_router.py --host 127.0.0.1 --port 8001
```

### Terminal 4: health checks and parser

First, set `input_dir` in `configs/local_quickstart.yaml` to an existing PDF and
choose `output_dir`. The default sample at
`inputs/smoke/mixed_source_9p.pdf` is Git-ignored and may be absent from
your checkout.

```bash
conda activate pdf-parser
curl --fail --noproxy '*' http://127.0.0.1:8001/health && \
  curl --fail --noproxy '*' http://127.0.0.1:8200/healthz && \
  curl --fail --noproxy '*' http://127.0.0.1:8100/healthz && \
  python main.py configs/local_quickstart.yaml
```

All three health responses should contain `status: ok`. Adjust the health URLs
if you changed the ports. The CLI accepts a config path; set the PDF path in
the YAML rather than passing a second CLI argument.

## Run a router profile

Ensure the configured Dolphin v2, Paddle Triton, and LLM/VLM services are
available, and fill the appropriate `.env` block above. These profiles use
Dolphin v2 and Triton transports; the local FastAPI servers in the previous
section cannot satisfy those contracts by changing only endpoint URLs.

### Terminal 1: router

Activate your existing environment with the router dependencies, then run:

```bash
python tools/serve_router.py --check && \
  python tools/serve_router.py --host 127.0.0.1 --port 8001
```

The router defaults to CPU and loads these checkpoints:

| Model | Default checkpoint | Optional shell override |
| --- | --- | --- |
| Stage 1 | `models/router/binary_router.pth` | `ROUTER_BINARY_CHECKPOINT` |
| Stage 2 figures | `models/router/second_stage_fig.pth` | `ROUTER_FIG_CHECKPOINT` |
| Stage 2 tables | `models/router/second_stage_tab.pth` | `ROUTER_TAB_CHECKPOINT` |

If needed, export checkpoint paths and `ROUTER_DEVICE` in this terminal before
running either command. `--check` checks file presence; server startup loads
the models. Keep the server running after `Application startup complete`.
If you change `--port`, update `ROUTER_SERVER_URL` in `.env`.

### Terminal 2: parser

Set `input_dir` and `output_dir` in your chosen YAML, activate the parser
environment, then select **one** profile:

```bash
conda activate pdf-parser
curl --fail --noproxy '*' http://127.0.0.1:8001/health && \
  python main.py configs/group_internal.yaml
```

Replace the config argument with `configs/default.yaml`,
`configs/managed_endpoints.yaml` as needed.
Always pass the config explicitly: bare `python main.py` selects `default`.
The router health response should report `status: ok` and three loaded models;
it only checks the router. Check your other provider services separately.

## Inspect output and stop services

The final document is saved as `<output_dir>/<input-PDF-stem>.md`. For the
local profile's default input/output paths:

```bash
ls -lh tmp/local_quickstart/*.md
```

For the internal profile, use `ls -lh tmp/group_internal/*.md`, or substitute
your configured output directory. Open the final Markdown and check that it is
nonempty and contains no `[Error]` markers. A successful CLI exit alone does
not establish that every node succeeded. Compare text, tables, and images with
the PDF; see [outputs and failures](outputs-and-failures.md).

After parsing, press `Ctrl+C` in each server terminal to stop the apps you
started. The manual commands leave them running until you stop them.

## Optional: repeat the clean-environment verification

Use this only when you want to recreate the verification rather than reuse
your prepared environments:

```bash
bash scripts/verify_local_quickstart_clean_conda.sh \
  configs/local_quickstart.yaml /absolute/path/to/input.pdf
```

The script creates fresh isolated Conda environments (parser/Dolphin Python
3.12, Paddle Python 3.11), starts the needed local CPU providers, runs the CLI,
and checks the final Markdown. It stops its own processes on exit and retains
logs, environment records, the generated YAML, and output under
`tmp/clean_conda_local_quickstart/<run-id>/`. `.env` must already contain the
LLM/VLM credentials. Use unused ports; the script overrides its local provider
URLs, with ports controlled by `DOLPHIN_15_PORT` and `PADDLE_OCR_PORT`.
Run `bash scripts/verify_local_quickstart_clean_conda.sh --help` for its options.
The script also accepts `sh` invocation and automatically enables Bash syntax.

## Model and sample conditions

Use your own authorized PDF when the configured development fixture is absent.
See [model/data assets](model-and-data-assets.md) for bundled-file rights and
[data handling](privacy-and-data-handling.md) for transfers and retained artifacts.
For commercial layout use, PP-DocLayoutV3 is recommended; the supplied router
profiles use Dolphin v2 under its separate research-license conditions and require
a compatible adapter to use PP-DocLayoutV3.

LLM/VLM usage is recorded by default; costs are optional. Shipped profiles do not calculate prices. See [usage and pricing](llm-inference.md) to select operator rates with `pricing_file` or reprice saved records.


`configs/beta.yaml` is a block-context profile under performance validation. It requires group_internal model/router/layout/OCR connections. See [configuration](configuration.md#beta-profile-under-performance-validation) for role, cost and fallback contracts.


Updated graph verification on 2026-11-25: local clean Conda installed fresh parser/router 3.12, Dolphin 3.12 and Paddle 3.11 environments and completed mixed_source_9p: 9 pages, 9 Stage 1 and 9 Stage 2 page records, 35 classified elements and 35 actual LLM/VLM requests. Default completed the same PDF with 16 classified elements and 17 model requests. Both preserved native text on pages 6–8 with zero model requests, no missing/duplicate/error pages, and owned-router cleanup. Different Dolphin versions/providers can produce different request counts and Markdown. Beta performance evaluation is separate.
