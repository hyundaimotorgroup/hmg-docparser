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
server. Fonts are detected automatically; if none are usable, verified Noto Sans
KR and its OFL license are downloaded once into `tmp/paddle_fonts/` and reused.
Set `PADDLE_PDX_LOCAL_FONT_FILE_PATH` in the environment or `.env` to override
the font. See `--help` for options.

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
