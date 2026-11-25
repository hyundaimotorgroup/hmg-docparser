# Model and data assets

[한국어](kor/model-and-data-assets.md)

The [parser license](../LICENSE) covers parser code. Models, dictionaries,
source PDFs, images, and derived facts need their own source and rights records.
Public availability or pseudonymization alone does not establish redistribution
permission. Downloaded models and bundled files have separate conditions.

## Model choices

| Model | Conditions | Integration |
| --- | --- | --- |
| [PP-DocLayoutV3](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3) | Model card lists Apache-2.0; commercial recommendation | Compatible layout adapter required; not in supplied profiles or reported benchmark scores. |
| [Dolphin 1.5](https://huggingface.co/ByteDance/Dolphin-1.5) | Model card lists MIT | Local FastAPI tutorial; download or `DOLPHIN_15_MODEL`. The [historical demo MIT notice](../third_party/licenses/Dolphin-1.5-demo-MIT.txt) is preserved separately. |
| [Dolphin v2](https://huggingface.co/ByteDance/Dolphin-v2) | [Qwen research license](https://huggingface.co/ByteDance/Dolphin-v2/blob/main/LICENSE): non-commercial research/evaluation; separate commercial license | vLLM/provider integration and benchmark configuration 1. |
| Paddle [mobile detection](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det) and [Korean recognition](https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec) | Model cards list Apache-2.0 | Tutorial downloads models and dictionary; Triton is operator-managed. |
| [Router EfficientNet B0 classifiers](../models/router/README.md) | Apache-2.0; Copyright (c) 2026 Hyundai Motor Group. Commercial use, modification, and redistribution permitted under the license. | Three bundled `.pth` files with [LICENSE](../models/router/LICENSE) and [NOTICE](../models/router/NOTICE). |
| LLM/VLM | Provider terms or separately licensed self-hosted weights | YAML IDs do not grant access or establish retention, licensing, cost, or compatibility. |

Record downloaded revisions, license copies/notices, checksums, and commercial
permission where required. Different upstream revisions can have different
licenses. Caches are separate from parser source. Only load trusted checkpoints.

## Referenced code and dependencies

Reviewed dependency names, versions, sources, copyright notices, and full license
texts are in [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES). Include that file and
[LICENSE](../LICENSE) when publishing the source code.

| Material | Source and notice |
| --- | --- |
| Dolphin 1.5 demo | [Referenced revision](https://github.com/bytedance/Dolphin/blob/b6c7978ffd/demo_page.py); MIT, Copyright 2025 ByteDance Ltd. and/or its affiliates. [MIT notice preserved](../third_party/licenses/Dolphin-1.5-demo-MIT.txt). |
| PaddleOCR | [Project](https://github.com/PaddlePaddle/PaddleOCR), [Apache-2.0](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE). Downloaded [Korean dictionary](https://github.com/PaddlePaddle/PaddleOCR/blob/main/ppocr/utils/dict/ppocrv5_korean_dict.txt) retains its upstream conditions. |
| TOON | [Format specification](https://github.com/toon-format/toon) for optional table output. |
| py-toon-format 0.1.0 | [Python implementation](https://github.com/ErtugrulKra/py-toon-format), [MIT package metadata](https://pypi.org/project/py-toon-format/0.1.0/). Preserve distribution notices when repackaging it. |
| pypdfium2/PDFium | [Project](https://github.com/pypdfium2-team/pypdfium2), [licensing](https://pypdfium2.readthedocs.io/en/stable/readme.html#licensing). The binding, PDFium, and bundled dependencies have separate notices. Preserve the licenses shipped with the actual build when redistributing binaries. |

## Router checkpoint license

The three bundled EfficientNet B0 router weights are released under Apache-2.0,
including commercial use, fine-tuning, and redistribution. Retain the supplied
license and notices and mark modifications. See [router model documentation](../models/router/README.md)
for scope and full conditions. Other models and sample datasets retain their
separately documented conditions.

## Bundled register

[assets/manifest.json](assets/manifest.json) records paths, byte sizes, SHA-256,
and source/rights fields. `not_recorded` means no asset-specific permission record
accompanies a file. Null source/owner/license fields state unavailable evidence;
they are not redistribution permission.

| Group | Files and purpose |
| --- | --- |
| Router | `models/router/binary_router.pth`, `second_stage_fig.pth`, `second_stage_tab.pth`: page/element classification. |
| Input sample | `inputs/test_KIA_EV9_price.pdf`. |
| Tutorial inputs | `tutorial/dolphin_15_fastapi/layout_smoke_page.png`, `tutorial/paddle_ocr_fastapi/paddle_test.png`. |
| Evaluation PDFs | `tools/eval/dp_evalset_simple.pdf`, `dp_evalset_design.pdf`, `dp_evalset_external.pdf`: public-release candidate datasets. |
| Evaluation facts | `tools/eval/*_gt.md`, `fact_dict_*.pkl`: reference facts; `eval_prompt.md`: judge prompt/example. |

Files are included in this source tree, but inclusion is not proof of permission.
Before republishing them or outputs, record original source, creator/owner,
license, permission scope, modifications, and disclosure review, or exclude the
asset. Derived Markdown, crops, and facts may retain source content. Internal
general/manufacturing benchmarks are not offered as public datasets.

## Integrity and safe use

Verify registered bytes from the repository root without loading models/pickle:

```bash
python - <<'PY'
import hashlib
import json
from pathlib import Path

manifest = json.loads(Path("docs/assets/manifest.json").read_text())
for asset in manifest["assets"]:
    path = Path(asset["path"])
    if (hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]
            or path.stat().st_size != asset["bytes"]):
        raise SystemExit(f"Asset mismatch: {path}")
print("All registered assets match")
PY
```

Hashes establish byte identity, not rights or safe serialization. Router `--check`
checks existence only. Update metadata with replacement bytes and do not silently
change a regression baseline. See [evaluation](../tools/eval/README.md),
[data handling](privacy-and-data-handling.md), and [release checks](release-checklist.md).
