# Model adapter map

Start with `factory.py` when you need to know which provider is selected from
configuration. It is the single place that normalizes provider aliases before
choosing an adapter.

| Provider/config value | Entry file | Transport implementation |
| --- | --- | --- |
| `azure`, `azure-openai` | `azure_openai.py` | OpenAI-compatible branch in `unified_client.py` |
| `llm_internal_api`, `internal-api` | `llm_internal_api.py` | internal API OpenAI-compatible, Anthropic REST, or Gemini REST branch in `unified_client.py`, chosen by `api_type` |
| `openai-compatible`, `vllm` | `openai_compatible.py` | OpenAI-compatible branch in `unified_client.py` |
| `openai` | `unified.py` via `ProviderChatAdapter` | OpenAI-compatible branch in `unified_client.py` |
| `anthropic` | `unified.py` via `ProviderChatAdapter` | Anthropic SDK branch in `unified_client.py` |
| `gemini` | `unified.py` via `ProviderChatAdapter` | Gemini SDK branch in `unified_client.py` |

`unified.py` converts `ChatModelRequest` into the client call. `gemini_config.py`
only converts Gemini generation-option names between SDK and REST conventions.

The Dolphin layout transport is deliberately outside this package: see
`core/adapters/dolphin_vllm/dolphin_vllm.py`. Although it uses an
OpenAI-compatible wire protocol, it is not an OpenAI model adapter.

The adapter API and the provider request behavior are intentionally kept stable:
this directory's local refactoring must not change prompts, payloads, retry and
timeout defaults, streaming, request count, concurrency, or SDK call paths.

Gemini requires the configured `base_url` and uses `timeout_seconds` in SDK
HTTP options (milliseconds). Anthropic disables SDK retries so the unified
client owns retry attempts. Internal REST errors retain HTTP status only.

OpenAI chat requests do not inject `temperature`; explicit unsupported sampling
options are rejected using registered capabilities. Whole-page requests use an
`output` body schema. Streams with no terminal reason retry within the configured
limits. Completed empty text and schema-valid empty required bodies also retry
within those limits; explicit abnormal finishes and schema failures remain failures.
Usage metadata retains filtered failure codes without provider messages.


See [LLM/VLM prompts, reasoning, accounting and security](../../../docs/llm-inference.md) for additional requests, exact model capability registration, partial costs and offline replay.

Usage collection is independent of optional pricing. Pass an explicit `pricing_snapshot` to calculate costs; no default price file is loaded. Accounting failures preserve provider results and do not cause another paid request.

Built-in capability rules load once at first lookup. A missing/invalid table leaves basic unknown-model calls available and emits a safe diagnostic; unsupported explicit reasoning still fails before transport. Operator capability files load strictly with `CapabilityRegistry.from_path(..., include_defaults=True)` to retain other built-in identities. See [capability usage](../../../docs/llm-inference.md#model-capabilities-and-operator-extensions).

The built-in table is `resources/model_capabilities.yaml`, read by `importlib.resources`. The project maintains and ships these rules independently of cwd/configs. The minimal advanced example is `configs/optional/model_capabilities.example.yaml`; it is not automatically applied. Basic unknown-model requests need no entry when reasoning is omitted or provider_default.
