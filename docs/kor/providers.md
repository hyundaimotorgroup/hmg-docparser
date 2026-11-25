# 제공자와 엔드포인트 계약

> 원문: [providers.md](../providers.md). 한국어 번역본입니다.

default·local_quickstart·managed_endpoints·group_internal은 같은 router/full-vision DAG를 사용합니다. local은 Dolphin 1.5·Paddle FastAPI를 로컬로 실행하고, 다른 프로필의 Dolphin v2·Paddle Triton 전송은 유지합니다. 모델 요청은 지정한 제공자로 전달됩니다. 이전 local 3페이지 실행 기록은 변경된 그래프의 검증 실적이 아닙니다.

| 프로필 | 레이아웃·OCR | 텍스트·비전 | 필수 `.env` 그룹 | 파서 외부로 전송되는 데이터 |
| --- | --- | --- | --- | --- |
| `configs/local_quickstart.yaml` | 로컬 Dolphin 1.5 / Paddle FastAPI | OpenAI 텍스트·비전 | `LOCAL_LLM_API_KEY` | 이미지는 루프백 서버, 텍스트·영역은 OpenAI로 전송 |
| `configs/default.yaml` | 로컬 router / Dolphin v2 / Paddle Triton | 공통 로컬 LLM API (OpenAI 호출) | `DOLPHIN_SERVER_URL`, `PADDLE_SERVER_URL`, `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_API_KEY` | 페이지 이미지·영역·파생 텍스트를 설정된 제공자로 전송 |
| `configs/managed_endpoints.yaml` | 로컬 router / 운영자 vLLM·Triton | 공통 로컬 LLM API (OpenAI 호출) | `DOLPHIN_SERVER_URL`, `PADDLE_SERVER_URL`, `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_API_KEY` | 문서 파생 내용을 운영자가 지정한 제공자로 전송 |
| `configs/group_internal.yaml` | 로컬 router / 비공개 Dolphin v2·Paddle | 내부 OpenAI/Gemini 비전 모델 | `DOLPHIN_SERVER_URL`, `PADDLE_SERVER_URL`, `LLM_INTERNAL_API_BASE_URL`, `LLM_INTERNAL_API_KEY` | 문서 파생 내용을 비공개 제공자로 전송 |
| `configs/beta.yaml` | 로컬 라우터 / Dolphin v2 / Paddle Triton | 내부 역할별 블록 복원 | group_internal과 동일한 연결 그룹 | 성능 검증 중인 파이프라인 |

운영자 서비스가 요구하지 않는다면 `PADDLE_TOKEN`과 선택적인 자체 운영 채팅 키는 비워둘 수 있습니다. 접근 권한, 요금, 보관, 네트워크 허용 여부는 사용자가 선택한 서비스에 따릅니다. 비용·문서 전송은 이 안내의 [데이터 처리](privacy-and-data-handling.md)와 제공자 약관을 확인하세요. 민감한 PDF는 [데이터 처리](privacy-and-data-handling.md)를 확인한 뒤 실행하세요.

## 그래프가 요구하는 기능

