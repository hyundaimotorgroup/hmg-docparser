[eng](../../README.md)

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

## 개요
PDF를 markdown으로 변환해주는 파서

한국어 업무 문서 처리에 초점을 둔 PDF 파서입니다. 텍스트·표·이미지를 추출해 구조화된 마크다운으로 만듭니다.

검색과 RAG 챗봇을 위해 한국어 문서 파싱과 Markdown 출력을 중심으로 개발합니다. 폭넓은 언어 지원, 범용 문서 변환, IOU 등 CV 관점의 성능은 목표로 두지 않습니다.

## 접근법

현대의 문서 파서는 각 추출 방식에 따라 한계가 있습니다. OCR은 표 구조 복원에 약하고, VLM은 텍스트가 Dense한 이미지에서 세부 정보를 놓칠 수 있습니다. PDF 내부 구조를 읽는
룰 기반 추출은 문서 구조와 레이아웃의 다양성에 대응하는 데 한계가 있습니다. 이러한 한계를 보완하기 위해 여러 추출 방식을 조합한 파이프라인을 구성했습니다.

- 네이티브 PDF 파서만으로 내용 추출이 충분한 경우에는 네이티브 PDF 파서만 사용합니다.
  그 외에는 스캔본의 텍스트를 OCR로 인식하고 표·이미지를 VLM으로 해석합니다.
  조합 방식은 프로필에 따라 다릅니다.
- 라우터 프로필은 초경량 분류 모델로 페이지·요소의 난이도를 판단해 처리 경로와
  VLM 등급을 선택합니다. 요소 분석 단계에서는 필요한 요소만 VLM에 전달해
  불필요한 호출과 비용을 줄입니다.
