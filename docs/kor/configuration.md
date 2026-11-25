# 네이티브 YAML 설정

> 원문: [configuration.md](../configuration.md). 한국어 번역본입니다.

`python main.py configs/local_quickstart.yaml`처럼 설정 경로를 `python main.py`에 전달합니다. CLI는 기존 셸 환경변수를 덮어쓰지 않으면서 `.env`를 읽습니다. 문자열 전체가 `${NAME}`이면 해당 변수가 필요하며 빈 값은 그대로 유지합니다. `${NAME:-default}`는 변수가 없거나 비어 있으면 기본값을 사용합니다. `${VISION_KEY:-${TEXT_KEY}}`처럼 다른 변수도 기본값으로 참조할 수 있습니다. 비밀값은 YAML이 아닌 비공개 환경에 보관하세요. 오프라인 컴파일 검사는 [설치 안내](installation.md)를 참고하세요.

`.env`와 `.env.example`에는 연결 주소·인증정보와 모델 설정을 함께 둡니다. default·managed_endpoints·local_quickstart는 `provider: openai`로 `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_API_KEY`를 텍스트와 모든 VLM 단계에서 공유합니다. 기본 주소는 `https://api.openai.com/v1`이며 로컬 추론 서버를 쓰려면 해당 서버의 OpenAI 호환 URL로 변경하세요. 모델은 `LOCAL_LLM_MODEL`, `LOCAL_LIGHT_VLM_MODEL`, `LOCAL_MEDIUM_VLM_MODEL`, `LOCAL_HEAVY_VLM_MODEL`에서 지정합니다.

group_internal과 beta는 `LLM_INTERNAL_API_BASE_URL`, `LLM_INTERNAL_API_KEY`, 선택적 `LLM_INTERNAL_API_PROJECT_ID`와 `provider: llm_internal_api`를 사용합니다. group_internal의 tier 모델은 별도 환경변수로 지정하고 beta 복원 모델은 역할별로 고정합니다. 모든 PDF 프로필은 `ROUTER_SERVER_URL`을 사용합니다. local은 `LOCAL_DOLPHIN_URL`·`LOCAL_PADDLE_URL`의 FastAPI이며 default·managed·group·beta는 `DOLPHIN_SERVER_URL`·`PADDLE_SERVER_URL`의 v2/Triton 계약입니다.

## 최상위 계약

default·managed_endpoints·group_internal은 Paddle TLS에 `${PADDLE_SSL:-true}`를
사용합니다. HTTP 서버에는 `PADDLE_SSL=false`를 지정하세요. SSL 환경변수 참조의
`true`/`false`는 엄격한 boolean으로 변환합니다. 편집기는 참조를 유지하며 `.env`를
읽지 않고 기본값을 검증하고, CLI는 실제 환경변수 값을 사용합니다.

스키마는 알 수 없는 필드를 거부합니다. 경로는 프로세스 작업 디렉터리를 기준으로 해석되므로 예제는 저장소 루트에서 실행하세요.

