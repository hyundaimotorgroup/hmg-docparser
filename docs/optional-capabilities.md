# Optional local capabilities

The primary `default.yaml` requires the router as a separate process.
The CLI does not start servers automatically; local_quickstart requires the router.
Editor, telemetry and Confluence remain separately selected capabilities.

## Optional local router

The primary [CLI setup](installation.md) needs a separately started router. The router
is a FastAPI process for all five PDF profiles. It serves three local image classifiers to the
parser on loopback. It is not a hosted API or a network deployment recipe.
Those profiles also need their configured layout, OCR, and LLM/VLM endpoints;
starting the router alone does not make them runnable. See
[providers](providers.md) and [configuration](configuration.md).

### Checkpoints and requirements

From the repository root, install the unified dependencies, then check the
router checkpoints when using a router profile:

```bash
python -m pip install -r requirements.txt
python tools/serve_router.py --check
```

The server loads three EfficientNet B0 checkpoints. By default it looks for
`models/router/binary_router.pth`, `models/router/second_stage_fig.pth`, and
`models/router/second_stage_tab.pth`. To use files you already have locally,
set `ROUTER_BINARY_CHECKPOINT`, `ROUTER_FIG_CHECKPOINT`, and
`ROUTER_TAB_CHECKPOINT` to their paths. `--check` verifies that the files
exist; it does not validate their contents, license, or checksum. Startup
loads them with PyTorch and fails if they are incompatible. Keep checkpoint
files in a trusted local location. The bundled router weights are [Apache-2.0 licensed](../models/router/README.md), including commercial use, modification, and redistribution. CPU is the default device;
`ROUTER_DEVICE` can select a device available to the local PyTorch install.
The three checkpoint paths are bundled in this source tree. Their source,
permission status, and SHA-256 are listed in [model/data assets](model-and-data-assets.md).
File presence or successful inference does not establish redistribution rights.
Memory and accelerator needs still require candidate-specific measurement.

### Local run

After `--check` succeeds, start the server in one terminal:

```bash
python tools/serve_router.py
```

It listens on `127.0.0.1:8001` by default. Only `127.0.0.1`, `::1`, and
`localhost` are accepted for `--host`; an external bind is rejected. In a
second terminal, set `ROUTER_SERVER_URL=http://127.0.0.1:8001` in your private
`.env` or shell, then select a router profile explicitly:

```bash
python main.py configs/local_quickstart.yaml
```

