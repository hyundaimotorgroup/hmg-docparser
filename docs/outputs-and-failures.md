# Outputs and failures

`output_dir` is the output root. Local defaults to `mixed_source_9p.pdf`: final `tmp/local_quickstart/mixed_source_9p.md`, intermediate `mixed_source_9p_GLOBAL_CONTEXT_EXT.md`, output node `global_context_assemble`. Earlier pdfplumber/LAYOUT/COMBINE_TEXT files and three-page runs belong to the previous local graph.

| Path under `output_dir` | When it appears |
| --- | --- |
| `<stem>.md` | Final document from the configured output node, when a document result has Markdown. |
| `<stem>_<task_name><save_suffix>.md` | A configured Markdown saver or assembler runs. |
| `imgs/` | An image VLM branch saves image crops referenced by Markdown. |
| `table_imgs/` | A table VLM branch saves table crops; Markdown can link them when `include_table_crop_images` is true. |
| `_llm_usage.jsonl` | LLM/VLM calls record provider usage; optional prices produce local cost estimates. Missing counts stay null. |
| `_private/*_debug*.md` | A saver/assembler has `save_debug_artifacts: true` and writes debug content. |
| `_private/structured-recovery/*_structured_recovery.json` | A structured table token cannot be restored; the file includes unresolved tokens and source table content. |
| `_private/dolphin_failures/page_<N>_<phase>.json` | Dolphin rendering, request or layout validation fails. Validation diagnostics include the raw layout response and image size; these files are excluded from artifact ZIPs. |
| `_page_split/`, `_layout_crops/` | Temporary split PDFs and layout crops; removed after each input unless `keep_page_artifacts: true` for the relevant node. |

Image and table crop directories can remain even when temporary layout crops
are removed. The recorded local result contained `imgs/` and `table_imgs/`. Local output
files are not automatically purged. See [privacy](privacy-and-data-handling.md)
before retaining or sharing them.

## Pages that skip Global Context

Default, managed_endpoints and group_internal retain Stage 1 L1 page Markdown
with `global_context_page.node_config.skip_levels: [1]`. The page node returns
its existing body, tables, image links, structured blocks, debug content and DTO
failures. Assembly includes these pages in order with one `@page:N` marker each.
Inherited page errors retain the existing failure path; skipping does not turn
an error into successful page content. Skipped pages emit no additional Global
Context usage record, while earlier model calls retain their own usage.
See [configuration](configuration.md#skipping-global-context-on-simple-pages)
for restoring all-page refinement with `[]`.

## Tables and page errors

If Global Context refinement fails after successful upstream extraction, the
document retains that page's Markdown, restored tables and image references,
followed by an error marker. Page failure metadata is retained. An inherited
layout/OCR/table/image failure still follows the existing failure path; preserving
a refinement input does not mark the failed refinement as successful.

`table_vlm_caption_maker.node_config.table_output_format` accepts
`markdown`, `html`, `json`, or `toon`; all five PDF profiles select
`markdown`. Table HTML is sanitized and converted to the selected form.
Structured table placeholders are restored after text merging; a missing
provider token can cause the validated table text to be appended, while an
unresolved token is preserved and recorded in the recovery artifact.

Layout, OCR, table, and image node failures can be recorded on a page as
`[Error] <stage>: <reason>` in Markdown. Other pages may still complete. A
schema, input validation, nonrecoverable node, or final output failure may stop
the run instead. Do not interpret a successful process exit as a guarantee
that every page parsed correctly: inspect page sections, search for `[Error]`,
and compare important tables and images with the source PDF. The local sample
completed three times with zero `[Error]` markers. Before the Global Context skip policy, default completed two
nine-page runs with zero page errors, but its two regression comparisons fell
below the Jaccard threshold. Those results are development evidence, not a
guarantee of text or table accuracy for every document.

Failure text, debug Markdown, recovery JSON, and images may contain source
content or provider error details. Remove credentials and document content
before posting logs or artifacts. The input scanner skips an input when its
final `<stem>.md` already exists in `output_dir`; use a new output directory
for a rerun you need to compare.

## Sharing example outputs

Use [data handling](privacy-and-data-handling.md) to review final/intermediate
Markdown, images, tables, errors, debug, and recovery artifacts together before
sharing them. Verify the source PDF and derived output's redistribution rights
in [model/data assets](model-and-data-assets.md). Release validation includes a
comparison with the authorized source and checks for private content; record
those results in the [release checklist](release-checklist.md).


Clean Conda verifies every page in `stage1_report.jsonl`, required element classifications in `stage2_report.jsonl`, `_llm_usage.jsonl`, final page completeness and native text preservation. Health alone does not establish successful use.

## Beta outputs and auxiliary failures

Beta writes final `<stem>.md` and intermediate `<stem>_BLOCK_CONTEXT.md` from `block_context_assemble`. Inspect role/page/block restored/failed/attempt counts in `block_context_report.jsonl`. Provider success and preservation validation success are separate. Failed restoration retains original content without turning a valid extraction page into an error page. Debug is disabled by default; enabled reasoning/raw HTML stay in `_private` artifacts.


Updated graph verification on 2026-11-25: local clean Conda installed fresh parser/router 3.12, Dolphin 3.12 and Paddle 3.11 environments and completed mixed_source_9p: 9 pages, 9 Stage 1 and 9 Stage 2 page records, 35 classified elements and 35 actual LLM/VLM requests. Default completed the same PDF with 16 classified elements and 17 model requests. Both preserved native text on pages 6–8 with zero model requests, no missing/duplicate/error pages, and owned-router cleanup. Different Dolphin versions/providers can produce different request counts and Markdown. Beta performance evaluation is separate.