| 키 | 의미 |
| --- | --- |
| `input_dir` | 입력 파일 또는 디렉터리. 바로 아래 파일을 검사합니다. PDF 프로필은 PDF를, 별도 Confluence 프로필은 Markdown을 받습니다. |
| `output_dir` | 로컬 Markdown 및 산출물 루트. `<stem>.md`가 이미 있으면 해당 입력을 건너뜁니다. |
| `document_limits` | 선택값: `allowed_extensions`, `max_input_mb`, `max_pdf_pages`, `max_zip_members`, `max_zip_uncompressed_mb`, `max_zip_compression_ratio`. 기본값은 `core/engine/config/models.py`에 있습니다. |
| `resource_budget.scheduler_max_workers` | 전역 스케줄러 상한인 1~64의 정수. 노드 동시성은 이 값을 넘을 수 없습니다. |
| `pricing_file` | 선택적 운영자 가격 YAML. 생략/null이면 사용량만 기록합니다. 상대 경로는 설정 YAML 디렉터리 기준이며 파일 오류는 파싱을 중단하지 않습니다. [가격 설정](llm-inference.md#운영자-가격-설정) 참고. |
| `langfuse.on` | 외부 사용량 내보내기 선택 불리언. 제공된 설정 6개 모두 꺼져 있습니다. [선택적 사용량 내보내기](optional-capabilities.md#선택적-langfuse-사용량-내보내기) 참고. |
| `pipeline.output_node` | 단일 `document_dto@v1`을 생성하는 노드 ID |
| `pipeline.nodes` | 유형이 지정된 DAG 노드의 비어 있지 않은 목록 |

각 노드는 `id`, 등록된 `node`, 유형이 있는 `input`과 `output` 객체(`type`, 선택적 `is_list`), `depends_on`, `execution_scope`를 갖습니다. `max_concurrency`, `description`, `node_config`는 선택값이며 `max_concurrency` 기본값은 1입니다. 노드에 따라 의존성 순서가 중요합니다. 첫 분할 노드는 `depends_on: [__START__]`을 사용하며 `__START__`는 `fanout` 노드의 유일한 의존성일 때만 유효합니다. `node_config`는 연결·모델 필수 키를 포함해 해당 노드의 스키마로 검사합니다. 컴파일러는 DTO 레이블, 목록 여부, 의존성 유형, 순환, 출력 노드를 확인합니다. 네 가지 실행 범위와 DTO 레이블은 [아키텍처](architecture.md#그래프와-페이지-실행-범위)를 참고하세요.

로컬 프로필의 마지막 분기는 다음과 같습니다.

```yaml
pipeline:
  output_node: global_context_assemble
  nodes:
    # 다른 필수 노드와 분기는 configs/local_quickstart.yaml에 있습니다.
    - id: global_context_assemble
      node: markdown_document_assembler
      execution_scope: fanin
      input: {type: page_markdown_dto@v1, is_list: true}
      output: {type: document_dto@v1}
      depends_on: [global_context_page]
      node_config:
        task_name: GLOBAL_CONTEXT_EXT
        save_suffix: _OCR
        save_debug_artifacts: false
```

이는 독립적으로 실행 가능한 그래프가 아닌 분기 일부입니다. 완전한 프로필을 복사해 값을 수정하세요. 제공된 설정 6개의 용도는 다음과 같습니다.

| 설정 | 그래프와 기록된 검증 |
| --- | --- |
| [`default.yaml`](../../configs/default.yaml) | 주력 15노드 router/full-vision 그래프, 출력 `global_context_assemble`. Global Context 생략 정책 적용 전 9페이지 실제 실행 2회·회귀 통과. |
| [`local_quickstart.yaml`](../../configs/local_quickstart.yaml) | default와 같은 15노드 router/full-vision 그래프; Dolphin 1.5·Paddle FastAPI, 출력 `global_context_assemble`. |
| [`managed_endpoints.yaml`](../../configs/managed_endpoints.yaml) | 운영자 vLLM/Triton·OpenAI 호환 비전 모델을 쓰는 default DAG. 컴파일 통과, 전체 provider 실행 미검증. |
| [`group_internal.yaml`](../../configs/group_internal.yaml) | 비공개 제공자를 쓰는 default DAG. 컴파일 통과, 전체 provider 실행 미검증. |
| [`beta.yaml`](../../configs/beta.yaml) | 성능 검증 중인 17노드 block-context 파이프라인. group/internal 추출 후 역할별 블록 문맥 복원, 출력 `block_context_assemble`. |
| [`optional/confluence_upload.yaml`](../../configs/optional/confluence_upload.yaml) | Markdown 로더·업로더의 문서 범위 2노드. 실제 uploader/client로 페이지 1개·첨부 38개 생성 및 검증. |

default·local·managed·group_internal에는 독립적인 내장 텍스트 추출·병합 분기가 없지만 이미지 없는 L1 페이지는 기존 직접 텍스트 gate를 사용할 수 있습니다. 엔드포인트 계약은 [제공자](providers.md), 저장 파일은 [출력](outputs-and-failures.md)을 참고하세요.

[로컬 설정 편집기](optional-capabilities.md#로컬-설정-편집기)는 YAML을 가져오고 내보내며 루프백 API로 동일한 검증기/컴파일러를 호출할 수 있습니다. 제공자를 호출하지 않고 그래프를 검사합니다. 내보낸 파일에는 사용자가 입력한 엔드포인트 참조나 비밀값이 있을 수 있으므로 공유 전에 검토하세요. 별도 YAML 경로는 [라우터](optional-capabilities.md#선택적-로컬-라우터)와 [Confluence](optional-capabilities.md#선택적-confluence-업로드) 안내에 있습니다.

## 검증 범위

선택한 프로필·환경변수 계약을 후보별 [개발 검사](development.md)로 확인하세요.
managed·group/internal의 자체 전체 제공자 실행은 완료되어 있지 않습니다. 컴파일은
그래프·스키마 검사이며 실제 서비스 호환성 증거가 아닙니다. 후보별 검증은
[릴리스 점검표](release-checklist.md)에서 추적합니다.

무인자 CLI는 `configs/default.yaml`을 선택합니다. 편집기에는 PDF 프로필 5개가 있고
Confluence는 별도 가져오기를 사용합니다. 엔드포인트가 지원하는 모델 ID를 선택하고
[모델 조건](model-and-data-assets.md)을 확인하세요.

## VLM 역할

복원된 `.env` 모델 설정에서 프로필 접두사에 맞는 모델 ID를 지정합니다. 변수가 없거나 비어 있으면 YAML 기본값을 사용합니다.

| 프로필 | 접두사 |
| --- | --- |
| default, managed_endpoints, local_quickstart | `LOCAL` |
| group_internal | `LLM_INTERNAL_API` |
| beta | group_internal 추출 연결; 복원 모델은 역할별 고정 |

| 처리 단계 | 모델 변수 |
| --- | --- |
| 페이지 전체 VLM | `<PREFIX>_LIGHT_VLM_MODEL` |
| 이미지·표 L2 | `<PREFIX>_LIGHT_VLM_MODEL` |
| 이미지·표 L3 | `<PREFIX>_MEDIUM_VLM_MODEL` |
| Global-context VLM | `<PREFIX>_HEAVY_VLM_MODEL` |

local_quickstart도 router와 whole-page/global-context를 사용하며 heavy 모델은 L2 후처리에 사용합니다. `LOCAL_LLM_MODEL` 텍스트 병합 단계는 이 프로필에 없습니다.

이미지 요소 L1은 이미지 VLM 호출 없이 영역 파일과 Markdown 참조를 저장합니다. Stage 1 페이지 L1의 직접 텍스트 추출은 페이지 전체 VLM을 생략합니다. default·local_quickstart·managed_endpoints·group_internal은 아래 정책에 따라 페이지 L1의 추가 Global Context VLM 요청도 생략합니다.

## 단순 페이지의 Global Context 호출 생략

Whole-page 모델은 구조화된 `output` 본문을 요청하고 그 Markdown만 페이지에
넣습니다. 내장 텍스트는 직접 추출 경로를 유지합니다. 생략 대상이 아닌 페이지의
Global Context만 실패하면 성공한 본문·복원된 표를 오류 표시와 함께 보존합니다.
[실패 동작](outputs-and-failures.md#표와-페이지-오류)을 참고하세요.

`global_context_extraction_vlm_merger.node_config.skip_levels`에 지정한 Stage 1
페이지 레벨은 추가 VLM 요청 없이 기존 Markdown을 사용합니다. 스키마 기본값은
`[]`이며, `default.yaml`·`managed_endpoints.yaml`·`group_internal.yaml`은
`global_context_page`에 명시적으로 `[1]`을 지정합니다.

정책을 바꾸려면 해당 노드의 기존 `node_config`에서 다음 값을 편집합니다.

```yaml
skip_levels: [1]
```

기존 provider·모델·연결·추론 설정은 유지합니다. 호출을 생략해도 모델 설정의
필수 필드는 필요합니다. `skip_levels: []`로 바꾸거나 옵션을 제거하면 기존처럼
후처리 대상 전체 페이지를 처리합니다. 값은 0 이상의 엄격한 정수 목록이어야 하며
`[true]`, `["1"]`, `[-1]`, `[1.0]`, 문자열 `"[1]"`은 거부합니다.
이 옵션은 Global Context와 기존 layout 노드에서만 허용하며 layout의 설정은
별도 단계에 적용됩니다. 다른 chat 노드는 이 옵션을 거부합니다.

| `[1]`에서 Stage 1 페이지 조건 | 앞 단계 결과 | Global Context |
| --- | --- | --- |
| L1, 내장 이미지 없음·추출 텍스트 있음 | pdfplumber 직접 텍스트 | 기존 Markdown 유지, 추가 렌더링·요청 없음 |
| L1, 내장 이미지 있음 | 기존 경량 페이지 VLM | 기존 Markdown 유지, 추가 렌더링·요청 없음 |
| L1, 내장 이미지 없음·추출 텍스트 비어 있음 | 기존 경량 페이지 VLM | 기존 Markdown 유지, 추가 렌더링·요청 없음 |
| L2 또는 레벨 정보 없음 | 기존 페이지 처리 | 기존 Global Context 렌더링·요청 유지 |
| 앞 단계 페이지 오류 있음 | 기존 오류 | 기존 오류 처리 우선 |

분할 페이지의 `page.metadata["stage1_level"]`만 검사하며 이미지 재검사나 L1→L2
승격은 하지 않습니다. Global Context 노드는 실행되어 새 페이지 DTO를 반환합니다.
입력을 직접 수정하지 않고 본문·표·이미지 링크·구조화 블록·디버그 Markdown·DTO
`failures`를 보존합니다. 선두 `@page:N`은 제거한 뒤 문서 조립에서 한 번 붙입니다.
생략 페이지에는 Global Context usage callback·accounting attempt가 없으며
해당 노드에 지정한 추가 사용자 요청도 적용되지 않습니다.

설정 편집기는 JSON 목록으로 옵션을 표시하고 YAML 가져오기·내보내기·검증에서
유지합니다. `merge_one_page_image()` 또는
`merge_page_markdown_with_images_vlm()` 직접 호출자는 `skip_levels`를 명시적으로
전달해야 합니다. 두 서비스의 기본값은 기존 동작을 유지합니다.
정책을 비교할 때는 그래프·입력 식별값과 함께 `skip_levels`를 기록하고 새 출력
디렉터리를 사용하세요. 최종 Markdown이 이미 있으면 해당 입력을 건너뜁니다.

## 제공자 API 유형

`group_internal`과 beta는 내부 API를 사용합니다. 두 프로필의 L2·페이지 전체 추출은 `openai`, L3 추출은 `gemini` 계약이며 group_internal의 global-context도 `gemini`입니다. beta의 text 복원은 `openai`, table/image 복원은 `gemini`입니다. default·local_quickstart·managed_endpoints는 medium·heavy VLM을 포함한 모든 모델 단계에서 `openai`를 사용합니다. API 유형은 모델 ID와 별도로 노드 설정에 지정합니다. 실제 지정 모델과 접근 조건은 [제공자 모델 예시](providers.md#모델-지정)를 참고하세요.


[LLM/VLM 추가 요청·reasoning·비용·보안](llm-inference.md)에서 여섯 노드의 사용자 요청, 기본 low, capability 확장, partial 비용과 비파괴 재계산을 설명합니다.

Capability는 사용자가 기본 작성하는 설정이 아닙니다. 사내 배포의 확인된 API 규칙은 별도 registry로 확장할 수 있습니다. [기본 동작과 운영자 사용법](llm-inference.md#모델-capability와-운영자-확장)을 참고하세요.

## 성능 검증용 beta 프로필

`configs/beta.yaml`은 17노드 실험 파이프라인입니다. group_internal과 동일한 추출 연결을 사용하고 global-context 대신 `text_context_restore`, `table_context_restore`, `image_context_restore`를 실행합니다. 하나의 `layout.block_context_restorer` 타입을 역할별로 재사용합니다. text는 `gpt-6-luna/openai`, table/image는 `gemini-3.8-flash/gemini`로 고정하며 공급자는 명시합니다. 공용 모델 이름만으로 내부 deployment capability를 공유하지 않습니다.

L1·native·whole-page·빈/링크 전용 블록은 추가 복원 요청을 생략합니다. 블록당 실제 요청은 최대 2회이며 보조 복원 실패는 원문을 유지하고 `block_context_report.jsonl`에 기록합니다. upstream 오류는 그대로 최종 결과에 전달합니다. `max_workers: 8`은 노드 내부 상한이며 전체 페이지/역할 요청의 전역 합계 상한은 아닙니다. 초기 실측에는 1~2를 권장합니다.

표 입력 `table_input_max_tokens: 256`은 UTF-8 bytes/3 로컬 추정치로 실제 과금 토큰 상한이 아닙니다. `few_shot_examples`는 역할별 서로 다른 예제 ID를 최대 2개 선택하며 `[]`도 허용합니다. formatter의 `restore_tables: true`, `include_page_marker: false`가 검증된 표를 직접 출력하고 assembler가 페이지당 마커를 하나 붙입니다. 이 직접 복구 프로필에서 표 문맥을 지원하며, 후속 global-context와의 조합은 별도 검증 대상입니다.
