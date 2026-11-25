# Router EfficientNet B0 checkpoints

[한국어](../../docs/kor/router-models.md)

Copyright (c) 2026 Hyundai Motor Group.

The three HMG-Doc Parser router checkpoints in this directory are released under
[Apache License 2.0](LICENSE). You may use them for commercial and non-commercial
purposes, modify or fine-tune them, and redistribute original or modified weights
subject to the license terms. No separate permission from the project is required
for uses covered by this license.

## Checkpoints

| File | Architecture | Purpose |
| --- | --- | --- |
| `binary_router.pth` | EfficientNet B0 | Stage 1 page routing. |
| `second_stage_fig.pth` | EfficientNet B0 | Stage 2 figure/image routing. |
| `second_stage_tab.pth` | EfficientNet B0 | Stage 2 table routing. |

The router instantiates `torchvision.models.efficientnet_b0(weights=None)` and
loads the checkpoint state with its classifier head. Files, byte sizes, SHA-256,
and licensing metadata are recorded in [the asset register](../../docs/assets/manifest.json).
See [local router setup](../../docs/optional-capabilities.md#optional-local-router)
for dependencies, checkpoint overrides, and the loopback server.

## Redistribution and attribution

Include this [LICENSE](LICENSE) and [NOTICE](NOTICE) when redistributing these
weights. Retain applicable copyright and attribution notices, and identify
modified files as required by Apache-2.0. Dependencies and unrelated models or
datasets retain their own license conditions.

The checkpoints are provided on an **AS IS** basis, without warranties or
conditions of any kind. No trademark permission or accuracy guarantee is granted.
Refer to the license for the full rights, patent, redistribution, and liability
terms. Only load trusted checkpoint files; a checksum verifies byte identity,
not serialization safety or suitability for your documents.
