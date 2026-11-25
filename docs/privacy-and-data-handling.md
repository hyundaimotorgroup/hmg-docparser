# Privacy and data handling

[한국어](kor/privacy-and-data-handling.md)

HMG-Doc Parser runs as a local CLI, but selected nodes send document content to
model services. A local layout/OCR setup still needs an image-capable LLM/VLM
endpoint. Choose documents and services you are authorized to use, and review
provider terms for retention, training use, location, security, and charges.
This repository does not control an external provider's handling of requests.

## Data flow

| Feature | Data processed | Destination and persistence |
| --- | --- | --- |
| PDF pipeline | Input PDF, page images, crops, extracted text, tables, prompts, generated text | Local processing plus the layout/OCR/LLM/VLM endpoints selected in YAML. Whole-page and global-context nodes can send broader page/document context than element nodes. |
| Router | Page/element image uploads | Configured router service; the supplied local entrypoint binds to loopback. |
| Artifacts | Final/intermediate Markdown, images, table crops, errors | Configured `output_dir`; see [output paths](outputs-and-failures.md). |
| Model initialization | Model files and decoder dictionaries | Tutorial services can download assets from external hosts and retain local caches. This is separate from transmitting a PDF for inference. |
| Config editor | Imported YAML and directly entered credentials | Browser memory and loopback requests; exported YAML includes direct values. |
| Langfuse | Model/provider, API type, token counts, job/node metadata | Optional external export to `LANGFUSE_HOST`; off in all supplied profiles. |
| Confluence | Markdown, local attachments, page titles and target IDs | Explicitly selected HTTPS Confluence destination; remote pages/attachments can change. |

Endpoint credentials come from your private environment or `.env`. Keep example
YAML values as environment references. Do not publish actual keys, internal
addresses, exported configs containing direct secrets, or private documents.
The group/internal profile does not grant access to group services.

The three Global Context profiles (default, managed_endpoints, group_internal)
set `skip_levels: [1]`: matching Stage 1 pages are not sent for additional Global
Context refinement. Router uploads and any earlier light whole-page VLM request
remain. L2/missing-level pages still send their existing context, and `[]`
restores refinement for every eligible page. See
[the policy](configuration.md#skipping-global-context-on-simple-pages).

## Outputs and retention

Final and intermediate Markdown, `imgs/`, and `table_imgs/` can retain source
content. Temporary `_page_split/` and `_layout_crops/` artifacts are removed
unless the relevant node retains them with `keep_page_artifacts: true`.
This does not purge all outputs, caches, downloaded files, or copies you make.

`save_debug_artifacts: true` may write private debug Markdown. Structured table
recovery can write original table content under `_private/structured-recovery/`.
The `_private` name is a directory convention, not encryption or access control.
Output directories and usage files have no automatic retention expiry. Apply
your filesystem access controls, backup policy, and deletion schedule.

## Usage records, errors, and telemetry

Dolphin failures can write raw layout responses and image dimensions under
`_private/dolphin_failures/`. These diagnostics can contain document content
and are excluded from artifact ZIPs, but remain local files until removed.

`<output_dir>/_llm_usage.jsonl` records call/attempt/event and job/node/page IDs, model/provider,
reported token counts, cached tokens, and optional cost estimates. Missing counts stay null. Its writer
does not include prompt or model output text. IDs and filenames can still identify
a document. Runtime usage/progress records in memory can contain prompts and
outputs, and errors or debug artifacts may expose source content or provider
information. Do not interpret the JSONL schema as a guarantee about every log.

With `langfuse.on: true` and configured credentials, the generation exporter sends
limited job/node and accounting metadata. Model, numeric usage and cost are supplied
only for complete local costs; disabled pricing and partial/unpriced costs omit them. It does not
include prompt, output, or document-body fields in that generation payload.
Review identifying metadata and the destination before enabling it. Export
failure does not stop parsing, so a successful parse does not prove delivery.
See [Langfuse behavior](optional-capabilities.md#optional-langfuse-usage-export).

## Config editor and Confluence

The editor processes submitted graphs in request memory and does not store them
in an application database. Browser downloads and exported `pipeline.yaml` can
retain full configurations, including directly entered secrets. Prefer environment
references and inspect exports before sharing; closing a tab does not remove downloads.

Confluence upload is a separate pipeline. It can create or update pages and
replace attachments; `update_existing` defaults to `true`. Check the target space,
credentials, write permissions, and attachment contents before running it. Result
JSON can contain remote URLs, titles, IDs, and errors. Remote copies follow your
Confluence retention and access policies. See
[Confluence upload](optional-capabilities.md#optional-confluence-upload).

## Sharing and incident reporting

Use synthetic or licensed examples when sharing results. Review Markdown,
images, table/debug/recovery files, errors, and metadata together; masking a
filename alone does not remove sensitive content. Model and dataset rights are
listed in [model/data assets](model-and-data-assets.md), and publication checks
are in the [release checklist](release-checklist.md).

Report security issues privately to [PSIRT](../.github/SECURITY.md). CLA account
and electronic-acceptance records follow the privacy notice supplied by the
organization at collection; this parser guide does not replace that notice.

Usage recording is independent of prices. A selected pricing snapshot can contain rates and contract selectors; treat it as private execution data. The price file itself is not included in ZIPs or telemetry. Langfuse supplies model, numeric usage and cost only for complete costs, omitting them for disabled/partial pricing. See [pricing](llm-inference.md).
