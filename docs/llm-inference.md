# LLM/VLM prompts, reasoning and accounting

All six general chat nodes accept `pipeline.nodes[].node_config.user_prompt`: `image_vlm_processor`, `table_vlm_caption_maker`, `text_markdown_llm_merger`, `text_image_vlm_merger`, `global_context_extraction_vlm_merger`, and `whole_page_llm_processor`. Fixed instructions, examples and output contracts are system messages. OCR, Markdown, images and additional requests are user data. Whole-page `prompt` remains a trusted system instruction; its model response uses an object with a single `output` string, and only that Markdown body enters the document. Native PDF text still bypasses the model. Dolphin, router and OCR protocols are independent.

```yaml
node_config:
  provider: openai
  model_name: gpt-6.1-sol
  base_url: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
  user_prompt: |
    Explain the visible diagram dimensions and component relationships in detail.
```

For a single execution, use the existing Python pipeline entry point:

```python
from core.engine.runtime import run_document_pipeline_from_config_path

run_document_pipeline_from_config_path(
    "configs/default.yaml",
    runtime_config={"node_overrides": {
        "image_parse": {"user_prompt": "Describe the diagram in detail."},
    }},
)
```

Use the actual node ID from your YAML; `image_parse` above is illustrative. Only known general chat node IDs and the `user_prompt` key are allowed. Omitted keys inherit YAML. Explicit `null`, empty strings and whitespace clear the request. YAML and run inputs are validated before processing, without silent truncation. Defaults are 8,192 Unicode code points and 32 KiB UTF-8 per node, and 128 KiB across the final node requests per execution. Newlines, indentation and multilingual text are preserved. Unsafe controls, surrogates and bidi controls are rejected. `${NAME}` in an additional request is literal text; connection credentials still support environment references.

Trusted host YAML may set `prompt_policy` with positive integer limits: `max_codepoints`, `max_bytes`, `max_run_bytes`, `max_context_bytes`, and `max_output_bytes`. Context and output default to 4 MiB each. The context check is a byte budget, not a tokenizer or a guarantee of the provider's token limit; oversized documents fail explicitly and must be split by the host. Override data cannot change host policy, endpoints, credentials, system messages, schemas, tools or prices. The loopback config editor includes a textarea, Unicode/UTF-8 counts and redacted validation errors. Its counter describes default limits; host policy is enforced by the server.

Without an additional request, images use the existing brief-caption default. Requests may ask for more detail within the schema and factual contract. Detailed linked captions are restored if downstream merges shorten or omit them. Crop filenames, table placeholders, caption fences and block coverage are retained. Disabled image parsing, missing crops, router skips and native whole-page text do not force model calls. On these paths, the request is not applied; `image_vlm_used`/`native_text_direct` and the absence of accounting attempts expose that fact. Requests are not automatically copied to other nodes.

