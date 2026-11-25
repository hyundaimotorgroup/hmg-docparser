# Native YAML configuration

Pass a config path to `python main.py`, for example
`python main.py configs/local_quickstart.yaml`. The CLI loads `.env` without
overriding existing shell variables. Whole-value `${NAME}` references require
the variable to exist; an empty value is preserved. `${NAME:-default}` uses
the default when the variable is missing or empty. Defaults can reference
another variable, such as `${VISION_KEY:-${TEXT_KEY}}`.
Keep secrets in your private environment, not in YAML. See
[installation](installation.md) for an offline compiler check.

`.env` and `.env.example` expose the model settings as well as connections.
Default, managed_endpoints, and local_quickstart use
`provider: openai`, sharing `LOCAL_LLM_BASE_URL` and `LOCAL_LLM_API_KEY` for
text and all vision stages. The base URL defaults to `https://api.openai.com/v1`;
set it to your local OpenAI-compatible server when using local inference.
Set `LOCAL_LLM_MODEL`, `LOCAL_LIGHT_VLM_MODEL`, `LOCAL_MEDIUM_VLM_MODEL`, and
`LOCAL_HEAVY_VLM_MODEL` in `.env` to choose the models.

Group_internal and beta use `LLM_INTERNAL_API_BASE_URL`, `LLM_INTERNAL_API_KEY`, optional `LLM_INTERNAL_API_PROJECT_ID`, and `provider: llm_internal_api`. Group tiers use their environment model variables; beta restoration models are fixed by role. All PDF profiles use `ROUTER_SERVER_URL`. Local uses `LOCAL_DOLPHIN_URL`/`LOCAL_PADDLE_URL` FastAPI; default/managed/group/beta use the Dolphin v2/Paddle Triton contracts at `DOLPHIN_SERVER_URL`/`PADDLE_SERVER_URL`.

Default, managed_endpoints and group_internal use `${PADDLE_SSL:-true}` for
Paddle TLS. Set `PADDLE_SSL=false` for HTTP endpoints. SSL environment references
resolve `true`/`false` to strict booleans. The editor preserves these references
and validates their defaults without reading `.env`; the CLI uses the actual
environment value.

## Top-level contract

The schema rejects unknown fields. Paths are interpreted from the process
working directory; run the examples from the repository root.

