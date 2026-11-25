# HMG-Doc Parser

<p align="left">
  <img src="https://img.shields.io/badge/status-active-brightgreen.svg" alt="active" />
   <img
   src="https://img.shields.io/badge/version-v1.0.0-green.svg"
   alt="Version: v1.0.0"/>
  <a href="https://opensource.org/licenses/Apache-2.0">
    <img
      src="https://img.shields.io/badge/License-Apache%202.0-blue.svg"
      alt="License: Apache 2./badge/version-1.0.0-blue.svg"/>
  </a>

</p>


## Overview

A PDF-to-Markdown parser.

A PDF parser focused on Korean business documents. It extracts text, tables,
and images into structured Markdown.

The project focuses on Korean document parsing and Markdown output for search
and RAG chatbots. Broad language coverage, general-purpose document conversion,
and computer vision metrics such as IoU are outside its goals.

[한국어](docs/kor/README.md)

## Approach

Modern document parsers face limitations with each extraction method: OCR
struggles to recover table structure, VLMs can miss details in images with dense
text, and rule-based extraction from PDF internals struggles with varied document
structures and layouts. The pipelines combine these methods to address their
respective limitations.

- Use only a native PDF parser when it can sufficiently extract the content.
  Otherwise, use OCR for scanned text and VLMs for table and image interpretation.
  The combination depends on the profile.
- Router profiles use lightweight classifiers to select processing paths and
  VLM tiers by page and element difficulty. Element analysis sends only the
  required elements to VLMs, reducing unnecessary calls and cost.
