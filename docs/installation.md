# Installation and validation

The completed local run used macOS arm64 and Python 3.12.15 in a fresh Conda
environment on 2026-10-23. Other complete pipeline platforms and Python
versions remain to be verified. The parser CLI runs on your machine; the
Dolphin and Paddle tutorial servers have separate environments and setup
instructions in the [local guide](providers.md#local-dolphin-and-paddle-with-openai).

Clone the published source and run installation commands from its root:

```bash
git clone https://github.com/hyundaimotorgroup/hmg-doc-parser.git
cd hmg-doc-parser
```

Install the parser and inspect its CLI:

```bash
conda create -n pdf-parser python=3.12 -y
conda activate pdf-parser
python -m pip install -r requirements.txt
python main.py --help
```

[`requirements.txt`](../requirements.txt) is the single dependency file for the
parser, local router, and Langfuse export. Optional feature packages are active
installation entries so dependency scanners can include them; comments label
their roles. Installing them does not start the router or enable Langfuse
export. Local_quickstart requires the router; Langfuse remains disabled. The two model
tutorials retain separate requirements files because their server environments
use different dependency versions; follow their linked instructions rather
than installing those server dependencies into the parser environment.
See the [router](optional-capabilities.md#optional-local-router),
[config editor](optional-capabilities.md#local-config-editor), and [telemetry](optional-capabilities.md#optional-langfuse-usage-export) guides for
their separate local use.

Security remediation pins are included directly in each environment's
requirements file, with no separate constraints file to package. Existing
parser environments can be updated with
`python -m pip install --upgrade -r requirements.txt`, followed by
`python -m pip check`.

## Compile smoke check

This checks the local profile's native schema, registry, and DAG without
starting providers or processing a PDF. It deliberately leaves `${NAME}`
references as configuration values; a real run resolves them from the
environment before validation.

```bash
python - <<'PY'
from pathlib import Path
import yaml
from tools.config_editor import validate_config

config = yaml.safe_load(Path("configs/local_quickstart.yaml").read_text(encoding="utf-8"))
print(validate_config(config))
PY
```

For an actual run, copy `.env.example` to `.env`, fill only the variables for
your chosen profile, and keep `.env` out of commits. Shell environment values
take precedence over `.env`. The local profile needs loopback Dolphin/Paddle
URLs plus your OpenAI text model, light/medium vision model IDs and API keys; see
[providers](providers.md) and the [local setup](providers.md#local-dolphin-and-paddle-with-openai). Provider calls
can incur charges and send document content to their endpoints. The recorded local run
used local Dolphin/Paddle services and a VLM API. See [development](development.md)
for validation boundaries and [assets](model-and-data-assets.md) for sample rights.

The CLI accepts one optional positional config path. Its no-argument default
is `configs/default.yaml`, the primary full-vision profile requiring router,
Dolphin v2, Paddle Triton, a local LLM API with OpenAI-compatible vision calls.
Use `configs/local_quickstart.yaml` explicitly for the introductory local setup. Use `configs/managed_endpoints.yaml` for self-managed
servers or `configs/group_internal.yaml` for private services. See [configuration](configuration.md) before changing YAML.

After installation, follow the [quickstart](quickstart.md) to start the required
services and parse a PDF. The [recommended model combination and Dolphin v2
hardware](../README.md#recommended-settings) are separate from the introductory
local FastAPI setup.

Default, managed_endpoints and group_internal set Global Context `skip_levels: [1]`;
Stage 1 L1 pages retain their upstream content without an additional refinement
request. Other pages still need the configured VLM endpoint. See
[the policy and rollback](configuration.md#skipping-global-context-on-simple-pages).

## Validation and sample selection

The recorded complete local pipeline covers macOS arm64/Python 3.12; it does not
establish full-platform support. Use [development checks](development.md) and
[the release checklist](release-checklist.md) to verify a fresh candidate.

The profile's private development sample may be absent from a clone. Set
`input_dir` to your own authorized PDF and choose a new `output_dir` before an
actual run. Bundled sample and model conditions are in
[model/data assets](model-and-data-assets.md). For commercial layout use,
PP-DocLayoutV3 is recommended; the supplied Dolphin profiles require their own
model conditions and a PP-DocLayoutV3 adapter has not been supplied.
