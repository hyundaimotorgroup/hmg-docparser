# HTTP input and resource limits

[한국어](kor/http-input-limits.md)

These settings apply to the config editor and local Router/Dolphin/Paddle HTTP
services. Supplied entrypoints bind to loopback. A public service deployment
needs separate authentication, address/origin, and proxy policies;
see [security](../.github/SECURITY.md).

## Defaults

MiB means 1,048,576 bytes. Request limits include JSON/base64 or multipart framing.
The existing router client normally batches 16 images with four concurrent requests.

| Suffix | Router (`ROUTER_`) | Dolphin (`DOLPHIN_15_`) | Paddle (`PADDLE_OCR_`) |
| --- | --- | --- | --- |
| `MAX_REQUEST_BYTES` | 536870912 (512 MiB) | 134217728 (128 MiB) | 134217728 (128 MiB) |
| `MAX_IMAGE_BYTES` | 67108864 (64 MiB), per file | 67108864, decoded base64 | 67108864, decoded base64 |
| `MAX_IMAGE_PIXELS` | 128000000, per image | 128000000 | 128000000 |
| `MAX_BATCH_PIXELS` | 256000000, per request | Not applicable | Not applicable |
| `MAX_IMAGES` | 128, per request | Single-image API | Single-image API |
| `MAX_PROMPT_CHARS` | Not applicable | 65536 characters | Not applicable |
| `MAX_CONCURRENT_REQUESTS` | 8 | 8 | 8 |
| `MAX_QUEUED_REQUESTS` | 64 | 64 | 64 |
| `READ_TIMEOUT_SECONDS` | 900 | 900 | 900 |

Combine prefix and suffix, for example `ROUTER_MAX_IMAGES`. Pixel budgets are
checked before RGB expansion. Pillow's own large-image protection remains active
and may reject an image before an application-specific limit.

Model-server active/queued limits apply per application worker. Queued requests
do not collect/decode their bodies in the application; OS, ASGI, and proxy buffers
are separate. An active slot covers receiving, decoding, model-lock waiting, and
inference. Body read timeout starts after acquiring a slot and is not an inference
timeout. Multiple workers increase aggregate concurrency.

| Editor variable | Default |
| --- | --- |
| `CONFIG_EDITOR_MAX_REQUEST_BYTES` | 2000000 |
| `CONFIG_EDITOR_MAX_YAML_DEPTH` | 128 |
| `CONFIG_EDITOR_MAX_YAML_NODES` | 100000 |
| `CONFIG_EDITOR_MAX_YAML_ALIASES` | 10000 |
| `CONFIG_EDITOR_MAX_EXPANDED_NODES` | 1000000 |
| `CONFIG_EDITOR_MAX_EXPANDED_BYTES` | 67108864, conservative expansion estimate |
| `CONFIG_EDITOR_MAX_CONCURRENT_REQUESTS` | 8, connection slots |
| `CONFIG_EDITOR_MAX_QUEUED_REQUESTS` | 64, waiting connections |
| `CONFIG_EDITOR_READ_TIMEOUT_SECONDS` | 120, socket read wait |

The editor bounds depth/alias expansion and rejects cyclic aliases and values
not representable as JSON. It uses SafeLoader and rejects executable YAML tags.

## Configuration and responses

Set environment variables before server startup and restart the server to apply
them. Limit values are nonnegative integers; `0` disables that application limit.
`MAX_CONCURRENT_REQUESTS=0` disables concurrency/queue gating. Retain appropriate
bounds for your workload and host resources.

```bash
ROUTER_MAX_IMAGES=32 ROUTER_MAX_BATCH_PIXELS=64000000 python tools/serve_router.py
```

Malformed inputs return 400 in editor/Router/Dolphin and 422 in Paddle. Exceeded
body/image/pixel/batch/prompt limits return 413. Full queues return 503 with
`Retry-After: 1`; body read timeout returns 408. Editor YAML structure/expansion
limit violations return 400. These budgets do not guarantee total memory or
CPU/GPU inference cost. Coordinate them with host and proxy limits.

## Offline regression

The [HTTP test file](../tests/test_http_input_security.py) patches model startup
and checks invalid inputs, limits, queues, and recovery without loading weights:

```bash
python -m pytest tests/test_http_input_security.py -q
```

Install parser dependencies plus pytest, httpx, and truststore as described in
[development](development.md). This is an HTTP-contract check, not a live-model
or complete-parser test.