`configs/default.yaml` is the primary router profile and has
additional vision model requirements. Both profiles are separate from the
verified [local quickstart](providers.md#local-dolphin-and-paddle-with-openai). With valid checkpoints, a local
`GET http://127.0.0.1:8001/health` reports the device and loaded models. The
router accepts image uploads at `/stage1/infer` and `/stage2/infer`; keep it
on loopback because these routes have no user authentication. The CLI's
checkpoint check and local health route are diagnostic tools, not evidence
that an end-to-end router profile is validated. Checkpoint redistribution follows
the supplied [LICENSE](../models/router/LICENSE) and [NOTICE](../models/router/NOTICE).

## Local config editor

The optional editor opens a native YAML DAG in a browser and validates it
with the same strict config schema and compiler used by the CLI. It does not
run a pipeline or call model providers. It is a local tool, separate from the
default [parser CLI](installation.md), with no hosted editor service.

From the repository root, after installing `requirements.txt`, start it with:

```bash
python tools/config_editor.py
```

Open `http://127.0.0.1:8765` on the same machine. The entrypoint accepts only
`127.0.0.1` for `--host`; `--port` changes the local port. It uses the base
parser dependencies and has no extra editor requirements.

### Edit and validate

The template menu loads all five PDF profiles: `default`, `local_quickstart`,
`managed_endpoints`, `group_internal` and `beta`. You can import a
YAML file, add or remove nodes, connect or remove edges, edit node IDs and
strict `node_config` fields, choose a document output node, and export YAML.
The UI checks port type and list compatibility while editing. The
**컴파일 검증** (compile validation) button posts the current graph to
`/api/validate`, which checks the native schema,
registry, and compiler and returns an execution order or errors. Validation
does not process files or contact a provider. Import parses YAML and then
validates it. The editor does not persist your graph between page loads; save
an exported `pipeline.yaml` when you need it later. See the
[configuration guide](configuration.md) for the graph contract.

### Secrets and exported files

Secret fields offer an environment reference such as `${API_KEY_NAME}` or
direct entry. A direct value sits in the browser's in-memory graph and is
sent to the loopback server in validation and export requests. The handler
does not write submitted YAML or secrets to an application store or request
log. It builds a response in request memory. Export serializes the full graph
into a downloaded `pipeline.yaml`, including any direct secret values you
entered. Importing a file also sends its full text to the loopback handler.
Use environment references, inspect downloads before sharing or committing,
and close the tab when finished. Browser downloads and any copies you make
remain your responsibility. The editor does not provide secret storage.

Some `${NAME}` references stay literal during editor validation; an actual
CLI run resolves them from the local environment first. A field requiring a
valid HTTPS URL may therefore need a concrete local test value for editor
validation. The optional [Confluence guide](optional-capabilities.md#optional-confluence-upload) explains this
case. Keep credentials out of any test YAML you export.

The Global Context node's `skip_levels` field is a JSON list in the editor.
Default, managed_endpoints and group_internal import `[1]`; use `[]` for the
previous all-page refinement behavior. Import/export and compilation preserve
this setting. It is separate from layout `skip_levels`; see
[configuration](configuration.md#skipping-global-context-on-simple-pages).
Skipped Global Context pages produce no model usage event for Langfuse export.

## Optional Langfuse usage export

The default CLI records LLM usage metadata locally in
`<output_dir>/_llm_usage.jsonl` when it makes LLM calls. External Langfuse
export is off in the current parser profiles. The package is included in the
unified `requirements.txt`; export requires an explicit `langfuse.on: true`
in the chosen YAML. It is not needed for
the [local quickstart](providers.md#local-dolphin-and-paddle-with-openai) or the other default CLI paths.

```bash
python -m pip install -r requirements.txt
```

Put `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` in your
private `.env` or shell environment. `LANGFUSE_TRACE_NAME` is optional and
defaults to `pdf_parser_trace`. The YAML setting is:

```yaml
langfuse:
  on: true
```

All three connection values must be present for export to be usable. The
exporter sends model/provider, API type, token counts, estimated usage and
cached token counts, plus job/node metadata. It does not send prompt text,
model output, or document bodies in the generation payload. A job ID or model
name may still identify a document or provider, so review metadata and the
destination before enabling export. See [privacy and data handling](privacy-and-data-handling.md).

Langfuse import and delivery errors are caught and recorded in local progress
state; the parsing callback continues. The exporter disables further sends
after a generation export error. Flush errors are also ignored by the
pipeline. This is fail-open for parsing, not a guarantee that usage data was
delivered. The local JSONL usage file is independent of the Langfuse option
and contains no prompt or output text. Enabling export can transmit usage
metadata to the configured `LANGFUSE_HOST`; use an approved endpoint and
credentials before a real run.

Langfuse receives model, numeric usage and cost only for complete local costs. Disabled pricing and partial/unpriced costs omit those fields. See [pricing and limitations](llm-inference.md). Background delivery failures may not be detected by the local parser.

## Optional Confluence upload

Confluence upload is a separate, explicitly selected local CLI pipeline. It
is not part of the PDF quickstart or a hosted service. The
[`confluence_upload.yaml`](../configs/optional/confluence_upload.yaml) graph
reads local `.md` or `.markdown` files, then the upload node sends their
Markdown and referenced local attachments to the configured HTTPS Confluence
site. It may create or update pages and alter attachments. Run it only with
credentials, acceptable external write access, and a reviewed target space.

### Local configuration

The YAML reads these values from the process environment or a private `.env`:

| Variable | Use |
| --- | --- |
| `CONFLUENCE_INPUT_PATH` | Local Markdown file or directory. |
| `CONFLUENCE_OUTPUT_DIR` | Local result artifact and final Markdown directory. Use a separate directory from the input. |
| `CONFLUENCE_TOKEN` | Confluence credential. |
| `CONFLUENCE_EMAIL` | Account email for Cloud API-token Basic authentication. Set an empty value only when using a supported Bearer credential; the YAML still requires the variable to exist. |
| `CONFLUENCE_SPACE_ID` | Target space key. |
| `CONFLUENCE_PARENT_ID` | Parent page ID for new pages. |
| `CONFLUENCE_BASE_URL` | Absolute HTTPS site URL, without query or fragment; the client appends `/wiki` if needed. |

The supplied graph has `document_limits.allowed_extensions: [.md, .markdown]`
and a document-scoped Markdown loader feeding `confluence_uploader`. The root
loader omits `depends_on`: the runtime passes it the input `DocumentDTO`.
`__START__` is reserved for a fanout root and fails compilation on this
document-scoped node. The uploader returns a document and writes a local
`<title>_confluence_upload.json` result artifact; its contents may include
page URLs, titles, IDs, and errors. Review it before sharing. A successful
run also writes `<input_stem>.md` under `CONFLUENCE_OUTPUT_DIR`. Existing
`<input_stem>.md` output causes that input to be skipped on a later run.

After reviewing the Markdown, target, and write permissions, an authorized
operator can invoke the separate pipeline from the repository root:

```bash
python main.py configs/optional/confluence_upload.yaml
```

The YAML passes `CONFLUENCE_EMAIL` to the client. A nonempty email selects
Basic authentication with email and token; an empty email selects Bearer.
Cloud API tokens need the account email. Omitting it caused HTTP 403 in the
development run; using the matching email fixed authentication. The current
client appends `/wiki` and was verified against Confluence Cloud; alternate
deployment paths and token contracts are not established by this run.

TLS verification stays enabled. If Requests cannot trust a site's certificate
chain, set `REQUESTS_CA_BUNDLE` in the private `.env` to an absolute path to a
trusted PEM CA bundle. The recorded macOS run used the system certificates in
that bundle; `verify=False` was not used. Keep the bundle available while its
path is configured, and refresh it when the local certificate environment changes.

Existing pages are updated
by default, and attachments may be deleted and uploaded again. The supplied
YAML leaves `update_existing` at its code default (`true`). Set
`update_existing: false` in `node_config` for a new-page run that fails on a
duplicate title. This operation
requires a real Confluence credential and external write approval; a config
compile or local loader smoke is not an upload test.

The authorized development upload on 2026-10-23 used the normal uploader and
client in the fresh Python 3.12 parser environment, with `update_existing: false`.
It created one page from the nine-page default result and uploaded 38 attachments
(1,043,256 bytes), with no warnings, updates, or deletes. Read-back confirmed
the title, space, parent, body text, four tables and 38 image references; every
downloaded attachment matched its original size and SHA-256. This covers the
uploader/client path, not a separate end-to-end run of the Markdown CLI graph.

The config editor validates raw YAML without expanding `${NAME}` references.
For this YAML, its `base_url` field requires a concrete HTTPS value, so raw
editor validation fails on `${CONFLUENCE_BASE_URL}`. The CLI first resolves
environment references and then validates the graph. A safe offline check can
load the YAML with example environment values and compile it without running
the upload node; do not put real tokens into shared YAML or evidence files.

## Validation and release checks

| Capability | Recorded scope and remaining checks |
| --- | --- |
| Router | Local inference/health depends on trusted files; Apache-2.0 and copyright notices accompany the weights; checksums, candidate profile runs, and resource sizing are release checks. |
| Config editor | Local graph validation and HTTP contracts; verify candidate UI links/loopback behavior. It does not run a parser. |
| Langfuse | Exporter error handling is described above; actual delivery to an authorized destination remains unverified. |
| Confluence | Development create/attachment client path was verified. Existing-page update, attachment replacement, alternate deployments, and a full Markdown CLI run are separate checks. |

Use [data handling](privacy-and-data-handling.md) for credentials/retention,
[model/data assets](model-and-data-assets.md) for weights/fixtures, and
[release checks](release-checklist.md) for candidate evidence. HTTP body/image/
queue limits are documented in [HTTP input limits](http-input-limits.md).


Start the required local router using [quickstart](quickstart.md). Project-maintained capabilities load from internal resources. Advanced operator extensions use `configs/optional/model_capabilities.example.yaml` and the [LLM guide](llm-inference.md); they are not auto-loaded.


`configs/beta.yaml` is a block-context profile under performance validation. It requires group_internal model/router/layout/OCR connections. See [configuration](configuration.md#beta-profile-under-performance-validation) for role, cost and fallback contracts.
