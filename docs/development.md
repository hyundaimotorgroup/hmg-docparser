# Development and validation

[한국어](kor/development.md)

Follow [installation](installation.md) to prepare the parser environment.
Contribution and review rules are in [CONTRIBUTING](../.github/CONTRIBUTING.md).
Run commands from the repository root. Choose validation appropriate to the
change; separate offline checks from inference that transfers documents or costs money.

## Offline checks

```bash
python main.py --help
python -m pip check
```

Use the [compile smoke example](installation.md#compile-smoke-check) to validate
`configs/local_quickstart.yaml` without loading a PDF or contacting a provider.
For changed graphs, check node registration/schema, DTOs, list cardinality,
scopes, dependencies, concurrency, and `pipeline.output_node`.

The HTTP input regression file is `tests/test_http_input_security.py`. It uses
synthetic inputs and patched model startup, not downloaded checkpoints or live
model APIs. Install the parser requirements plus test dependencies:

```bash
python -m pip install pytest httpx 'truststore>=0.10,<1'
python -m pytest tests/test_http_input_security.py -q
```

These tests cover bounded decoding, request bodies, image/batch/prompt limits,
queues, timeout/recovery, and safe editor YAML import/export/validation. They do
not constitute a full parser/provider or model-accuracy suite. Include this file
and its imported helper modules in a release that documents the command.
No repository-wide formatter/linter command is prescribed.

## Global Context skip regression

Run the offline suite from the repository root after installing the test
requirements above:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider tests
```

For the focused behavior checks, select `tests/test_global_context_skip.py`.
They verify zero renders/requests for matching Stage 1 pages, calls for L2 and
missing levels, defaults/rollback, Markdown/debug/structured-block/failure
preservation, mixed-page assembly, upstream native/light VLM paths and runtime
cancellation. Config checks include strict values, model-required fields, node
scope, all three shipped profiles, editor catalog and loopback YAML round trips.
Model responses are local stubs; the synthetic pipeline exercises the real PDF
splitter, scheduler, Global Context node and document assembler. These tests do
not measure live provider quality or cost.

## Live checks and regression

Model-only CPU smoke entrypoints are in the
[Dolphin](../tutorial/dolphin_15_fastapi/README.md) and
[Paddle](../tutorial/paddle_ocr_fastapi/README.md) tutorials. They may download
models and need their separate environments. Use fixtures with documented rights.

For the full local quickstart, the clean Conda script creates separate parser,
Dolphin, and Paddle environments, starts CPU servers, waits for model-ready health
responses, and runs the parser. It uses existing Conda or installs checksum-verified
Miniforge under `tmp/miniforge3`. Configure the text/vision model IDs and credentials
in your private `.env` first. Pass an explicit approved input rather than relying
on the private development fixture default:

```bash
bash scripts/verify_local_quickstart_clean_conda.sh --help
bash scripts/verify_local_quickstart_clean_conda.sh configs/local_quickstart.yaml /absolute/path/to/approved.pdf
```

The script rejects occupied ports and requires nonempty final Markdown without
`[Error]` markers. Servers it starts stop on exit. Environments, logs, generated
YAML, and outputs remain under `tmp/clean_conda_<config-name>/<run-id>/`.
`DOLPHIN_15_PORT`/`PADDLE_OCR_PORT` default to 8200/8100; the generated YAML uses
those loopback addresses. `QUICKSTART_READY_TIMEOUT` defaults to 1200 seconds per
server. Set `PADDLE_PDX_LOCAL_FONT_FILE_PATH` when automatic local font detection
is unsuitable. See `--help` for options.

Review regression options before a live comparison:

```bash
python tools/default_config_regression.py --help
```

Select `--config`, `--input`, and a profile-specific `--output-root`. Use
`--record-baseline` for the initial authorized baseline, then the same selection
without that flag to compare Markdown/metrics. Baseline metadata must match the
unresolved pipeline hash and input hash before provider calls. Missing/mismatched
baselines, empty output, or page-error output are rejected. Do not compare
quickstart and default graph baselines. Model output variability can require
review beyond token/sequence similarity thresholds.

Record candidate commit, commands, OS/Python/dependencies, config/input hashes,
model/server versions, data/cost prerequisites, results, and artifacts. Follow
[data handling](privacy-and-data-handling.md) before sharing evidence. Confluence
writes and Langfuse delivery need their own permitted targets and validation.

## Adding or changing a node

1. Update the DTO and interface if the data contract changes. Orchestration belongs
   in `core/nodes/`, reusable processing in `core/services/`, and external calls in
   `core/adapters/`.
2. Register the node in `core/engine/registry/bootstrap.py` and its schema in
   `core/engine/config/node_config.py`. Check `input`, `output`, `is_list`, scope,
   dependencies, and the final output node.
3. Add appropriate compiler/runtime/failure tests using synthetic or licensed
   fixtures. Check page recovery and output preservation where behavior changes.
4. Update [architecture](architecture.md), [configuration](configuration.md),
   [providers](providers.md), [outputs](outputs-and-failures.md), and
   [privacy](privacy-and-data-handling.md), including their Korean counterparts.

## Validation boundaries

Development runs before the Global Context skip policy covered macOS arm64/Python 3.12 local quickstart,
default parsing, and a Confluence create/attachment client path.
They are development evidence, not a guarantee for every release or platform.
Managed/group full runs, real Langfuse delivery, Confluence existing-page updates/
attachment replacement, and PP-DocLayoutV3 integration need separate verification.
Use the [release checklist](release-checklist.md) for the current candidate and
[asset register](model-and-data-assets.md) for fixture/checkpoint conditions.


Project maintainers update `core/adapters/models/resources/model_capabilities.yaml` with exact identities, verification sources/dates and reasoning/usage regression checks. Ordinary users do not edit the built-in YAML. Clean Conda starts the CPU router in the parser environment and records `/health` instance/model readiness, checkpoint SHA-256, page-level Stage 1/2, usage/native preservation and owned-PID cleanup. `ROUTER_PORT` defaults to 8001.

## Beta validation

Beta remains under performance validation. Run `tests/test_block_context_*.py` for role/schema/preservation/retry/concurrency/cancellation/deadline/transport/formatter/DAG contracts. Separate identical-upstream restoration comparisons from full E2E measurements. Record fact preservation, context quality, fallback rate, actual usage, latency and memory. Source-project scores are not OSS validation results.


Updated graph verification on 2026-11-25: local clean Conda installed fresh parser/router 3.12, Dolphin 3.12 and Paddle 3.11 environments and completed mixed_source_9p: 9 pages, 9 Stage 1 and 9 Stage 2 page records, 35 classified elements and 35 actual LLM/VLM requests. Default completed the same PDF with 16 classified elements and 17 model requests. Both preserved native text on pages 6–8 with zero model requests, no missing/duplicate/error pages, and owned-router cleanup. Different Dolphin versions/providers can produce different request counts and Markdown. Beta performance evaluation is separate.

Beta measurements on 2026-11-25 used the first two public design pages. A full CLI run completed both pages with 44 model requests and 143,070 reported tokens; 14 of 23 restoration targets succeeded and 9 retained their originals. In a separate comparison using identical extracted DTOs and the same judge, baseline preserved 133/149 facts and beta 130/149, with no failed judgments. This sample showed no improvement and used more restoration requests/tokens. Broader datasets and the worker 1/2/8 latency/memory comparison remain unmeasured.