Global Context supports page-level `skip_levels`, with `[1]` enabled in default,
managed_endpoints and group_internal. Matching Stage 1 pages retain their upstream
Markdown with host-side table restoration, without image rendering or a VLM request. The node's `user_prompt` and reasoning
are not applied on skipped pages, and no Global Context usage callback or attempt
record is emitted. Existing light whole-page VLM calls still apply when native
text is unavailable. L2/missing-level pages use the existing inference options;
`[]` restores refinement on all eligible pages. See
[configuration](configuration.md#skipping-global-context-on-simple-pages).

## Reasoning

The OpenAI chat transport does not add a default `temperature`, including for
unregistered models. Set `extra_body.temperature` only when you intend to send
it; known unsupported sampling options are rejected before transport. Dolphin's
separate layout inference keeps its own generation settings.

`core/domain/inference/models.py` defines immutable `ReasoningConfig`. `core/adapters/models/reasoning.py` resolves intent and serializes it; `core/services/model_routing.py` owns connection and level inheritance. Capability entries are exact provider/protocol/model/deployment identities in `core/adapters/models/resources/model_capabilities.yaml`; prices live separately.

Most users can omit reasoning entirely. A successfully loaded capability for a verified effort model that supports low sends low automatically. Budget-only and unknown models send no reasoning option. Low does not mean disabled; medium does not guarantee positive thinking on every request. Actual server effort stays `unknown` unless separately reported.

```yaml
# Optional trusted developer settings, not required in the default YAML/UI.
reasoning: {mode: effort, effort: medium}
# Other forms:
# reasoning: {mode: provider_default}  # omit; also disables default_low
# reasoning: {mode: disabled}         # only if supported
# reasoning: {mode: budget, budget_tokens: 1024}
# reasoning: {mode: adaptive, effort: low}
```

Null reasoning uses normal resolution. Priority: explicit intent → legacy `extra_body` intent → registered model suffix → capability default low → omission. Explicit intent replaces valid legacy intent. Conflicting legacy forms, invalid budgets and unsupported explicit options fail before transport. No fallback retry weakens intent. `level2_reasoning`/`level3_reasoning` inherit only for the same final model/provider/API/endpoint/deployment identity. Different identities discard inherited thinking while retaining ordinary sampling options. A level `extra_body` replaces the entire base body, including an explicit empty mapping.

Public `gpt-6.1-sol` supports low/medium/high/xhigh/max and defaults to OSS low; none/minimal are rejected. Public `gpt-6-luna` also supports none/disabled. Neither receives unsupported sampling defaults. For their Chat API, use `extra_body.max_completion_tokens` (positive integer, at most 128000); legacy `max_tokens` is rejected before transport. Native output limits and Anthropic budget/output constraints are also validated. Gemini 2.5 Flash/Pro entries use documented budgets, not invented low budgets. Public Claude Opus 5.5 supports adaptive thinking and effort, including default low; forced schema tools are rejected for this model. Claude Sonnet 4 supports budget thinking; forced tools with budget thinking are also rejected. Unknown Gemini/gateway aliases remain option-free. Generic `openai-compatible` receives no vLLM repetition penalty; explicit `vllm` is a separate backend.

SDK serialization is tested with real SDKs and in-memory HTTP transports. google-genai 1.75.0 retains the existing Pydantic pin. Nested thinking keys are serialized by an engine-owned native HTTP extension to avoid SDK snake_case pass-through. Older Anthropic SDKs serialize documented native `output_config` through their `extra_body` extension. These are wire compatibility checks, not live provider acceptance or quality checks.

## Model capabilities and operator extensions

`core/adapters/models/resources/model_capabilities.yaml` is a project-maintained **API compatibility table**, independent of prices. Ordinary users do not need to write it. It describes supported reasoning modes/efforts, default low, sampling restrictions, output limits and provider usage semantics. A price entry cannot enable a model feature, and a capability entry does not provide a price.

Built-in rules load once on the first model lookup. If the file is missing or invalid, the entire table is rejected and a safe `default_capabilities_unavailable` warning is emitted once. Basic calls continue with the existing unknown-model behavior: no automatic low, no registered suffix conversion and no capability-based omitted-token-to-zero inference. Provider/API and response validation still apply; this fallback does not guarantee that an endpoint accepts the request. Explicit unsupported reasoning or legacy thinking options fail before a model request, rather than being silently dropped. Explicit `mode: provider_default` intentionally leaves reasoning to the provider. Restart the process after correcting a built-in file; failed loading is not retried on each call.

### Add verified deployment rules

Use an operator file or trusted Python registration for a private deployment. Match `provider`, `api_type`, `model` and optional `deployment` exactly to the configured route. Public API capabilities do not automatically apply to an internal service with the same model name. Do not put credentials, endpoints or rates in this file.

For a service you have confirmed supports the OpenAI-style effort parameter, an operator file can start with:

```yaml
models:
  - provider: llm_internal_api
    api_type: openai
    model: demo-deployment
    modes: [effort]
    efforts: [low, high]
    default_low: true
    serializer: openai
```

This is an illustrative deployment contract, not a claim about your service. Only declare options the deployment supports. `version: 1` is optional. Fields not relevant to your deployment can be omitted. `serializer` selects a registered serializer (`openai`, `gemini` or `anthropic`), not a Python import path. Custom serializers and usage semantics require trusted Python registration.

Load the file explicitly and pass the resulting registry through the existing runtime extension:

```python
from pathlib import Path
from core.adapters.models.capabilities import CapabilityRegistry
from core.engine.runtime import run_document_pipeline_from_config_path

registry = CapabilityRegistry.from_path(
    Path("my-model-rules.yaml").resolve(), include_defaults=True
)
run_document_pipeline_from_config_path(
    "configs/group_internal.yaml",
    runtime_config={"_capability_registry": registry},
)
```

Configure the matching provider/API/model in the selected node as usual. `include_defaults=True` retains built-in rules for other identities; an exact operator entry takes precedence. Omit this flag to use only the selected file. Relative paths passed directly to `from_path` use the Python process's current directory; use an absolute path when the location matters. This Python extension does not introduce a new native YAML configuration option.

An explicitly selected file fails before execution if it is missing, empty or invalid. Duplicate YAML keys or identities, unknown fields, string booleans, malformed modes/efforts, invalid dates and nonpositive/inconsistent limits are rejected. Trusted `ModelCapability(...)` registration uses the same entry validation. Source/date metadata records the operator's evidence; it does not verify live availability or expire rules automatically.

`omitted_thinking_is_zero` defaults to false. Enable it only with documented deployment-specific evidence, a nonempty `source` and an ISO `verified_on` date. Even then, usage normalization requires valid counts and successful final completion; explicit null/invalid thoughts never become zero. Most operators should leave this field unset. `registry.load_error` exposes a safe built-in loading diagnostic when inherited defaults are unavailable.

## Usage and costs

Usage is recorded independently of pricing. Cost calculation is optional, operators maintain their actual rates, and stored JSONL can be repriced without another model request. Omit `pricing_file` (or set it to null) to record usage without calculating cost.

### Set operator prices

Prices are in **USD per one million tokens**. Start with this four-line file:

```yaml
openai:
  demo-model:
    input: 1.00
    output: 4.00
```

These are fictional rates. Replace them with your service contract. Match `provider` and model keys exactly to `provider` and `model_name` in `_llm_usage.jsonl`; the recorded model can differ from a configured alias. No prices are inferred from model names or shared between public APIs and internal services. `configs/optional/llm_pricing.yaml` is an example and is never loaded automatically.

Save your file beside the selected configuration YAML and enable it there:

```yaml
pricing_file: ./my-prices.yaml
```

Relative paths resolve against that configuration file's directory. For a Python mapping passed to `run_document_pipeline`, use an absolute price path or pass `config_dir=...`; the current directory is not silently assumed. `load_yaml_with_env` retains the source directory. The editor preserves `pricing_file` without opening it; after export, relative paths refer to the exported YAML location. The trusted `_host_pricing_path` compatibility option remains available. Conflicting explicit paths disable pricing with a diagnostic and parsing continues.

Numeric values and numeric strings must be finite and nonnegative; explicit zero is valid. Duplicate YAML keys, booleans, negative values, NaN/Infinity and malformed structures are errors. A missing, empty or invalid price file disables pricing with a safe diagnostic during parsing. Usage serialization, collection limits, calculation or local sink failures do not repeat a successful provider request or discard its parsing result. Invalid response JSON, abnormal finish reasons, schema mismatches and output limits remain response failures.

Basic input/output rates do not verify cache discounts, long-context rates or additional billing components. Missing cache detail remains null; an input-rate assumption can produce a partial subtotal. Add only the conditions your service uses. For a cache-read discount:

```yaml
openai:
  demo-model:
    input: 1.00
    output: 4.00
    cache_read: 0.10
```

For prices depending on the request's total input length:

```yaml
openai:
  demo-model:
    bands:
      - up_to: 272000
        input: 1.00
        output: 4.00
      - up_to: 1050000
        input: 2.00
        output: 6.00
```

These figures are fictional too. Bounds must increase. The bands cover 0–272,000 and 272,001–1,050,000 input tokens; one band prices the whole request, including output. This is not progressive billing of just the excess. Unknown total input or input beyond the last band is unpriced. Do not combine model-level input/output with `bands`. Optional `cache_read` can be shared at model level or overridden per band. Advanced legacy `entries` files retain API, deployment, region, tier, TTL and date selectors; the four-line format does not require those fields.

### Read usage and cost results

Each actual attempt creates a version 2 record with `call_id`, `attempt_index`, `event_id`, canonical usage, filtered raw usage/snapshots, completion evidence, requested/effective/sent reasoning, processing outcome and, when pricing is enabled, an immutable price snapshot. Disabled or failed pricing leaves `pricing_snapshot: null`. Historic snapshot contents and fingerprints are preserved. Missing counts remain null. Reported zero is zero. OpenAI/Anthropic output already includes reasoning; Gemini output is valid candidates plus thoughts. No display function computes output from total minus input. Normal provider completion and application parsing success are separate. EOF alone is insufficient. Failed/cancelled attempts retain any usage already received. SDK retries are disabled, engine transport retries are individually recorded, and sink/schema failures never repeat a successful paid request. A shared client uses context-local records; callback-free calls expose `last_call_records` and `last_usage_record` in the calling context.

A stream that ends without a terminal reason can retry within the existing
attempt and timeout limits. Partial text from that attempt is discarded as page
output, while its usage record remains. Explicit abnormal finishes, such as a
token limit or a safety stop, are failures and do not trigger this retry.

Gemini omitted thoughts derive zero **only** with an exact verified `omitted_thinking_is_zero` capability, valid input/body counts, explicit successful normal completion and final usage, no numeric contradiction, and no earlier positive thought snapshot lost. Null/invalid values, failure, cancellation, MAX_TOKENS and absent completion evidence do not qualify. No public/gateway omission capability is enabled merely from a model's name. Synthetic tests register that policy explicitly. Cache omission stays null independently.

The Decimal calculator prices ordinary input, cache reads/writes and total output once. If total output is unknown but visible body is valid, `components.response_output` is included in the known subtotal. Complete output replaces that body component, preventing double charging. API `cost_usd` is retained as a separate provider-reported amount and is never added to the token estimate. Model pricing `complete` means a complete estimate for the stated scope, not reconciliation with a bill.

When pricing is enabled, valid reported tokens are priced using registered rates even when cache breakdown is incomplete. For OpenAI/Gemini inclusive input, subtract only reported read/write counts and price the remaining input at the regular rate as `estimated_input_usd`. Reported cache counts use their own rates and are not added twice. Anthropic reports noncached input separately: `regular_input_tokens` preserves and prices that count even when canonical inclusive input is null. Invalid fields do not erase other valid token components. When only reasoning output is reported, its tokens are priced once at the output rate. Valid unclassified remainder counts are separately estimated at the maximum registered input/output rate; this does not classify them as output or establish a guaranteed cost bound.

`estimated_components` records rate assumptions; `estimated_subtotal_usd` combines those estimates with known components once. Missing cache read rates use the registered regular input rate as an explicit estimate. Missing cache-write TTL uses the maximum registered TTL rate (or the regular input rate if no write rate exists) as an explicit estimate; it does not claim an actual TTL. Legacy entries can select an assumed context band from collected Anthropic input; that tariff remains estimated. New `bands` require known total input. Canonical missing cache fields stay null. Unregistered or invalid rates are not invented.

`tokens_complete` and `cost_status` are independent. An incomplete total cost has `amount_usd: null`. `known_subtotal_usd` and `known_subtotal_average_page_usd` are separate component sums, not the whole cost or a guaranteed lower bound. A missing monetary basis is `unknown` and displays `—`; valid zero displays 0. Disabled pricing displays `disabled (usage recorded)`. `missing_usage` means provider usage is absent; `unpriced` means no applicable price or pricing disabled/failed; `partial` means only some components or assumptions could be calculated. A null amount does not mean free service. The CLI selects complete amount → subtotal including estimates → known components. It labels estimates as `estimated subtotal (partial)` and reports incomplete cost attempts and USD and summaries include `estimated_subtotal_average_page_usd`; every model/node/page bucket follows the same rule. Output display prefers known body counts, otherwise known total output; it never mutates the summary.

`_llm_usage.jsonl` and atomic `_llm_usage_summary.json` are written under the execution output directory on success/failure/cancellation. The shared reducer supplies live tracker, JSONL replay and stored calculations. These accounting files are excluded from public artifact ZIPs. Logs omit prompts, output bodies, credentials, headers and endpoints; errors omit provider exception text. Failed attempts can include `metadata.request_error` with filtered exception type, HTTP status, error code and parameter. Optional Langfuse 4.9 uses `start_observation`: complete estimates supply canonical usage and total cost; partial observations omit model and numeric usage to suppress automatic pricing, while metadata retains estimated input/subtotal and assumption bases.

The existing Langfuse exporter supplies model, numeric usage and cost only for complete local costs. With pricing disabled or partial/unpriced, it sends metadata observations with those fields omitted. Enabling Langfuse does not automatically calculate costs. Local JSONL is the primary record; successful parsing or flush does not establish server receipt, and background delivery failures can go undetected.

### Reprice saved JSONL

Offline replay never calls a model, never modifies the source JSONL and requires a new output directory:

```sh
python tools/recalculate_llm_usage.py outputs/run/_llm_usage.jsonl outputs/replayed --page-count 3
# Explicit new price estimate (as-of date is a host choice):
python tools/recalculate_llm_usage.py outputs/run/_llm_usage.jsonl outputs/repriced \
  --pricing configs/my-prices.yaml --as-of 2026-11-18 --page-count 9
```

For an undated operator file, `--as-of` does not establish that the rates were historically in effect. Offline `--pricing` reports an invalid file as an error because calculation is the purpose of that command. Local estimates are not provider invoice amounts.

Records without a snapshot can be replayed and repriced; `--repair` leaves them unchanged. Legacy identical lines retain distinct occurrence IDs. Ambiguous legacy cache/thinking remains missing. `--repair` enriches historical v2 records in memory only when stored price fingerprint/date/entry, raw counts, completion and capability evidence validate. It does not alter the source; repeated enrichment is idempotent. Historical repair also restores omitted input estimates and independently reported Anthropic noncached input from raw usage. An explicit `--pricing` re-estimate is different from historical repair. `load_summary` reads the atomic file without a live tracker.

## Trusted extensions and output security

Register `ModelCapability` in `CapabilityRegistry`, a serializer with `register_reasoning_serializer`, a backend factory with `register_chat_provider`, and custom tasks with `register_task_builder`. Registration is trusted Python code, never an import path supplied by a prompt. Pass a host registry through `runtime_config['_capability_registry']`; `_host_pricing_path` selects a trusted price file. Static capability files can be loaded with `CapabilityRegistry.from_path`.

```python
from core.adapters.models.capabilities import CapabilityRegistry, ModelCapability
from core.adapters.models.reasoning import register_reasoning_serializer
from core.adapters.models.factory import register_chat_provider
from core.adapters.models.unified import ProviderChatAdapter

register_reasoning_serializer("my_compute", lambda intent: {"compute_effort": intent.effort})
registry = CapabilityRegistry()
registry.register(ModelCapability(
    provider="my_server", api_type="openai", model="my_model",
    modes=("effort",), efforts=("low", "high"), default_low=True,
    serializer="my_compute", source="host-verified deployment contract",
))
register_chat_provider("my_server", lambda: ProviderChatAdapter("my_server"))
# Configure provider=my_server, api_type=openai and use registry in trusted runtime_config.
```

A legacy advanced price entry specifies exact provider/api_type/model, optional explicit aliases/deployment/region/service_tier/context interval/cache_ttl, `source`, `verified_on`, `effective_from`, `effective_until`, and rates per million tokens. Unknown or multiple matches are unpriced. Token generation/cache is the built-in calculator scope; other charge components must be declared unsupported (partial) or handled by a trusted extension before they can be complete.

Model JSON keys/types/output lengths are validated before artifacts. Filenames are sanitized; unsafe remote, absolute or traversal image paths are removed. Tables retain validated structure and only named/hex `color` and `background-color` values, rejecting events, URLs, expressions and arbitrary CSS. All HTML tags outside validated tables in model Markdown are escaped. Applications rendering Markdown must still disable raw HTML or apply a sanitizer and restrict asset serving to the output root. Role boundaries and validators limit authority; they do not claim that prompt injection is impossible.

Official contracts fetched for this implementation: [OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning), [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [OpenAI pricing](https://developers.openai.com/api/docs/pricing), [Anthropic thinking](https://platform.claude.com/docs/en/build-with-claude/thinking). Google thinking page retrieval was blocked; Gemini budget capabilities retain the baseline documented contract and live/model omission behavior requires separate verification. Offline tests do not establish provider availability, image quality, server reasoning strength, or invoice accuracy.


## Empty responses and structured Markdown recovery

The unified client classifies completed empty text as `empty_text_response` before
JSON parsing. A schema-valid required `output` containing only whitespace is
`empty_structured_output`. Only these processing errors may retry a completed
response. Invalid JSON, schema violations, refusal/safety/length finishes, and
postprocessing errors do not become empty retries. The configured maximum includes
the first request (default three); waits check cancellation and the overall deadline.
Every paid attempt retains the same call ID, increasing attempt index, observed
completion, usage, and a safe diagnostic code. Accounting failures do not repeat a
successful provider request.

The shared protocol retains `[[TABLE_BLOCK:table_<16 lowercase hex digits>]]`
and the existing `vlm_image_caption` fences. Prompt version `3` and protocol
`structured-markdown-1` are recorded in usage/page metadata. Models copy opaque
IDs and exact summaries. Pure restoration returns text, occurrence diagnostics,
and restored/appended/removed identities; page updates and private recovery writes
happen at the caller boundary. All token occurrences are restored, and automatic
append consumes existing exact table occurrences so repeated restoration is stable.

A source reference missing from its registry, an empty/invalid table, conflicting
registry entries, or an unresolved token remains an error with usable content
preserved. Only a complete registry and captured source references allow invented
references to be removed as warnings. Code fences do not exempt model output;
literal exemptions require explicit host/native provenance. Body and debug issues
are aggregated separately under `_private/structured-recovery`.

Final assembly and the runtime writer share validation. Internal page/node metadata
and the usage summary distinguish `complete`, `complete_with_errors`, and `failed`;
existing external status enums are unchanged. Partial output contains preserved
content and error markers. Evaluation consumers require the complete-document
contract, including metadata errors rather than file existence alone.


Built-in rules load through `importlib.resources`, independently of the working directory and repo-root configs. The project maintains them; users receive updates with the package. Unknown models can attempt basic calls with reasoning omitted or `provider_default`. Advanced verified extensions use `configs/optional/model_capabilities.example.yaml`, explicitly loaded with `CapabilityRegistry.from_path(..., include_defaults=True)` and passed as runtime `_capability_registry`. For YAML directly under configs, price opt-in is `pricing_file: ./optional/llm_pricing.yaml`.

## Beta restoration requests

Trusted role instructions and fictional examples enter system messages; the block reference and additional request enter TaskPrompt JSON user data. Each role renders the current page once and closes worker image copies. Responses contain exactly two strings, `reasoning` and `output`. Strict JSON does not repair fences, keys or bodies. Validation preserves references, numeric signs/decimals/units/punctuation and existing captions/links. Reasoning stays out of normal Markdown and usage bodies; enabled debug stores it privately. A shared page deadline and cancellation stop new blocks/retries; in-flight transport cleanup follows timeout/cancellation support.
