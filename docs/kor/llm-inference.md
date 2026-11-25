# LLM/VLM 추가 요청, reasoning, 사용량·비용

일반 chat 노드 여섯 개 모두 `pipeline.nodes[].node_config.user_prompt`를 지원합니다: `image_vlm_processor`, `table_vlm_caption_maker`, `text_markdown_llm_merger`, `text_image_vlm_merger`, `global_context_extraction_vlm_merger`, `whole_page_llm_processor`. 고정 지시·few-shot·출력 계약은 system, 실제 OCR·Markdown·이미지·추가 요청은 user로 전달합니다. Whole-page의 기존 `prompt`는 신뢰된 system 지시입니다. 모델 응답은 단일 `output` 문자열을 가진 객체이며, 그 Markdown 본문만 문서에 넣습니다. PDF 내장 텍스트 경로는 계속 모델을 호출하지 않습니다. Dolphin/router/OCR의 별도 프로토콜은 유지합니다.

```yaml
node_config:
  provider: openai
  model_name: gpt-6.1-sol
  base_url: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
  user_prompt: |
    이미지에 보이는 치수와 구성 요소의 관계를 자세히 추출해주세요.
```

실행별 요청은 기존 Python 진입점에 전달합니다.

```python
from core.engine.runtime import run_document_pipeline_from_config_path

run_document_pipeline_from_config_path(
    "configs/default.yaml",
    runtime_config={"node_overrides": {
        "image_parse": {"user_prompt": "도면을 자세히 설명해주세요."},
    }},
)
```

위 `image_parse`는 예시입니다. 실제 YAML의 node ID를 사용하세요. 알려진 일반 chat node ID와 `user_prompt` 키만 허용합니다. 키 미지정은 YAML 상속, 명시 null·빈 문자열·공백은 요청 해제입니다. 원본 입력과 최종 요청을 처리 전에 검증하고 자동 절단하지 않습니다. 기본 상한은 노드별 8,192 Unicode code point와 UTF-8 32 KiB, 실행별 최종 요청 합계 128 KiB입니다. 다국어·개행·들여쓰기는 보존하고 금지 제어문자·surrogate·bidi 제어문자는 거절합니다. 추가 요청의 `${NAME}`은 문자 그대로이며 연결·인증 설정의 환경변수 참조는 유지됩니다.

신뢰된 host YAML의 `prompt_policy`에서 양의 정수로 `max_codepoints`, `max_bytes`, `max_run_bytes`, `max_context_bytes`, `max_output_bytes`를 조정할 수 있습니다. 문서 context와 응답 출력은 별도 기본 4 MiB 상한을 사용합니다. 이는 byte 기반 검증이며 tokenizer 검증이나 공급자 context token 상한을 보장하지 않습니다. 초과 문서는 host가 분할해야 합니다. 사용자 override로 상한·system·endpoint·인증·schema·도구·가격을 변경할 수 없습니다. 로컬 설정 편집기는 textarea·Unicode/UTF-8 카운터·본문 없는 오류를 제공합니다. 카운터는 기본 상한 안내이고 실제 host 정책은 서버가 검증합니다.

추가 요청이 없을 때 이미지는 기존 짧은 캡션을 기본으로 사용합니다. 요청이 있으면 사실·schema 계약 내에서 상세도를 변경합니다. 후속 merge가 링크에 연결된 상세 캡션을 축약하거나 누락하면 원본 설명을 복원합니다. 파일명·표 placeholder·caption fence·block coverage를 보존합니다. 이미지 비활성화·crop 없음·router skip·whole-page native-text 경로는 모델 호출을 강제하지 않습니다. 이때 추가 요청은 적용되지 않으며 `image_vlm_used`/`native_text_direct`와 accounting attempt 부재로 확인합니다. 요청을 다른 노드로 자동 전파하지 않습니다.