- 레이아웃은 렌더링된 PDF 페이지마다 Dolphin 읽기 순서 박스를 반환해야 합니다. 로컬 FastAPI 경로는 base64 PNG를 `POST /v1/layout`로 보냅니다. 자체 운영 Dolphin v2 경로는 이미지 data URL을 넣은 스트리밍 OpenAI 호환 채팅 완료를 사용합니다. [정확한 계약](#vllm을-통한-dolphin-v2)을 참고하세요.
- OCR은 텍스트 영역의 줄과 선택적인 신뢰도 점수를 반환해야 합니다. 로컬 경로는 `POST /v1/ocr`, 자체 운영 경로는 Triton `IMAGE_BYTES` 입력과 `OCR_RESULT` 출력을 기대합니다. URL만 바꿔 두 전송 방식을 대체할 수 없습니다.
- 텍스트 병합에는 채팅 모델, 표·이미지 분기에는 이미지 입력이 필요합니다. OpenAI/호환 경로는 chat completions를 사용하며 일부 호출은 엄격한 JSON schema 출력을 요청합니다. 해당 요청 형식을 지원하는 모델을 선택하세요. 정상 상태 엔드포인트만으로 파서 호환성이 증명되지는 않습니다.

default·managed_endpoints·local_quickstart는 모든 모델 단계에 `provider: openai`, 공통 `LOCAL_LLM_BASE_URL`과 `LOCAL_LLM_API_KEY`를 사용합니다. group_internal만 사용하는 `provider: llm_internal_api`는 기존 비공개 어댑터에 연결됩니다. 팩토리에는 Azure, Anthropic, Gemini 어댑터도 있지만 로컬 퀵스타트 경로로 검증되지 않았습니다. 비공개 주소·자격 증명·모델 ID는 공유 예제가 아닌 `.env`에 두세요. 엄격한 `node_config`는 [설정](configuration.md), 파서 환경은 [설치](installation.md)를 참고하세요.

## 로컬 Dolphin과 Paddle 및 OpenAI

이 경로는 로컬 PDF 처리, Dolphin 1.5 레이아웃, 한국어 Paddle OCR에 OpenAI 텍스트·비전 채팅을 결합합니다. 두 로컬 서버는 YAML의 루프백 기본 주소를 사용하며 필요하면 `.env`의 `LOCAL_DOLPHIN_URL` / `LOCAL_PADDLE_URL`로 재정의합니다.

### 1. 모델 서비스 시작

1. [Dolphin 1.5 서버 튜토리얼](tutorial/dolphin_15_fastapi/README.md)을 따릅니다. 기본 URL은 `http://127.0.0.1:8200`입니다. GPU VRAM 8 GiB, RAM 16 GiB, 디스크 10 GiB 계획값은 **Dolphin 서버만**을 대상으로 하며 측정된 하한이 아닙니다.
2. [한국어 PP-OCRv5 CPU 튜토리얼](tutorial/paddle_ocr_fastapi/README.md)을 따릅니다. 기본 URL은 `http://127.0.0.1:8100`입니다. 모델 쌍은 `PP-OCRv5_mobile_det`와 한국어 사전을 쓰는 `korean_PP-OCRv5_mobile_rec`입니다. macOS arm64에서 독립 CPU 스모크와 3페이지 파서 실행이 성공했습니다. 본인 문서에서 OCR 품질을 확인하세요.
3. API 키로 접근 가능한 OpenAI 텍스트·비전 모델 ID를 선택합니다. 비전 모델은 이미지 입력을 지원해야 합니다. 두 ID와 API 키를 `.env`에 넣으세요. 파서의 구조화 출력 요청을 지원한다면 같은 멀티모달 모델을 두 역할에 쓸 수 있습니다.

파서를 실행하기 전에 두 튜토리얼의 상태 확인 엔드포인트를 검사하세요. OpenAI 요청은 기본적으로 `https://api.openai.com/v1`을 사용하며 네트워크가 필요합니다. 자체 로컬 LLM/VLM 서버를 쓰려면 `LOCAL_LLM_BASE_URL`을 해당 서버의 OpenAI 호환 주소로 설정하세요. 네 일반 프로필은 이 URL과 `provider: openai`를 공유합니다.

### 2. 파서 설정 및 실행

[설치 안내](installation.md)에 따라 파서를 설치한 뒤 저장소 루트에서 실행합니다.

```bash
cp .env.example .env
# 서버에 맞게 LOCAL_LLM_BASE_URL, LOCAL_LLM_API_KEY, LOCAL_*_VLM_MODEL을 설정하세요.
python main.py configs/local_quickstart.yaml
```

`configs/local_quickstart.yaml`은 Dolphin에 `version: v1`, `v1_transport: fastapi`, OCR에 `transport: fastapi`를 설정합니다. Paddle 튜토리얼은 `POST /v1/ocr`를 사용하지만 원래 OCR 전송 방식은 Triton의 `/v2/models/.../infer` API를 사용하므로 이 설정이 필요합니다. Triton 설정에서 URL만 바꾸면 동작하지 않습니다. 로컬 설정은 텍스트·비전 단계에 `provider: openai`를 사용합니다. `LOCAL_LLM_API_KEY` 하나를 텍스트·비전에 공유합니다.

개발 fixture는 `inputs/smoke/dp_evalset_general_3p.pdf`이며 공개 재배포에는 자산 권리 검토가 필요합니다. 실행 후 `tmp/local_quickstart/dp_evalset_general_3p.md`를 확인하세요. macOS arm64의 새 Conda 환경에서 세 페이지가 생성됐고 파이프라인 오류 표시는 없었습니다. 운영에 쓰기 전에 한국어 띄어쓰기와 원본 PDF의 표·이미지를 비교하세요. 모델 출력은 실행마다 달라질 수 있습니다.

### 데이터 경계

로컬 튜토리얼 서버는 `127.0.0.1`에 바인딩됩니다. 최초 모델 다운로드에는 외부 HTTPS가 필요합니다. OpenAI는 LLM/VLM 노드에 제출한 텍스트와 페이지 영역을 받습니다. 이 설정의 `langfuse.on`은 거짓입니다.

## 자체 운영 모델 엔드포인트

이 경로는 이미 vLLM과 Triton을 운영하는 사용자를 위한 것입니다. 서버는 사용자가 운영하고 파서는 클라이언트로 동작합니다. `configs/managed_endpoints.yaml`을 사용하고 자체 주소·모델 ID·자격 증명을 `.env`에 넣으세요.

### vLLM을 통한 Dolphin v2

이 경로에는 [Dolphin v2 연구 라이선스](https://huggingface.co/ByteDance/Dolphin-v2/blob/main/LICENSE)가
적용되고 상업적 이용은 별도 라이선스가 필요합니다. 상업적 레이아웃 분석은 호환
어댑터를 갖춘 PP-DocLayoutV3를 고려하세요. [모델 조건](model-and-data-assets.md)을 참고하세요.

원본 [`ByteDance/Dolphin-v2`](https://huggingface.co/ByteDance/Dolphin-v2)를 vLLM의 OpenAI 호환 서버에서 제공합니다. vLLM 버전, GPU, 모델 지원에 따라 조정할 시작 명령은 다음과 같습니다.

```bash
vllm serve ByteDance/Dolphin-v2 --served-model-name dolphinv2 --host 127.0.0.1 --port 8000
curl --fail http://127.0.0.1:8000/v1/models
```

파서 Dolphin v2 어댑터는 제공 모델 ID, PNG 이미지를 `data:image/png;base64,...` URL로 넣은 사용자 메시지, 프롬프트 `Parse the reading order of this document.`를 포함한 스트리밍 `POST /v1/chat/completions` 요청을 보냅니다. 응답은 Dolphin v2 레이아웃 박스가 담긴 텍스트를 스트리밍해야 합니다. `DOLPHIN_SERVER_URL`을 OpenAI 호환 기본 URL(위 예제에서는 `http://127.0.0.1:8000/v1`), `DOLPHIN_MODEL=dolphinv2`로 지정하세요. 이 vLLM 명령은 연동 출발점이며 실행과 PDF 전체 결과는 아직 검증되지 않았습니다.

### Triton을 통한 Paddle OCR

Paddle 모델용 Triton HTTP 추론 엔드포인트를 제공해야 합니다. 현재 파서의 통신 계약은 다음과 같습니다.

| 필드 | 필수 값 |
| --- | --- |
| 엔드포인트 | Triton HTTP `POST /v2/models/{model_name}/infer` |
| 입력 | `IMAGE_BYTES`, shape `[1]`, PNG 영역 바이트를 담은 Triton `BYTES` |
| 출력 | `OCR_RESULT`, 첫 요소가 `[[text, score], ...]` 형식의 JSON 문자열 |
| 모델명 | 로드된 Triton 모델 ID를 `PADDLE_MODEL`로 지정 |
| 주소 | `PADDLE_SERVER_URL`은 `http://` 접두사가 없는 `host:port` |
| TLS·인증 | default/managed/group은 `PADDLE_SSL`을 사용하고 기본값은 `true`입니다. HTTP에는 `false`를 지정하거나 YAML에 고정 `ssl` 값을 사용할 수 있습니다. `PADDLE_TOKEN`이 비어 있지 않으면 bearer 토큰으로 전송합니다. |

실제 주소와 모델명으로 Triton HTTP 상태 및 모델 경로를 확인합니다.

```bash
curl --fail http://127.0.0.1:8003/v2/health/ready
curl --fail http://127.0.0.1:8003/v2/models/paddle/ready
```

이 명령은 Triton 라우팅만 검사합니다. Paddle 백엔드가 필요한 텐서를 반환하는지는 증명하지 못합니다. PDF 실행 전에 승인된 이미지로 추론 요청 한 건을 확인하세요. 인증 없는 서버에서는 `PADDLE_TOKEN`을 비워두면 어댑터가 bearer 헤더를 생략합니다.

[로컬 Paddle FastAPI 튜토리얼](tutorial/paddle_ocr_fastapi/README.md)은 `POST /v1/ocr`를 사용하므로 Triton 엔드포인트로 사용할 수 없습니다. 이 튜토리얼에는 [로컬 설정](#로컬-dolphin과-paddle-및-openai)을 사용하세요.

### 텍스트·비전 채팅 모델

`.env`의 `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_API_KEY`와 `LOCAL_LIGHT_VLM_MODEL`, `LOCAL_MEDIUM_VLM_MODEL`, `LOCAL_HEAVY_VLM_MODEL`을 지정하세요. whole-page·표·이미지·global-context 단계 모두 `POST /v1/chat/completions`를 사용하며 비전 단계는 이미지 data URL을 받아야 합니다. 모델 운영자는 용량, 네트워크 접근, 인증, 데이터 보관을 책임집니다. 결과는 `tmp/managed_endpoints` 아래에 저장됩니다. 전체 설정과 출력은 보류된 클린 클론·제공자 실행에서 확인해야 합니다. 서버 상태만으로 호환성을 판단하지 마세요.

## 그룹 및 내부 설정

이 경로는 비공개 모델 서비스와 내부 API를 사용합니다. 조직 규칙에 따른 접근 권한이 이미 있는 사용자를 위한 것이며 저장소가 서비스를 공개하지는 않습니다.

1. 승인된 내부 채널로 프로젝트 유지관리자에게 문의해 Dolphin v2 엔드포인트/모델 ID, Paddle OCR Triton 엔드포인트/모델 ID/토큰을 요청합니다. 같은 승인 절차로 내부 API 기본 URL, 프로젝트 ID, LLM/VLM 모델 ID, 본인 자격 증명을 받으세요. 이 값을 issue, PR, 예제에 넣지 마세요.
2. [설치 안내](installation.md)에 따라 파서를 설치합니다.
3. `.env.example`을 `.env`로 복사해 받은 `LLM_INTERNAL_API_*`, `DOLPHIN_SERVER_URL`, `PADDLE_SERVER_URL`, `PADDLE_TOKEN` 값을 채우고 파일을 비공개로 유지합니다.
4. 저장소 루트에서 `python main.py configs/group_internal.yaml`을 실행합니다.

파서는 페이지 이미지·영역을 지정된 Dolphin/Paddle 엔드포인트에, 문서 파생 내용을 내부 API에 보냅니다. PDF 사용 전에 조직의 데이터 처리 규칙을 확인하세요. 출력은 `tmp/group_internal` 아래에 저장됩니다.

## Global Context 요청 정책

default·managed_endpoints·group_internal은 `global_context_page`에
`skip_levels: [1]`을 지정합니다. 경량 페이지 VLM으로 이미 처리한 경우를 포함해
Stage 1 L1 내용은 추가 Global Context 렌더링·요청 없이 유지합니다. L2·레벨 미상은
기존 provider·모델·API 계약을 사용합니다. 인증·모델 필수 필드는 유지하며 `[]`로
전체 대상 호출을 복원합니다.
[설정 안내](configuration.md#단순-페이지의-global-context-호출-생략)를 참고하세요.
이 정책 자체가 실제 제공자 품질이나 전체 처리 비용의 측정 결과는 아닙니다.

## 모델 라이선스와 검증 범위

상업적 레이아웃 분석에는 Dolphin v2 대신
[PP-DocLayoutV3](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3)(Apache-2.0)를
권장합니다. 제공 프로필은 Dolphin 전용 어댑터를 사용하므로 PP-DocLayoutV3에는
호환 어댑터가 필요하며 URL만 바꾸는 대체 모델이 아닙니다. Dolphin v2의
[Qwen 연구 라이선스](https://huggingface.co/ByteDance/Dolphin-v2/blob/main/LICENSE)는
상업적 이용에 별도 라이선스를 요구하고, Dolphin 1.5 모델 카드는 MIT를 명시합니다.
[자산 조건](model-and-data-assets.md)과 [제3자 고지](../../THIRD_PARTY_NOTICES)를 확인하세요.

| 경로 | 검증 한계 |
| --- | --- |
| 로컬 | 과거 로컬 Dolphin/Paddle·VLM 실행 기록이 있으며 후보·fixture 재검사는 릴리스 작업입니다. |
| Default | 개발 제공자 실행이 기록되어 있으나 후보별 가중치·모델 버전을 확인해야 합니다. |
| Managed | 컴파일·계약 안내가 있으며 별도 전체 vLLM/Triton/제공자 실행은 미검증입니다. |
| Group/internal | 비공개 접근과 허가된 전체 실행이 필요합니다. 설정이 서비스 접근을 제공하지 않습니다. |

엔드포인트 접근·자격 증명·비용·제공자 데이터 조건은 사용자 책임입니다. 허가된 모델·
문서를 선택하고 health만으로 호환성을 판단하지 마세요. [개발 검사](development.md)와
[릴리스 점검표](release-checklist.md)를 사용합니다. 접근 요청과 별도로 보안·행동
신고는 [SECURITY](SECURITY.md)와 [행동 강령](CODE_OF_CONDUCT.md)을 따릅니다.

## 모델 지정

YAML의 기본 모델은 아래 개발용 지정을 반영합니다. 실제 엔드포인트와 계정이 지원하는 모델 ID를 사용해야 하며 모델명 지정만으로 접근 권한이 생기지는 않습니다. 단계별 변수 연결은 [설정 안내](configuration.md#vlm-역할)를 참고하세요.

| 접두사 | Light / 텍스트 LLM | Medium | Heavy | 기록된 제공자 검증 |
| --- | --- | --- | --- | --- |
| `LLM_INTERNAL_API` | `gpt-6-luna` | `gemini-3.8-flash` | `gemini-3.8-flash` | group_internal 전용. 전체 provider 실행 미검증. |
| `LOCAL` | `gpt-6-luna` | `gpt-6-luna` | `gpt-6.1-sol` | 내부 프로필을 제외한 네 프로필이 공유. 변경된 연결은 오프라인 검증. |

LLM/VLM 사용량은 기본 기록되며 비용은 선택 사항입니다. 기본 프로필은 가격을 계산하지 않습니다. 실제 요율의 `pricing_file` 설정과 재계산은 [사용량·가격 안내](llm-inference.md)를 참고하세요.


`configs/beta.yaml`은 성능 검증 중인 block-context 프로필입니다. group_internal의 모델·라우터·layout/OCR 연결이 필요하며 자세한 역할·비용·실패 보존 계약은 [설정](configuration.md#성능-검증용-beta-프로필)을 참고하세요.