| Key | Meaning |
| --- | --- |
| `input_dir` | Input file or directory; the scanner considers files directly inside it. PDF profiles accept PDFs; the separate Confluence profile accepts Markdown. |
| `output_dir` | Local Markdown and artifact root. Existing `<stem>.md` files cause matching inputs to be skipped. |
| `document_limits` | Optional `allowed_extensions`, `max_input_mb`, `max_pdf_pages`, `max_zip_members`, `max_zip_uncompressed_mb`, `max_zip_compression_ratio`. Defaults are defined in `core/engine/config/models.py`. |
| `resource_budget.scheduler_max_workers` | Global scheduler cap, integer 1–64; a node's concurrency cannot exceed it. |
| `pricing_file` | Optional operator pricing YAML. Omit/null for usage only. Relative paths use the configuration YAML directory; price file errors do not stop parsing. See [price setup](llm-inference.md#set-operator-prices). |
| `langfuse.on` | Optional boolean for external usage export; off in all six supplied configs. See [optional usage export](optional-capabilities.md#optional-langfuse-usage-export). |
| `pipeline.output_node` | ID of a node producing one `document_dto@v1`. |
| `pipeline.nodes` | Nonempty list of typed DAG nodes. |

Each node has `id`, registered `node`, typed `input` and `output` objects
(`type`, optional `is_list`), `depends_on`, `execution_scope`, and optional
`max_concurrency`, `description`, and `node_config`. `max_concurrency` defaults
to 1. Dependencies are ordered where the node requires it. The first split
node uses `depends_on: [__START__]`; `__START__` is valid only as the sole
dependency of a `fanout` node. `node_config` is checked against the chosen
node's schema, including required connection and model keys. The compiler
checks DTO labels, list cardinality, dependency types, cycles, and output node.
The [architecture guide](architecture.md#graph-and-page-scopes) lists the four
scope shapes and DTO labels.

The local profile's final branch illustrates the contract:

```yaml
pipeline:
  output_node: global_context_assemble
  nodes:
    # Other required nodes and branches are in configs/local_quickstart.yaml.
    - id: global_context_assemble
      node: markdown_document_assembler
      execution_scope: fanin
      input: {type: page_markdown_dto@v1, is_list: true}
      output: {type: document_dto@v1}
      depends_on: [global_context_page]
      node_config:
        task_name: GLOBAL_CONTEXT_EXT
        save_suffix: _OCR
        save_debug_artifacts: false
```

This is a branch excerpt, not a standalone graph. Copy a complete profile and
edit its values. All six supplied configs have separate purposes:

| Config | Graph and recorded verification |
| --- | --- |
| [`default.yaml`](../configs/default.yaml) | Primary 15-node router/full-vision graph ending at `global_context_assemble`; two nine-page runs and regression passed before the Global Context skip policy. |
| [`local_quickstart.yaml`](../configs/local_quickstart.yaml) | Same 15-node router/full-vision graph as default; local Dolphin 1.5/Paddle FastAPI, output `global_context_assemble`. |
| [`managed_endpoints.yaml`](../configs/managed_endpoints.yaml) | Default graph with operator-run vLLM/Triton and OpenAI-compatible vision endpoints; compiled, full provider run unverified. |
| [`group_internal.yaml`](../configs/group_internal.yaml) | Default graph with private providers; compiled, full provider run unverified. |
| [`beta.yaml`](../configs/beta.yaml) | 17-node block-context pipeline under performance validation. Group/internal extraction followed by role-specific restoration; output `block_context_assemble`. |
| [`optional/confluence_upload.yaml`](../configs/optional/confluence_upload.yaml) | Two document-scoped nodes loading Markdown and uploading it; the underlying uploader/client created one page with 38 verified attachments. |

Default, managed and group/internal have no standalone embedded-text extraction
or text-merging branch; image-free L1 pages can use the existing direct-text gate.
See [providers](providers.md) for endpoint contracts and [outputs](outputs-and-failures.md) for saved files.

The optional [local config editor](optional-capabilities.md#local-config-editor) can import and
export YAML and call the same validator/compiler through its loopback API.
It validates a graph without invoking a provider. Its export may contain
endpoint references or secrets entered by a user; review exported files
before sharing them. The [router](optional-capabilities.md#optional-local-router) and [Confluence](optional-capabilities.md#optional-confluence-upload)
guides cover their separate YAML paths.

## Validation boundaries

Validate selected profiles and their environment contracts for the release
candidate using [development checks](development.md). The managed and
group/internal profiles have not completed their own end-to-end provider runs.
Compilation validates graph/schema contracts and does not establish live
compatibility. Track candidate verification in [release checks](release-checklist.md).

The no-argument CLI selects `configs/default.yaml`. The editor catalog offers
all five PDF profiles; Confluence is imported separately. Use model IDs your
endpoint supports and check [model conditions](model-and-data-assets.md).

## VLM roles

Set the restored model settings in `.env` using the profile prefix. YAML
defaults also apply when a setting is missing or empty:

| Profiles | Prefix |
| --- | --- |
| default, managed_endpoints, local_quickstart | `LOCAL` |
| group_internal | `LLM_INTERNAL_API` |
| beta | Group extraction connections; restoration models fixed by role |

| Processing stage | Model variable |
| --- | --- |
| Whole-page VLM | `<PREFIX>_LIGHT_VLM_MODEL` |
| Image/table L2 | `<PREFIX>_LIGHT_VLM_MODEL` |
| Image/table L3 | `<PREFIX>_MEDIUM_VLM_MODEL` |
| Global-context VLM | `<PREFIX>_HEAVY_VLM_MODEL` |

Local_quickstart uses the router and whole-page/global-context stages. The heavy model refines L2 pages. This profile has no `LOCAL_LLM_MODEL` text-merge stage.

## Skipping Global Context on simple pages

Whole-page model calls request a structured `output` body and insert only that
Markdown into the page. Native text remains a direct extraction path. If a
non-skipped Global Context call fails after successful extraction, existing
content and restored tables are retained with an error marker; see
[failure behavior](outputs-and-failures.md#tables-and-page-errors).

`global_context_extraction_vlm_merger.node_config.skip_levels` selects Stage 1
page levels that retain their existing Markdown without another VLM request.
The schema default is `[]`; `default.yaml`, `managed_endpoints.yaml` and
`group_internal.yaml` explicitly set `[1]` on `global_context_page`.

To change this policy, edit that node's existing `node_config`:

```yaml
skip_levels: [1]
```

Keep the existing provider, model, connection and inference settings. These
remain required by the model configuration contract even when calls are skipped.
Set `skip_levels: []` or remove the option to restore refinement of every
eligible page. The value must be a list of strict nonnegative integers;
`[true]`, `["1"]`, `[-1]`, `[1.0]` and the string `"[1]"` are rejected.
This option is available on Global Context and the existing layout nodes;
the layout setting controls a separate stage. Other chat nodes reject it.

| Stage 1 page condition with `[1]` | Upstream result | Global Context |
| --- | --- | --- |
| L1, no embedded image, nonempty native text | Direct pdfplumber text | Retain Markdown; no additional render/request |
| L1, embedded image | Existing light whole-page VLM | Retain Markdown; no additional render/request |
| L1, no embedded image, empty native text | Existing light whole-page VLM | Retain Markdown; no additional render/request |
| L2 or missing level | Existing page processing | Existing Global Context render/request |
| Inherited page failure | Existing error | Existing failure handling takes precedence |

The decision uses only the split page's `page.metadata["stage1_level"]` and
does not recheck images or promote L1 pages to L2. The Global Context node still
runs and returns a new page DTO. It preserves body text, tables, image links,
structured blocks, debug Markdown and DTO failures without changing the input;
the leading `@page:N` is removed before document assembly adds it once.
Skipped pages produce no Global Context usage callback or accounting attempt,
and that node's additional user request is not applied on those pages.

The local editor exposes the option as a JSON list and preserves it through
YAML import/export and validation. Direct callers of
`merge_one_page_image()` or `merge_page_markdown_with_images_vlm()` must pass
`skip_levels` explicitly; both service defaults preserve the previous behavior.
When comparing policies, record `skip_levels` with the graph/input identity and
use a new output directory so an existing final Markdown does not skip the input.

## Provider API types

Group_internal and beta use the internal API. Their L2 and whole-page extraction uses `openai`, while L3 uses `gemini`; group_internal global-context also uses `gemini`. Beta text restoration uses `openai`, and table/image restoration uses `gemini`. All model stages in default, local_quickstart and managed_endpoints use `openai`, including medium/heavy vision models.
API types belong to node configuration, independent of the model ID.
See [provider model examples](providers.md#model-assignments) for the recorded
assignments and access requirements.


See [LLM/VLM prompts, reasoning, accounting and security](llm-inference.md) for additional requests, exact model capability registration, partial costs and offline replay.

Capabilities are project-maintained defaults. Operators can extend verified deployment rules through a separate registry. See [default behavior and operator usage](llm-inference.md#model-capabilities-and-operator-extensions).

## Beta profile under performance validation

`configs/beta.yaml` is a 17-node experimental pipeline. It uses group_internal extraction endpoints and replaces global-context with `text_context_restore`, `table_context_restore`, and `image_context_restore`, all using `layout.block_context_restorer`. Text is fixed to `gpt-6-luna/openai`, table/image to `gemini-3.8-flash/gemini`, with an explicit provider. Public model names do not grant internal deployment capabilities.

L1/native/whole-page/empty/link-only blocks skip additional restoration. Each block makes at most two actual requests; auxiliary restoration failures preserve the original and appear in `block_context_report.jsonl`. Upstream errors remain visible in the final result. `max_workers: 8` caps workers within a node; it is not a global cap across pages/roles. Use 1–2 for initial measurements.

`table_input_max_tokens: 256` is a local UTF-8 bytes/3 estimate, not a billable token limit. Select up to two distinct role-specific `few_shot_examples`, or `[]`. Formatter options `restore_tables: true` and `include_page_marker: false` render verified tables directly; the assembler adds one marker per page. Table context is supported in this direct restoration profile; combining it with downstream global-context needs separate validation.
