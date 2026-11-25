# Provider and endpoint contracts

Default, local_quickstart, managed_endpoints and group_internal share the router/full-vision DAG. Local runs Dolphin 1.5 and Paddle FastAPI; the other profiles retain Dolphin v2/Paddle Triton. Model requests go to the configured providers. Earlier local three-page runs describe the previous graph, not validation of this graph.

| Profile | Layout and OCR | Text and vision | Required `.env` groups | Data sent off the parser process |
| --- | --- | --- | --- | --- |
| `configs/local_quickstart.yaml` | Local Dolphin 1.5 / Paddle FastAPI | OpenAI text and vision | `LOCAL_LLM_API_KEY` | Images go to loopback servers; text and crops go to OpenAI. |
| `configs/default.yaml` | Local router / Dolphin v2 / Paddle Triton | Local LLM API (OpenAI calls) | `DOLPHIN_SERVER_URL`, `PADDLE_SERVER_URL`, `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_API_KEY` | Page images, crops and derived text go to configured endpoints. |
| `configs/managed_endpoints.yaml` | Local router / operator-run vLLM and Triton | Local LLM API (OpenAI calls) | `DOLPHIN_SERVER_URL`, `PADDLE_SERVER_URL`, `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_API_KEY` | Document-derived content goes to operator-supplied endpoints. |
| `configs/group_internal.yaml` | Local router / private Dolphin v2 and Paddle | Internal OpenAI/Gemini vision | `DOLPHIN_SERVER_URL`, `PADDLE_SERVER_URL`, `LLM_INTERNAL_API_BASE_URL`, `LLM_INTERNAL_API_KEY` | Document-derived content goes to private endpoints. |
| `configs/beta.yaml` | Local router / Dolphin v2 / Paddle Triton | Internal role-specific block restoration | Same connection groups as group_internal | Pipeline under performance validation. |

`PADDLE_TOKEN` and optional self-managed chat keys may be empty where the
operator's service does not require them. Provider/model access, charges,
retention, and network permissions depend on the service selected by the user;
review [data handling](privacy-and-data-handling.md) and the selected provider terms
for costs and data transfer before processing sensitive PDFs.

## Capabilities the graph needs