- Independent branches and pages run in parallel to reduce parsing time.
  Adjust `resource_budget.scheduler_max_workers` and per-node `max_concurrency`
  in YAML to match available CPU/GPU resources and endpoint capacity. See
  [configuration](docs/configuration.md#top-level-contract).
- Save images with generated filenames and Markdown references. Tables support
  Markdown, HTML, JSON, and TOON output.
- A separate pipeline converts Markdown to Confluence Cloud (SaaS) HTML and
  uploads pages and attachments.

## Performance

Scores measure fact-level information preservation using `gpt-5.4-mini` as an
LLM judge. Each score is the proportion of reference facts judged to be correctly
preserved in the parsed output, accounting for missing or contradictory
information (0–1; higher is better).

| Evaluation set | Contents | Public availability | ours<br>(conf.1) | ours<br>(conf.2) | mineru-2.5-pro<br>(advanced xhigh) | infinity-parser-v2-pro<br>(bf16) |
| --- | --- | --- | --- | --- | --- | --- |
| dp_evalset_general.pdf | Moderate difficulty.<br>Business reports, maintenance manuals, price lists, and scanned presentation slides | Internal benchmark (not publicly available) | 0.983 | 0.968 | 0.978 | **0.988** |
| dp_evalset_manufacturing.pdf | Extremely difficult.<br>Complex manufacturing documents, including manufacturing processes | Internal benchmark (not publicly available) | **0.84** | 0.783 | 0.747 | 0.792 |
| dp_evalset_simple.pdf | Easy. ebook | Public | **0.998** | **0.998** | 0.988 | 0.942 |
| dp_evalset_design.pdf | Difficult. Pseudonymized design specifications and review documents | Public | **0.96** | 0.798 | 0.841 | 0.821 |
| dp_evalset_external.pdf | Difficult.<br>A collection of challenging samples for traditional parsers | Public | **0.882** | 0.87 | 0.748 | 0.688 |

The three included evaluation sets are source-tree assets; their
[origin and redistribution records](docs/model-and-data-assets.md) apply separately
from the parser code license.

- Configuration 1: the `default.yaml` pipeline. `router: on`, `layout_parser: dolphin-v2`, `light_vlm: gpt-5.4-mini`, `medium_vlm: gemini-3.5-flash`, `heavy_vlm: gemini-3.1-pro-preview`.
- Configuration 2: `layout_parser: dolphin-v1.5`; all other settings are the same as Configuration 1.

To run the evaluation, refer to [tools/eval](tools/eval) for the public evaluation
sets and ground-truth facts, and [eval_prompt.md](tools/eval/eval_prompt.md) for the
evaluation prompt and code. Internal benchmark datasets will not be publicly
released.

### Processing cost, speed and model plans

HMG-Doc Parser currently uses commercial VLMs, which incur token charges.
Processing costs approximately **USD 0.01–0.03 per page**, depending on document
complexity. (Commercial document parsing models typically cost approximately
**USD 0.01–0.06 per page**.)

With Configuration 1, max_worker 8, and an NVIDIA L4 GPU, a 126-page document
was processed in 2 minutes 4 seconds.

> We aim to reduce parsing costs with models we train ourselves and are developing
> plans to make these models publicly available for the community.

## Recommended settings

**An image-capable VLM endpoint is required for all four pipeline choices
below, including the local quickstart.** Use an API or a self-hosted service;
running layout and OCR locally does not remove this requirement.

| Component | Recommendation |
| --- | --- |
| Layout parser for commercial use | [PP-DocLayoutV3](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3) (Apache 2.0) |
| Layout parser | Dolphin v2 (3B), as used in benchmark configuration 1 |
| OCR | PaddleOCR v5 mobile: `PP-OCRv5_mobile_det` + `korean_PP-OCRv5_mobile_rec` |
| Heavy VLM | `gemini-3.1-pro` or better |
| Medium VLM | `gemini-3.8-flash` or better |
| Light VLM | `gpt-6-luna` or better |

Dolphin v2 is available for research use only. Consider PP-DocLayoutV3 for
commercial use.

### Recommended hardware for Configuration 1

| Resource | Recommended specification |
| --- | --- |
| GPU | CUDA-compatible NVIDIA GPU with at least 16 GB VRAM; 24 GB preferred for larger pages or concurrent requests |
| System memory | At least 32 GB RAM |
| Storage | At least 20 GB of free SSD space for model files, caches, and runtime dependencies |
| Runtime | Linux, a compatible NVIDIA driver, and a vLLM version supporting the model's Qwen2.5-VL architecture |
| VLM access | Required: an image-capable API or self-hosted VLM endpoint; the layout-server GPU specification does not include VLM hosting |

The recommendations describe the target model combination; the supplied YAML
profiles retain their current defaults. Select image-capable models and an
endpoint that supports each model and the parser's request format. The three
`LOCAL` profiles share one OpenAI-compatible API URL; using Gemini models there
requires a compatible gateway. See [VLM roles](docs/configuration.md#vlm-roles)
and [provider model assignments](docs/providers.md#model-assignments).

## Pipelines

Choose one of four starting points, or build a custom DAG:

| Pipeline | Intended use | Config |
| --- | --- | --- |
| Local quickstart | A CPU-capable option for lower-spec computers. Combines native PDF text extraction with local Dolphin 1.5/PaddleOCR and a VLM API. CPU inference can be slow. | [`local_quickstart.yaml`](configs/local_quickstart.yaml) |
| Default | Vision extraction and VLM processing, with difficulty routing, layout/OCR, table/image interpretation, and global-context refinement for pages outside `skip_levels: [1]`. | [`default.yaml`](configs/default.yaml) |
| Group companies | Designed for access to group-company VLM services and GPU resources. Contact the developer at [mccartney@hyundai.com](mailto:mccartney@hyundai.com) to use this setup. | [`group_internal.yaml`](configs/group_internal.yaml) |
| Beta | Designed to further reduce LLM costs by eliminating heavy VLMs and reduce hallucinations through role-specific processing of individual blocks. This pipeline is in beta. | [`beta.yaml`](configs/beta.yaml) |

### Custom pipelines

Describe nodes and their dependencies in a YAML DAG, then run it:

```bash
python main.py configs/my_pipeline.yaml
```

Reuse existing nodes or inherit the [`Node` interface](core/interfaces/node.py)
to implement your own. For example, this page node trims Markdown while
preserving its DTO and metadata:

```python
from dataclasses import replace
from core.domain.markdown.models import PageMarkdownDTO
from core.interfaces.node import Node, NodeContext, NodeResult

class TrimMarkdownNode(Node):
    node_name = "trim_markdown"
    input_type = output_type = "page_markdown_dto@v1"
    is_page_parallel = True

    def run(self, context: NodeContext, value: object) -> NodeResult:
        if not isinstance(value, PageMarkdownDTO):
            raise TypeError("expected PageMarkdownDTO")
        return NodeResult(value=replace(value, markdown=value.markdown.strip()))
```

Register the node in [`register_node_by_name`](core/engine/registry/bootstrap.py)
and its configuration schema in [`node_config.py`](core/engine/config/node_config.py).
Connect it in YAML with matching DTO types, list cardinality, and execution
scope. For this example, use `execution_scope: page` and
`input`/`output: {type: page_markdown_dto@v1, is_list: true}`; the runtime calls
it once per page. See [configuration](docs/configuration.md) and
[adding a node](docs/development.md#adding-or-changing-a-node).

The [config validation UI](docs/optional-capabilities.md#local-config-editor)
lets you draw and edit the DAG, check DTO connections and compilation, and
export YAML. Start it with `python tools/config_editor.py`, then open
[http://127.0.0.1:8765](http://127.0.0.1:8765).

## Installation and quickstart

- [Installation](docs/installation.md): install the parser and validate a YAML pipeline.
- [Quickstart](docs/quickstart.md): configure endpoints, start services, and parse a PDF.

If you are unsure how to get started, use
[`verify_local_quickstart_clean_conda.sh`](scripts/verify_local_quickstart_clean_conda.sh)
as a reference for running the local pipeline. Read the
[quickstart guide](docs/quickstart.md) for more details.

Follow the quickstart instructions for your selected pipeline. For self-managed
endpoints, `configs/managed_endpoints.yaml` uses the default DAG with your own
services. The CLI runs locally and writes Markdown and image artifacts to the
configured output directory.

## Documentation

| Guide | Links |
| --- | --- |
| Configuration and endpoints | [YAML configuration](docs/configuration.md) · [Providers](docs/providers.md) |
| Architecture and development | [Architecture](docs/architecture.md) · [Development](docs/development.md) |
| Optional features | [Router, config editor, Langfuse, and Confluence](docs/optional-capabilities.md) |
| Evaluation | [Evaluation guide](tools/eval/README.md) |


## Contributing
Contributions are welcome.
Before contributing, please review:

- [CONTRIBUTING.md](.github/CONTRIBUTING.md)
- [CLA-KOR.md](https://github.com/hyundaimotorgroup/.github/blob/main/legal/CLA-KOR.md)
- [CLA-ENG.md](https://github.com/hyundaimotorgroup/.github/blob/main/legal/CLA-ENG.md)

If CLA verification is enabled, contributors may be required to complete the Contributor License Agreement (CLA) process before a pull request can be merged.

## Project Policies

- Code of Conduct: [CODE_OF_CONDUCT.md](.github/CODE_OF_CONDUCT.md)
- Security Policy: [SECURITY.md](.github/SECURITY.md)

## Support

Before creating a new issue, please search existing issues to avoid duplicates.

For bug reports and feature requests:
- [GitHub Issues](https://github.com/hyundaimotorgroup/hmg-doc-parser/issues)
- [Issue Templates](.github/ISSUE_TEMPLATE/)

For security concerns:

- Follow the instructions in [SECURITY.md](.github/SECURITY.md)

## Releases
Release notes and version history are available in the following locations:
- [CHANGELOG.md](./CHANGELOG.md)
- [GitHub Releases](https://github.com/hyundaimotorgroup/hmg-doc-parser/releases)

This project follows [Semantic Versioning](https://semver.org/).

## License
The parser code and three bundled EfficientNet B0 router checkpoints are licensed
under [Apache-2.0](LICENSE).
Third-party licenses are in [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES); model and
sample conditions are in [model and data assets](docs/model-and-data-assets.md).

## Acknowledgements

We thank the maintainers and contributors of the following open-source projects
for their work:

- [TOON](https://github.com/toon-format/toon): the format used for optional TOON table output.
- [py-toon-format](https://github.com/ErtugrulKra/py-toon-format): the Python implementation used for TOON output.
- [Dolphin](https://github.com/bytedance/Dolphin): document parsing models used for layout analysis.
- [PaddleOCR](https://github.com/PADDLEPADDLE/PADDLEOCR): OCR models used for text detection and recognition, including Korean text.