Global Context는 페이지 `skip_levels`를 지원하며 default·managed_endpoints·
group_internal에 `[1]`이 적용되어 있습니다. 일치하는 Stage 1 페이지는 렌더링·VLM
요청 없이 앞 단계 Markdown을 유지합니다. 생략 페이지에는 해당 노드의 `user_prompt`·
reasoning을 적용하지 않고 Global Context usage callback·attempt record도 만들지
않습니다. 직접 텍스트를 얻지 못한 페이지의 기존 경량 페이지 VLM 호출은 유지합니다.
L2·레벨 미상은 기존 추론 옵션을 사용하며 `[]`는 전체 대상 후처리를 복원합니다.
[설정 안내](configuration.md#단순-페이지의-global-context-호출-생략)를 참고하세요.

## Reasoning

OpenAI chat 전송은 미등록 모델을 포함해 기본 `temperature`를 자동 추가하지
않습니다. 직접 전송하려면 `extra_body.temperature`에 지정합니다. 모델의 미지원이
확인된 sampling 옵션은 전송 전에 거절합니다. 별도 Dolphin 레이아웃 추론의 생성
설정은 유지합니다. 실패한 모델 요청에는 예외 종류·HTTP 상태·오류 코드·문제
파라미터만 필터링한 `metadata.request_error`를 기록할 수 있으며 원본 오류 메시지는
기록하지 않습니다.

공통 불변 타입은 `core/domain/inference/models.py`, 공급자 해석·직렬화는 `core/adapters/models/reasoning.py`, 연결·레벨 상속은 `core/services/model_routing.py`에 있습니다. Capability는 `core/adapters/models/resources/model_capabilities.yaml`의 정확한 provider/protocol/model/deployment identity로 관리하고 가격표와 분리합니다.

일반 사용자는 reasoning을 생략하면 됩니다. 기본 규칙을 정상적으로 읽었고 low가 확인된 effort 모델에는 low를 자동 전달하고, budget-only·미등록 모델에는 옵션을 생략합니다. Low는 off가 아니며 medium도 매번 양의 추론을 보장하지 않습니다. 서버 실제 강도가 별도로 보고되지 않으면 `unknown`입니다.

```yaml
# 선택적 신뢰된 개발자 설정. 기본 YAML/UI에서 선택할 필요가 없습니다.
reasoning: {mode: effort, effort: medium}
# reasoning: {mode: provider_default}  # 옵션 생략, default_low도 해제
# reasoning: {mode: disabled}         # 지원 모델만 가능
# reasoning: {mode: budget, budget_tokens: 1024}
# reasoning: {mode: adaptive, effort: low}
```

Reasoning null은 기본 해석입니다. 명시 설정 → legacy extra_body → 등록된 접미사 → capability default_low → 생략 순서로 적용합니다. 명시 설정은 유효한 legacy 설정보다 우선합니다. Legacy 중복·잘못된 예산·명시 미지원 옵션은 호출 전에 거절하며 실패 후 강도를 몰래 낮춰 재호출하지 않습니다. L2/L3는 최종 model/provider/API/endpoint/deployment identity가 같을 때만 상속합니다. 다른 identity에는 inherited thinking을 제거하고 일반 sampling 옵션은 보존합니다. Level extra_body는 빈 객체도 포함해 전체 교체입니다.

Public `gpt-6.1-sol`은 low/medium/high/xhigh/max를 지원하고 OSS 기본은 low입니다. none/minimal은 거절합니다. `gpt-6-luna`는 none/disabled도 지원합니다. 두 모델에는 미지원 sampling 기본값을 보내지 않습니다. Chat API 출력 상한은 `extra_body.max_completion_tokens`의 양의 정수(최대 128000)로 지정하며, legacy `max_tokens`는 호출 전에 거절합니다. Native 출력 옵션과 Anthropic thinking/출력 예산의 관계도 검증합니다. Gemini 2.5 Flash/Pro는 budget 모델이며 임의 low 예산을 만들지 않습니다. Public Claude Opus 5.5는 adaptive/effort 및 기본 low를 지원하지만 이 모델의 강제 schema tool은 거절합니다. Sonnet 4의 budget thinking과 강제 tool도 함께 사용할 수 없습니다. 미확인 Gemini/gateway alias는 옵션 생략입니다. 일반 `openai-compatible`에 vLLM 반복 페널티를 강제하지 않습니다. 명시적 `vllm` backend는 별도입니다.

SDK는 실제 SDK와 in-memory HTTP transport로 wire payload를 검증합니다. Google SDK는 1.75.0을 사용해 기존 Pydantic pin을 유지합니다. 중첩 thinking 키가 snake_case로 통과되는 SDK 동작을 엔진 소유 native HTTP extension으로 보완합니다. 구형 Anthropic SDK도 문서화된 native `output_config`를 extra_body로 직렬화합니다. 이 검증은 실 API 수용·품질 검증과 별개입니다.

## 모델 capability와 운영자 확장

`core/adapters/models/resources/model_capabilities.yaml`은 프로젝트가 관리하는 **API 호환성 규칙표**이며 가격과 독립적입니다. 일반 사용자가 작성할 필요는 없습니다. Reasoning mode/effort, 기본 low, sampling 제한, 출력 상한과 공급자 사용량 의미를 설명합니다. 가격 entry로 모델 기능을 활성화하거나 capability로 단가를 정하지 않습니다.

기본 규칙은 첫 모델 조회에서 한 번 읽습니다. 파일이 없거나 잘못되면 표 전체를 거부하고 안전한 `default_capabilities_unavailable` 경고를 한 번 남깁니다. 기본 호출은 기존 미등록 모델 동작으로 계속합니다. 자동 low·등록 접미사 변환·capability에 근거한 누락 토큰의 0 변환은 적용하지 않습니다. 공급자/API·응답 검증은 유지하며 이 동작이 실제 endpoint의 요청 수용을 보장하지는 않습니다. 지원 근거가 없는 명시적 reasoning·legacy thinking 옵션은 모델 호출 전에 오류로 처리하고 조용히 버리지 않습니다. 명시적인 `mode: provider_default`는 공급자 기본값을 선택한다는 뜻입니다. 기본 파일을 고쳤다면 프로세스를 재시작하세요. 호출마다 실패한 파일을 다시 읽지 않습니다.

### 확인된 배포 규칙 추가

사내 배포는 운영자 파일이나 신뢰된 Python 등록으로 확장합니다. `provider`, `api_type`, `model`과 선택적 `deployment`가 설정한 route와 정확히 일치해야 합니다. 모델 이름이 같다는 이유로 공개 API 규칙을 사내 서비스에 적용하지 않습니다. 이 파일에 키·endpoint·단가를 넣지 않습니다.

서비스가 OpenAI 형식의 effort 파라미터를 지원한다고 확인했다면 다음처럼 시작할 수 있습니다.

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

위 예제는 가상 배포 계약이며 실제 서비스의 지원을 보증하지 않습니다. 확인한 옵션만 선언하세요. `version: 1`은 선택 사항이고 배포와 무관한 필드는 생략할 수 있습니다. `serializer`는 등록된 직렬화기(`openai`, `gemini`, `anthropic`)를 선택하며 Python import 경로가 아닙니다. Custom serializer·사용량 의미는 신뢰된 Python 코드로 등록합니다.

파일을 명시적으로 읽고 기존 runtime 확장에 전달합니다.

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

선택한 노드에 일치하는 provider/API/model을 평소처럼 설정합니다. `include_defaults=True`는 다른 identity의 기본 규칙을 유지하며 정확히 일치하는 운영자 entry가 우선합니다. 이 옵션을 생략하면 해당 파일만 사용합니다. `from_path`에 직접 전달한 상대 경로는 Python 프로세스 cwd 기준이므로 위치가 중요하면 절대 경로를 사용하세요. 새 native YAML 설정 옵션을 추가하는 방식은 아닙니다.

운영자가 명시한 파일의 누락·빈 파일·형식 오류는 실행 전에 오류로 보고합니다. 중복 YAML key/identity, 알 수 없는 필드, 문자열 boolean, 잘못된 mode/effort·날짜, 0 이하·모순된 한도는 거부합니다. 신뢰된 `ModelCapability(...)` 등록도 같은 entry 검증을 사용합니다. 출처·날짜는 운영자의 확인 근거를 기록하며 실제 서비스 가용성을 검증하거나 규칙을 자동 만료시키지는 않습니다.

`omitted_thinking_is_zero`의 기본값은 false입니다. 배포별 확인 근거와 비어 있지 않은 `source`, ISO 날짜의 `verified_on`이 있을 때만 활성화하세요. 이 경우에도 사용량 정규화는 유효 토큰·성공한 최종 완료를 요구하며 명시적 null/invalid thoughts는 0으로 바꾸지 않습니다. 대부분의 운영자는 이 필드를 생략하면 됩니다. 상속한 기본 표에 오류가 있으면 `registry.load_error`에서 안전한 진단을 확인할 수 있습니다.

## 사용량과 비용

종료 이유 없이 끝난 스트림은 기존 재시도 횟수·시간 한도 내에서 재요청할 수 있습니다.
해당 시도의 부분 텍스트는 페이지 출력으로 쓰지 않고 사용량 기록은 유지합니다.
토큰 한도나 안전 중단처럼 명시된 비정상 종료는 실패이며 이 재시도 대상이 아닙니다.

사용량은 가격 설정과 무관하게 기록됩니다. 비용 계산은 선택 사항이며 실제 단가는 운영자가 관리합니다. 저장된 JSONL로 모델을 다시 호출하지 않고 과거 실행 비용을 재계산할 수 있습니다. `pricing_file`을 생략하거나 null로 두면 사용량만 기록합니다.

### 운영자 가격 설정

**USD 기준 토큰 100만 개당 가격**을 네 줄부터 적습니다.

```yaml
openai:
  demo-model:
    input: 1.00
    output: 4.00
```

숫자는 가상 예제입니다. 사용하는 서비스의 실제 요율로 교체하세요. provider와 모델 key는 `_llm_usage.jsonl`의 `provider`, `model_name`과 정확히 일치해야 합니다. 기록 모델명은 설정한 별칭과 다를 수 있습니다. 모델 이름으로 요율을 추정하거나 공개 API와 사내 API의 가격을 공유하지 않습니다. `configs/optional/llm_pricing.yaml`은 예제이며 자동으로 읽지 않습니다.

선택한 설정 YAML과 같은 디렉터리에 가격 파일을 저장한 뒤 설정에 추가합니다.

```yaml
pricing_file: ./my-prices.yaml
```

상대 경로는 설정 YAML 디렉터리 기준입니다. Python mapping을 `run_document_pipeline`에 직접 전달할 때는 절대 가격 경로나 `config_dir=...`를 사용합니다. cwd를 조용히 기준으로 삼지 않습니다. `load_yaml_with_env`는 설정의 원래 디렉터리를 보존합니다. 편집기는 가격 파일을 열지 않고 옵션을 유지합니다. 내보낸 뒤에는 새 YAML 위치가 상대 경로 기준입니다. 신뢰된 `_host_pricing_path`는 호환 옵션으로 유지하며 서로 다른 명시 경로가 충돌하면 비용을 비활성화하고 진단을 남깁니다. 파싱은 계속됩니다.

일반 숫자와 숫자 문자열을 허용하며 유한한 0 이상이어야 합니다. 명시적 0은 유효합니다. 중복 YAML key, boolean, 음수, NaN/Infinity와 잘못된 구조는 오류입니다. 파일 누락·빈 파일·잘못된 가격은 비용 기능만 끄고 안전한 진단을 남깁니다. Usage 직렬화·수집 한도·계산·로컬 sink 실패 때문에 정상 provider 요청을 반복하거나 정상 파싱 결과를 버리지 않습니다. 응답 JSON 손상·비정상 종료·schema 불일치·출력 한도는 실제 응답 실패로 유지합니다.

기본 input/output만 작성했다고 cache 할인·장문 요율·추가 과금까지 확인된 계약은 아닙니다. 누락 cache는 null로 남으며 입력 요율을 적용한 가정은 부분 소계로 표시될 수 있습니다. 서비스에 필요한 조건만 추가하세요. Cache read 할인 예제:

```yaml
openai:
  demo-model:
    input: 1.00
    output: 4.00
    cache_read: 0.10
```

요청 전체 입력 길이에 따라 가격이 달라질 때:

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

이 요율도 가상 값입니다. 상한은 오름차순이며 구간은 0~272,000과 272,001~1,050,000입니다. 요청 전체에 구간 하나를 선택해 출력까지 같은 구간 단가를 적용합니다. 초과 토큰에만 적용하는 누진 계산이 아닙니다. 전체 입력이 없거나 마지막 상한을 넘으면 unpriced입니다. 모델 최상위 input/output과 `bands`를 함께 쓰지 않습니다. `cache_read`는 모델 공통값 또는 구간별 값으로 추가할 수 있습니다. 기존 고급 `entries` 형식의 API·deployment·region·tier·TTL·날짜 조건은 계속 지원하며 네 줄 형식에서는 필수가 아닙니다.

### 사용량과 비용 결과 읽기

실제 시도마다 v2 record를 남깁니다. Call/attempt/event ID, canonical usage, allowlist raw/snapshot, 완료 근거, requested/effective/sent reasoning, processing 결과, 가격 기능을 사용하면 불변 가격 snapshot이 포함됩니다. 비활성화·가격 실패에서는 `pricing_snapshot: null`이며 과거 snapshot 내용과 fingerprint는 보존합니다. 누락은 null, 보고된 0은 0입니다. OpenAI/Anthropic output에 포함된 reasoning을 다시 더하지 않으며 Gemini는 유효 candidates+thoughts를 사용합니다. 표시에서 total-input을 역산하지 않습니다. 정상 provider 완료와 parsing 성공은 별개이고 EOF만으로 완료를 인정하지 않습니다. 실패·취소 직전 수신한 usage도 보존합니다. SDK retry는 비활성화하고 엔진 transport retry는 각각 기록합니다. Sink·schema 오류는 성공한 유료 호출을 반복하지 않습니다. 공유 client의 기록은 호출 context별이며 callback 없이도 `last_call_records`/`last_usage_record`를 조회할 수 있습니다.

Gemini thoughts **키 생략**을 0으로 유도하려면 exact verified `omitted_thinking_is_zero` capability, 유효 input/body, 명시 성공·정상 완료·최종 usage, 모순 없는 수치 및 과거 양의 snapshot 유실 부재가 모두 필요합니다. Explicit null/invalid·실패·취소·MAX_TOKENS·완료 근거 누락은 제외합니다. 이름만 보고 public/gateway 생략 정책을 활성화하지 않습니다. 합성 테스트는 정책을 명시적으로 등록합니다. Cache 누락은 독립적으로 null입니다.

공통 Decimal 계산기로 일반 input·cache read/write·전체 output을 한 번씩 과금합니다. 전체 output이 미확정이어도 본문 count가 유효하면 `components.response_output`을 known subtotal에 포함합니다. 전체 output이 확인되면 output 성분으로 대체해 중복 합산하지 않습니다. API `cost_usd`는 별도 provider reported 금액이며 추정 비용에 더하지 않습니다. `complete`는 명시 범위의 완전한 추정이지 청구서 대조 완료가 아닙니다.

가격이 활성화되면 캐시 분해 정보가 부족해도 수집된 유효 토큰은 등록 단가로 계산합니다. OpenAI/Gemini의 총 입력에서는 실제 보고된 cache read/write만 빼고 남은 입력을 일반 단가로 계산하여 `estimated_input_usd`에 둡니다. 보고된 캐시는 별도 요율로 한 번만 계산합니다. Anthropic의 별도 비캐시 입력은 `regular_input_tokens`로 보존하므로 총 입력이 null이어도 비용을 계산합니다. 일부 필드가 invalid여도 다른 유효 토큰 성분은 버리지 않습니다. 추론 출력만 보고된 경우에도 output 단가로 한 번 계산합니다. 유효한 unclassified 잔여 토큰도 등록 input/output 단가 중 최댓값으로 별도 추정하며, 확정 출력이나 보장된 비용 범위로 바꾸지 않습니다.

`estimated_components`에 단가 가정을 기록하고 `estimated_subtotal_usd`는 추정 성분과 알려진 성분을 한 번씩 합산합니다. Cache read 단가가 없으면 등록 일반 입력 단가로 추정합니다. Cache write TTL이 없으면 등록 TTL 단가 중 최댓값(쓰기 단가 자체가 없으면 일반 입력 단가)으로 추정하며 실제 TTL로 저장하지 않습니다. 기존 고급 entry는 수집된 Anthropic 입력으로 가정한 구간을 선택할 수 있으며 해당 비용은 추정으로 표시합니다. 새 `bands`는 알려진 전체 입력을 요구합니다. Canonical cache null은 그대로 유지하며 미등록·invalid 단가를 만들지 않습니다.

`tokens_complete`와 `cost_status`는 독립입니다. Partial 전체 금액은 `amount_usd: null`이고 `known_subtotal_usd` 및 성분합/페이지 평균을 따로 제공합니다. 이는 전체 비용·전체 평균·보장된 하한이 아닙니다. 금액 근거가 없으면 `unknown`과 `—`, 유효 0이면 0입니다. 비활성화는 `disabled (usage recorded)`로 표시합니다. `missing_usage`는 공급자 사용량 누락, `unpriced`는 적용 가격 없음 또는 가격 비활성화·실패, `partial`은 일부 성분·가정만 계산했다는 뜻입니다. null은 무료라는 뜻이 아닙니다. CLI는 완전한 amount → 추정 포함 subtotal → 알려진 성분합 순으로 금액을 선택하고 추정에는 `estimated subtotal (partial)`와 불완전 비용 시도 수·USD를 표시합니다. Summary의 `estimated_subtotal_average_page_usd`와 model/node/page 집계도 동일 계약을 사용합니다. 출력 표시 함수는 알려진 본문 → 전체 출력 순서로 선택하고 summary를 수정하지 않습니다.

성공·실패·취소 종료 시 출력 디렉터리에 `_llm_usage.jsonl`과 atomic `_llm_usage_summary.json`을 기록합니다. Live tracker·JSONL replay·저장 집계는 같은 reducer를 사용합니다. Accounting 파일은 공개 ZIP에서 제외합니다. Prompt·응답 본문·인증·헤더·endpoint는 usage 로그에 저장하지 않고 provider exception 전문을 오류에 넣지 않습니다. 선택적 Langfuse 4.9는 `start_observation`으로 완전한 비용과 canonical usage를 전달하며 partial은 model/numeric usage를 생략해 자동 가격 계산을 억제하며 입력 추정·추정 포함 합계·가정 근거는 metadata에 보존합니다.

모델 호출 없는 재계산은 새 디렉터리가 필요합니다.

현재 Langfuse exporter는 로컬 비용이 complete일 때만 모델명·숫자 usage·cost를 전송합니다. 가격이 비활성화되거나 partial/unpriced이면 이 필드가 없는 metadata observation을 보냅니다. 켜기만 해도 자동 비용 계산이 되는 것은 아닙니다. 로컬 JSONL이 기준 기록이며 파싱·flush 성공으로 서버 수신을 보장하지 않습니다. 백그라운드 전송 실패는 감지하지 못할 수 있습니다.

### 저장 JSONL 재계산

모델을 재호출하거나 원본 JSONL을 수정하지 않으며 출력 경로는 새 디렉터리여야 합니다.

```sh
python tools/recalculate_llm_usage.py outputs/run/_llm_usage.jsonl outputs/replayed --page-count 3
python tools/recalculate_llm_usage.py outputs/run/_llm_usage.jsonl outputs/repriced \
  --pricing configs/my-prices.yaml --as-of 2026-11-18 --page-count 9
```

날짜 없는 운영자 가격표의 `--as-of`는 그날 실제 요율이었다는 보증이 아닙니다. 오프라인 `--pricing`은 계산이 목적이므로 잘못된 가격 파일을 명확한 오류로 보고합니다. 로컬 추정은 실제 청구액과 다를 수 있습니다. Snapshot 없는 기록도 replay·재계산할 수 있고 `--repair`는 그대로 둡니다.

동일한 legacy 두 줄도 별개 occurrence ID를 유지하고 모호한 cache/thinking은 누락으로 남깁니다. `--repair`는 저장 가격 fingerprint/date/entry와 raw·완료·capability 근거가 일치할 때만 과거 v2의 메모리 사본을 보완합니다. 원본은 변경하지 않으며 반복 보완은 idempotent입니다. 과거 보완에는 누락된 입력 추정 및 raw로 보고된 Anthropic 비캐시 입력 비용 복원도 포함합니다. 새 가격을 지정한 재추정과 과거 보완은 다릅니다. Live tracker가 없는 새 프로세스에서도 `load_summary`로 저장 summary를 읽습니다.

## 확장과 출력 안전

신뢰된 Python 코드로 `CapabilityRegistry.register`, `register_reasoning_serializer`, `register_chat_provider`, `register_task_builder`를 사용합니다. Host registry는 `runtime_config['_capability_registry']`, 가격 파일은 `_host_pricing_path`로 전달합니다. 프롬프트로 import path나 callback을 지정하지 못합니다. [영문 문서](../llm-inference.md)의 custom backend 예시와 가격 entry 계약을 참고하세요. 기존 고급 가격 entry는 exact identity, 선택적 alias/deployment/region/tier/context/TTL, 출처·확인일·유효기간·million token 단위를 명시합니다. 중복/미등록은 unpriced입니다. 내장 계산 범위 밖 성분은 unsupported(부분 비용)로 선언하거나 신뢰된 확장으로 처리해야 합니다.

모델 JSON 필수 키·타입·출력 길이를 artifact 사용 전에 검증합니다. 파일명을 정리하고 remote·절대경로·traversal 이미지 링크를 제거합니다. Table은 구조와 named/hex `color`·`background-color`만 유지하며 이벤트·URL·expression·임의 CSS를 제거합니다. 모델 Markdown에서는 검증된 표 외의 모든 HTML 태그를 escape합니다. Markdown consumer도 raw HTML을 비활성화하거나 sanitizer를 적용하고 asset root를 제한해야 합니다. 역할 분리·검증이 prompt injection 자체를 완전히 차단한다고 주장하지 않습니다.

구현 중 가져온 공식 자료: [OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning), [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [가격](https://developers.openai.com/api/docs/pricing), [Anthropic thinking](https://platform.claude.com/docs/en/build-with-claude/thinking). Google thinking 페이지는 조회가 차단됐으며 Gemini budget entry는 기존 문서 계약을 유지합니다. 실제 모델·생략 의미는 별도 확인이 필요합니다. 로컬 테스트로 provider 이용 가능성·이미지 품질·서버 실제 강도·청구서 정확성을 검증했다고 보고하지 않습니다.


기본 규칙은 `importlib.resources`로 패키지 내부에서 자동 로드하며 작업 디렉터리나 repo-root configs에 의존하지 않습니다. 갱신은 프로젝트가 맡고 사용자는 패키지 업데이트로 받습니다. 일반 미등록 모델은 reasoning 미지정/`provider_default`로 기본 호출을 시도할 수 있습니다. 검증된 고급 확장 예제는 `configs/optional/model_capabilities.example.yaml`이며 `CapabilityRegistry.from_path(..., include_defaults=True)`로 명시적으로 읽고 runtime `_capability_registry`에 전달합니다. configs 바로 아래 YAML의 가격 opt-in은 `pricing_file: ./optional/llm_pricing.yaml`입니다.

## Beta 블록 복원 요청

복원 요청은 신뢰된 역할별 지시·가상 예제를 system에, 해당 블록 reference와 사용자 요청을 TaskPrompt JSON user 데이터에 넣습니다. 전체 페이지 이미지는 역할당 한 번 렌더링하고 worker별 복사본을 닫습니다. 요청은 정확히 `reasoning`, `output` 두 문자열이며 strict JSON에서는 fence/키/본문 복구를 허용하지 않습니다. 참조·수치 부호·소수·단위·문장부호·기존 caption/link를 보존 검사합니다. reasoning은 일반 Markdown/usage 본문에 넣지 않으며 debug를 켰을 때만 `_private` 산출물에 포함합니다. 페이지의 공유 시간 예산·취소는 새 블록과 재시도를 중단합니다. 진행 중 transport 정리는 timeout/취소 지원 범위에 따릅니다.