- Layout must return Dolphin reading-order boxes for each rendered PDF page.
  The local FastAPI path calls `POST /v1/layout` with a base64 PNG. The
  self-managed Dolphin v2 path uses a streaming OpenAI-compatible chat
  completion with an image data URL; see the exact
  [endpoint contract](providers.md#dolphin-v2-through-vllm).
- OCR must return text lines with optional confidence scores for text crops.
  The local path calls `POST /v1/ocr`; the self-managed path expects Triton
  `IMAGE_BYTES` input and `OCR_RESULT` output. These transports are not
  interchangeable by changing only the URL.
- Graphs with text merging need a chat model; table and image branches need image
  input. The OpenAI/OpenAI-compatible path uses chat completions and some
  calls request strict JSON-schema output. Select models that support these
  request forms. A healthy endpoint alone does not prove parser compatibility.

`provider: openai` is used by default, managed_endpoints,
and local_quickstart. These profiles share `LOCAL_LLM_BASE_URL` and
`LOCAL_LLM_API_KEY` for every model stage. Only group_internal uses `provider: llm_internal_api`, which maps to the existing private
adapter. The factory also contains Azure, Anthropic, and Gemini adapters, but
these are not verified local quickstart paths. Private
addresses, credentials, and model IDs belong in `.env`, never in shared
examples. See [configuration](configuration.md) for the strict `node_config`
fields and [installation](installation.md) for the parser environment.

## Local Dolphin and Paddle with OpenAI

Use this path for local PDF processing, Dolphin 1.5 layout, and Korean Paddle
OCR, with OpenAI handling text and vision chat requests. The YAML defaults use loopback addresses for the two local servers;
override `LOCAL_DOLPHIN_URL` / `LOCAL_PADDLE_URL` in `.env` when needed.

### 1. Start the model services

1. Follow the [Dolphin 1.5 server tutorial](../tutorial/dolphin_15_fastapi/README.md).
   Its default base URL is `http://127.0.0.1:8200`. The stated 8 GiB GPU VRAM,
   16 GiB RAM, and 10 GiB disk budget covers the **Dolphin server only** and is
   an unmeasured planning floor.
2. Follow the [Korean PP-OCRv5 CPU tutorial](../tutorial/paddle_ocr_fastapi/README.md).
   Its default base URL is `http://127.0.0.1:8100`. The model pair is
   `PP-OCRv5_mobile_det` plus `korean_PP-OCRv5_mobile_rec` with its Korean
   dictionary. Its standalone CPU smoke and the three-page parser run succeeded
   on macOS arm64. Review OCR quality against your own documents.
3. Choose OpenAI text and vision model IDs available to your API key. The
   vision model must accept image inputs. Add both IDs and your API key to
   `.env`. The same multimodal model may serve both roles if it supports the
   parser's structured output requests.

Check the two tutorial health endpoints before running the parser. OpenAI
requests use `https://api.openai.com/v1` by default and require network access.
To use your own local LLM/VLM server, set `LOCAL_LLM_BASE_URL` to its
OpenAI-compatible endpoint. The four non-internal profiles share this URL
and use `provider: openai`.

### 2. Configure and run the parser

Install the parser as shown in the [installation guide](installation.md).
Then, from the repository root:

```bash
cp .env.example .env
# Set LOCAL_LLM_BASE_URL, LOCAL_LLM_API_KEY, and LOCAL_*_VLM_MODEL for your server.
python main.py configs/local_quickstart.yaml
```

`configs/local_quickstart.yaml` sets Dolphin `version: v1` and
`v1_transport: fastapi`, and sets OCR `transport: fastapi`. This is required:
the Paddle tutorial speaks `POST /v1/ocr`, while the original OCR transport
speaks Triton's `/v2/models/.../infer` API. Setting only a different URL in
the Triton config will not work. The local config uses `provider: openai` for
the text and vision stages. Set `LOCAL_LLM_API_KEY`; text and vision share this credential.

The development fixture is `inputs/smoke/dp_evalset_general_3p.pdf`;
public redistribution still awaits asset rights review. Inspect
`tmp/local_quickstart/dp_evalset_general_3p.md` after the run. A fresh Conda
verification on macOS arm64 produced three page sections and no pipeline error
markers. Check Korean word spacing and the source PDF's tables/images before
using the result in production; model output can vary between runs.

### Data boundary

The local tutorial servers bind to `127.0.0.1`. The first model download still
uses external HTTPS. OpenAI receives the text and page crops submitted to
LLM/VLM nodes. `langfuse.on` is false in the config.

## Self-managed model endpoints

This path is for operators who already run vLLM and Triton. You operate the
servers; the parser is a client. Use `configs/managed_endpoints.yaml` and put
your own addresses, model IDs, and credentials in `.env`.

### Dolphin v2 through vLLM

This path uses the [Dolphin v2 research license](https://huggingface.co/ByteDance/Dolphin-v2/blob/main/LICENSE).
Commercial use requires a separate license. For commercial layout use, consider
PP-DocLayoutV3 with a compatible adapter; see [model conditions](model-and-data-assets.md).

Serve the upstream [`ByteDance/Dolphin-v2`](https://huggingface.co/ByteDance/Dolphin-v2)
model through vLLM's OpenAI-compatible server. A starting command, subject to
your vLLM version, GPU, and model support, is:

```bash
vllm serve ByteDance/Dolphin-v2 --served-model-name dolphinv2 --host 127.0.0.1 --port 8000
curl --fail http://127.0.0.1:8000/v1/models
```

The parser's Dolphin v2 adapter sends a streaming `POST /v1/chat/completions`
request with the served model ID, a user message containing a PNG image as a
`data:image/png;base64,...` URL, and the prompt
`Parse the reading order of this document.` The response must stream text
content containing Dolphin v2 layout boxes. Set `DOLPHIN_SERVER_URL` to the
OpenAI-compatible base URL (`http://127.0.0.1:8000/v1` in the command above)
and `DOLPHIN_MODEL=dolphinv2`. This vLLM command is an integration
starting point; its runtime and an end-to-end PDF result are not verified yet.

### Paddle OCR through Triton

Expose a Triton HTTP inference endpoint for your Paddle model. This is the
current parser's Triton wire contract:

| Field | Required value |
| --- | --- |
| Endpoint | Triton HTTP `POST /v2/models/{model_name}/infer` |
| Input | `IMAGE_BYTES`, shape `[1]`, Triton `BYTES`, containing PNG crop bytes |
| Output | `OCR_RESULT`, first element is a JSON string containing `[[text, score], ...]` |
| Model name | Your loaded Triton model ID, set as `PADDLE_MODEL` |
| Address | `PADDLE_SERVER_URL` is `host:port`, without an `http://` prefix |
| TLS and auth | Default/managed/group read `PADDLE_SSL` (`true` by default); set `false` for HTTP, or use a literal YAML `ssl`. `PADDLE_TOKEN` is sent as a bearer token when nonempty. |

Check server readiness with the Triton HTTP health route and the model route,
using your server's actual address and model name:

```bash
curl --fail http://127.0.0.1:8003/v2/health/ready
curl --fail http://127.0.0.1:8003/v2/models/paddle/ready
```

The commands above check Triton routing only; they do not prove that your
Paddle backend returns the required tensor. Verify one inference request with
your own approved image before running a PDF. Leave `PADDLE_TOKEN` empty for
an unauthenticated server; the adapter then omits the bearer header.

The [local Paddle FastAPI tutorial](../tutorial/paddle_ocr_fastapi/README.md)
uses `POST /v1/ocr` and cannot be used as a Triton endpoint. Use the
[fully local config](providers.md#local-dolphin-and-paddle-with-openai) for that tutorial.

### Text and vision chat models

Set `LOCAL_LLM_BASE_URL` and `LOCAL_LLM_API_KEY` in `.env`, plus
`LOCAL_LIGHT_VLM_MODEL`, `LOCAL_MEDIUM_VLM_MODEL`, and
`LOCAL_HEAVY_VLM_MODEL` for your served vision models. Whole-page, table, image and global-context stages
use `POST /v1/chat/completions`; the vision stage must accept image data URLs.
The model operator is responsible for capacity, network access, authentication,
and data retention. The parser writes results under `tmp/managed_endpoints`.

A complete managed-profile provider run has not been verified. Check both
inference and final PDF output using [development](development.md) and
[release validation](release-checklist.md); health alone does not prove compatibility.

## Group and internal setup

This path uses private model services and an internal API endpoint. It is for
users who already have access under their organization's rules; the services
are not offered publicly by this repository.

1. Contact the project maintainer through your approved internal channel.
   Request the Dolphin v2 endpoint/model ID and the Paddle OCR Triton
   endpoint/model ID and token. Request the internal API base URL, project ID,
   LLM/VLM model IDs, and your own API credential through the same approved
   access process. Do not put any of these values in an issue, PR, or example.
2. Install the parser using the [installation guide](installation.md).
3. Copy `.env.example` to `.env` and fill `LLM_INTERNAL_API_*`, `DOLPHIN_SERVER_URL`,
   `PADDLE_SERVER_URL`, and `PADDLE_TOKEN` with the values provided to you. Keep the file private.
4. Run `python main.py configs/group_internal.yaml` from the repository root.

The parser sends page images and crops to the supplied Dolphin/Paddle
endpoints and sends document-derived content to the internal API endpoint.
Check your organization's data handling requirements before using a PDF.
Output goes under `tmp/group_internal`.

## Global Context request policy

Default, managed_endpoints and group_internal set `skip_levels: [1]` on
`global_context_page`. Stage 1 L1 content is retained without an additional
Global Context render/request, including pages already parsed by the light
whole-page VLM. L2 and missing-level pages keep the existing provider/model/API
contract. Credentials and model fields remain required; `[]` restores all
eligible calls. See [configuration](configuration.md#skipping-global-context-on-simple-pages).
This policy does not measure live provider quality or total processing cost.

## Model licenses and validation boundaries

For commercial layout use, [PP-DocLayoutV3](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3)
(Apache-2.0) is recommended instead of Dolphin v2. The supplied profiles use
Dolphin-specific adapters; PP-DocLayoutV3 needs a compatible layout adapter and
is not a drop-in endpoint URL replacement. Dolphin v2 is subject to its
[Qwen research license](https://huggingface.co/ByteDance/Dolphin-v2/blob/main/LICENSE),
with separate licensing required for commercial use. Dolphin 1.5's model card
lists MIT. See [asset conditions](model-and-data-assets.md) and
[third-party notices](../THIRD_PARTY_NOTICES).

| Path | Validation boundary |
| --- | --- |
| Local | Recorded development parsing used local Dolphin/Paddle and a VLM API; fresh candidate/fixture checks remain release tasks. |
| Default | Development provider runs were recorded; verify exact checkpoint and model versions for each candidate. |
| Managed | Compile/contract guidance is available; a separate complete vLLM/Triton/provider run remains unverified. |
| Group/internal | Private access and an authorized full run are required; supplied configuration does not provide service access. |

You are responsible for endpoint access, credentials, cost, and provider data
terms. Select permitted models/data and inspect output rather than inferring
compatibility from health checks. Use [development](development.md) and
[release checks](release-checklist.md) for validation. Security and conduct
reports follow [SECURITY](../.github/SECURITY.md) and
[the Code of Conduct](../.github/CODE_OF_CONDUCT.md), separately from access requests.

## Model assignments

The YAML model defaults reflect these development assignments. Use model
IDs supported by your endpoint and account; a configured name does not grant access.
The stage-to-variable mapping is in [configuration](configuration.md#vlm-roles).

| Prefix | Light / text LLM | Medium | Heavy | Recorded provider verification |
| --- | --- | --- | --- | --- |
| `LLM_INTERNAL_API` | `gpt-6-luna` | `gemini-3.8-flash` | `gemini-3.8-flash` | group_internal only; complete provider run unverified. |
| `LOCAL` | `gpt-6-luna` | `gpt-6-luna` | `gpt-6.1-sol` | Shared by the four non-internal profiles; revised routing verified offline. |

LLM/VLM usage is recorded by default; costs are optional. Shipped profiles do not calculate prices. See [usage and pricing](llm-inference.md) to select operator rates with `pricing_file` or reprice saved records.


`configs/beta.yaml` is a block-context profile under performance validation. It requires group_internal model/router/layout/OCR connections. See [configuration](configuration.md#beta-profile-under-performance-validation) for role, cost and fallback contracts.