- 독립적인 분기와 페이지를 병렬 처리해 파싱 시간을 줄입니다.
  YAML의 `resource_budget.scheduler_max_workers`와 노드별 `max_concurrency`로
  CPU·GPU 자원과 엔드포인트 처리 용량에 맞춰 병렬 수준을 조절할 수 있습니다.
  [설정 안내](configuration.md#최상위-계약)를 참고하세요.
- 이미지는 파일명을 자동 생성해 저장하고 Markdown에서 참조합니다.
  표 출력은 Markdown·HTML·JSON·TOON을 지원합니다.
- 별도 파이프라인으로 Markdown을 Confluence(SaaS버전) HTML로 변환하고 페이지와 첨부 파일을
  업로드할 수 있습니다.

## 성능

`gpt-5.4-mini`를 평가 LLM으로 사용해 문서의 사실 단위 정보 보존율을 측정했습니다. 점수는 기준 사실 중 파싱 결과에 올바르게 보존되었다고 판단된 사실의 비율이며,
정보 누락과 모순을 함께 고려합니다.(0–1, 높을수록 좋음).

| 평가셋 | 내용 | 오픈소스 공개여부 | ours<br>(설정1) | ours<br>(설정2) | mineru-2.5-pro<br>(advanced xhigh) | infinity-parser-v2-pro<br>(bf16) |
| --- | --- | --- | --- | --- | --- | --- |
| dp_evalset_general.pdf | 평이한 난이도.<br>경영 리포트, 정비 매뉴얼, 가격표, 스캔된 프레젠테이션 슬라이드 | 내부 벤치마크 (비공개) | 0.983 | 0.968 | 0.978 | **0.988** |
| dp_evalset_manufacturing.pdf | 초고난이도.<br>복잡한 제조 문서, 제조 프로세스가 포함됨 | 내부 벤치마크 (비공개) | **0.84** | 0.783 | 0.747 | 0.792 |
| dp_evalset_simple.pdf | 쉬운 난이도. ebook | 공개 | **0.998** | **0.998** | 0.988 | 0.942 |
| dp_evalset_design.pdf | 어려운 난이도. 가명화된 디자인 설계 및 리뷰 문서 | 공개 | **0.96** | 0.798 | 0.841 | 0.821 |
| dp_evalset_external.pdf | 어려운 난이도.<br>전통적인 파서에서 어려워하는 하드셋 샘플들 모음 | 공개 | **0.882** | 0.87 | 0.748 | 0.688 |

포함된 평가 세트 3개는 소스 트리의 자산입니다. [출처·재배포 기록](model-and-data-assets.md)은 파서 코드 라이선스와 별도로 적용됩니다.

* 설정1: default.yaml 파이프라인. `router: on`, `layout_parser: dolphin-v2`, `light_vlm: gpt-5.4-mini`, `medium_vlm: gemini-3.5-flash`, `heavy_vlm: gemini-3.1-pro-preview`
* 설정2: `layout_parser: dolphin-v1.5`, 이외 위와 동일

평가를 실행하려면 [tools/eval](../../tools/eval)의 공개 평가셋과 정답 사실을 참고하세요. 평가 프롬프트와 코드는 [eval_prompt.md](../../tools/eval/eval_prompt.md)에 있습니다. 내부 벤치마크 데이터셋은 공개하지 않습니다.

### 처리 비용·속도와 모델 공개 계획

HMG Doc Parser는 현재 상용 VLM을 활용하기 때문에 토큰 비용이 청구됩니다. 처리 비용은 문서 난이도에 따라 페이지당 약 **0.01–0.03 USD**입니다.
(상용 도큐먼트 파싱 모델의 비용은 일반적으로 페이지당 약 **0.01–0.06 USD** 수준입니다.)

설정1, max_worker 8, NVIDIA L4 GPU 환경에서 126페이지 문서 처리에 2분 4초가 소요되었습니다.

> 자체 학습 모델을 통해 파싱 비용을 낮추는 것을 목표로 하며, 커뮤니티에서 활용할 수 있도록 모델 공개 계획을 수립하고 있습니다.

## 권장 설정

**아래 네 가지 파이프라인 모두 이미지 입력을 지원하는 VLM 엔드포인트가
필수입니다. 로컬 퀵스타트도 VLM 연결이 필요합니다.** API 또는 직접 운영하는
서비스를 사용하며, 레이아웃·OCR을 로컬에서 실행하더라도 VLM을 준비해야 합니다.

| 구성 요소 | 권장 모델 |
| --- | --- |
| 상업적 활용용 레이아웃 파서 | [PP-DocLayoutV3](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3) (Apache 2.0) |
| 레이아웃 파서 | Dolphin v2 (3B), 벤치마크 설정1에 사용 |
| OCR | PaddleOCR v5 mobile: `PP-OCRv5_mobile_det` + `korean_PP-OCRv5_mobile_rec` |
| Heavy VLM | `gemini-3.1-pro` 이상 |
| Medium VLM | `gemini-3.8-flash` 이상 |
| Light VLM | `gpt-6-luna` 이상 |

※ dolphin-v2는 연구용으로만 활용할 수 있습니다. 상업적 활용에는 PP-DocLayoutV3 활용을 고려하세요.

### 설정1 기준 권장 사양

| 항목 | 권장 사양 |
| --- | --- |
| GPU | CUDA를 지원하는 NVIDIA GPU, VRAM 16 GB 이상. 큰 페이지나 동시 요청을 처리한다면 24 GB 권장 |
| 시스템 메모리 | RAM 32 GB 이상 |
| 저장 공간 | 모델 파일·캐시·실행 의존성을 위한 SSD 여유 공간 20 GB 이상 |
| 실행 환경 | Linux, 호환되는 NVIDIA 드라이버, 모델의 Qwen2.5-VL 아키텍처를 지원하는 vLLM 버전 |
| VLM 연결 | 필수: 이미지 입력을 지원하는 API 또는 자체 VLM 엔드포인트. 위 GPU 사양에는 VLM을 직접 운영할 자원이 포함되지 않습니다. |

권장 설정은 목표 모델 조합이며, 제공된 YAML 프로필의 현재 기본값과는 차이가
있습니다. 이미지 입력과 파서의 요청 형식을 지원하는 모델·엔드포인트를
선택하세요. `LOCAL` 프로필 3개는 하나의 OpenAI 호환 API 주소를 공유하므로,
이 경로에서 Gemini 모델을 사용하려면 호환 게이트웨이가 필요합니다.
[VLM 역할](configuration.md#vlm-역할)과 [제공자 모델 지정](providers.md#모델-지정)을 참고하세요.

## 파이프라인

네 가지 기본 선택지에서 시작하거나 커스텀 DAG를 구성할 수 있습니다.

| 파이프라인 | 용도 | 설정 파일 |
| --- | --- | --- |
| 로컬 퀵스타트 | 저사양 컴퓨터에서도 CPU로 실행할 수 있는 구성. PDF 내장 텍스트 추출, 로컬 Dolphin 1.5·PaddleOCR, VLM API를 함께 사용합니다. CPU 추론은 느릴 수 있습니다. | [`local_quickstart.yaml`](../../configs/local_quickstart.yaml) |
| 기본 | 비전 추출과 VLM 중심 구성. 난이도 라우팅, 레이아웃·OCR, 표·이미지 해석, Stage 1 L1을 제외한 전역 문맥 보정을 사용합니다. | [`default.yaml`](../../configs/default.yaml) |
| 그룹사 전용 | 그룹사 VLM 서비스와 GPU 자원을 활용한다는 전제로 만든 구성. 사용하려면 개발자에게 직접 문의하세요: [mccartney@hyundai.com](mailto:mccartney@hyundai.com). | [`group_internal.yaml`](../../configs/group_internal.yaml) |
| Beta | Heavy VLM 사용을 없애 LLM 비용을 더 절감하고, 블록별 역할 분담을 통해 환각을 줄이도록 설계한 파이프라인입니다. beta 버전입니다. | [`beta.yaml`](../../configs/beta.yaml) |

### 커스텀 파이프라인

YAML 설정 파일에 노드와 의존 관계를 DAG로 정의하고 실행합니다.

```bash
python main.py configs/my_pipeline.yaml
```

기존 노드를 조합하거나 [`Node` 인터페이스](../../core/interfaces/node.py)를
상속해 직접 노드를 만들 수 있습니다. 예를 들어 다음 페이지 노드는 DTO와
메타데이터를 유지하면서 Markdown 앞뒤 공백을 정리합니다.

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

새 노드는 [`register_node_by_name`](../../core/engine/registry/bootstrap.py)에,
설정 스키마는 [`node_config.py`](../../core/engine/config/node_config.py)에 등록합니다.
연결하는 노드의 DTO 유형·목록 여부·실행 범위를 맞추면 서로 조합할 수 있습니다.
위 예제는 YAML에서 `execution_scope: page`,
`input`/`output: {type: page_markdown_dto@v1, is_list: true}`로 선언하며,
런타임이 페이지마다 한 번씩 호출합니다. [설정 안내](configuration.md)와
[노드 추가 방법](development.md#노드-추가와-변경)을 참고하세요.

[설정 검증 UI](optional-capabilities.md#로컬-설정-편집기)에서 DAG를 그리고 수정하며,
DTO 연결·컴파일을 검증한 뒤 YAML로 내보낼 수 있습니다.
`python tools/config_editor.py`로 시작하고
[http://127.0.0.1:8765](http://127.0.0.1:8765)를 여세요.

## 설치와 빠른 시작

- [Installation · 설치](installation.md): 파서 설치와 YAML 파이프라인 검증
- [Quickstart · 빠른 시작](quickstart.md): 엔드포인트 설정, 서비스 시작, PDF 파싱

실행 방법이 잘 모르겠다면
[`verify_local_quickstart_clean_conda.sh`](../../scripts/verify_local_quickstart_clean_conda.sh)를
참고해 로컬 파이프라인을 실행하세요. 더 자세한 내용은 [빠른 시작 문서](quickstart.md)를 읽어보세요.

선택한 파이프라인에 맞춰 빠른 시작 안내를 따라 실행하세요. 자체 운영
엔드포인트용 `configs/managed_endpoints.yaml`은 기본 DAG에 본인의 서비스를
연결하는 설정입니다. CLI는 로컬에서 실행되며 설정된 출력 디렉터리에
Markdown과 이미지를 저장합니다.

## 문서 안내

| 안내 | 링크 |
| --- | --- |
| 설정과 엔드포인트 | [YAML 설정](configuration.md) · [제공자](providers.md) |
| 구조와 개발 | [아키텍처](architecture.md) · [개발 안내](development.md) |
| 선택 기능 | [라우터, 설정 편집기, Langfuse, Confluence](optional-capabilities.md) |
| 평가 | [평가 안내](evaluation.md) |

## 기여
프로젝트에 기여를 환영합니다.
기여하기 전에 다음 문서를 확인해 주세요.

- [CONTRIBUTING.md](../../.github/CONTRIBUTING.md)
- [CLA-KOR.md](https://github.com/hyundaimotorgroup/.github/blob/main/legal/CLA-KOR.md)
- [CLA-ENG.md](https://github.com/hyundaimotorgroup/.github/blob/main/legal/CLA-ENG.md)

CLA 검증이 활성화되어 있는 경우, Pull Request가 병합되기 전에 기여자에게 Contributor License Agreement (CLA) 절차의 완료가 요구될 수 있습니다.

## 프로젝트 정책

- 행동 강령: [CODE_OF_CONDUCT.md](../../.github/CODE_OF_CONDUCT.md)
- 보안 정책: [SECURITY.md](../../.github/SECURITY.md)

## 지원
새로운 Issue를 생성하기 전에 기존 Issue를 검색하여 중복된 내용이 없는지 확인해 주세요.

버그 신고 및 기능 요청:
- [GitHub Issues](https://github.com/hyundaimotorgroup/hmg-doc-parser/issues)
- [Issue Templates](../../.github/ISSUE_TEMPLATE/)

보안 관련 문의:
- [SECURITY.md](../../.github/SECURITY.md)의 안내를 따라주세요.

## 릴리스
릴리스 노트 및 버전 이력은 다음 위치에서 확인할 수 있습니다.
- [CHANGELOG.md](./CHANGELOG.md)
- [GitHub Releases](https://github.com/hyundaimotorgroup/hmg-doc-parser/releases)

이 프로젝트의 버전 표기는 [Semantic Versioning](https://semver.org/)를 따릅니다.

## 라이선스

파서 코드와 동봉 EfficientNet B0 라우터 가중치 세 개는 [Apache-2.0](../../LICENSE)으로
배포합니다. Copyright (c) 2026 Hyundai Motor Group.
제3자 라이선스는 [THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES), 모델·샘플의 조건은
[모델·데이터 자산](model-and-data-assets.md)에 있습니다.

## 감사의 글

선택적 표 형식의 [TOON](https://github.com/toon-format/toon)과 실제 Python 구현체
[py-toon-format](https://github.com/ErtugrulKra/py-toon-format), 레이아웃 분석의
[Dolphin](https://github.com/bytedance/Dolphin), 한국어 OCR의
[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) 유지관리자·기여자에게 감사드립니다.
