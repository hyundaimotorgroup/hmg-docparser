# 빠른 시작: 서비스를 시작하고 PDF 파싱하기

> 원문: [quickstart.md](../quickstart.md). 한국어 번역본입니다.

이 안내는 Python 환경, 의존성, 모델 파일, 라우터 체크포인트, 제공자 접근
권한이 준비돼 있다고 가정합니다. 먼저 [설치 안내](installation.md)를 확인하세요.
모든 명령은 저장소 루트에서 실행합니다. 각 터미널에서 실행할 앱에 맞는 환경을
활성화하세요. 아래 Conda 환경 이름은 예시이며 본인의 환경 이름이나 경로로 바꿉니다.

파서 CLI는 제공자 서버를 자동으로 시작하지 않습니다. 파싱이 끝날 때까지
필요한 서버를 각각의 터미널에서 실행해 두세요.

## 파이프라인 선택

| 설정 | 내 컴퓨터에서 시작할 앱 | 별도로 준비할 서비스 | 기본 출력 디렉터리 |
| --- | --- | --- | --- |
| `configs/local_quickstart.yaml` | 라우터, Dolphin 1.5 FastAPI, Paddle OCR FastAPI, 파서 CLI | OpenAI 호환 텍스트·비전 API | `tmp/local_quickstart` |
| `configs/default.yaml` | 라우터, 파서 CLI | Dolphin v2, Paddle Triton, OpenAI 호환 비전 API | `tmp/default` |
| `configs/managed_endpoints.yaml` | 라우터, 파서 CLI | 자체 운영 Dolphin v2/vLLM, Paddle Triton, OpenAI 호환 비전 서비스 | `tmp/managed_endpoints` |
| `configs/group_internal.yaml` | 라우터, 파서 CLI | 비공개 Dolphin v2, Paddle Triton, 내부 비전 API | `tmp/group_internal` |
| `configs/beta.yaml` | 라우터·파서 CLI; group/internal 추출 연결 | 내부 Luna/OpenAI 및 Flash/Gemini; 성능 검증 중 | `tmp/beta` |

운영자가 관리하는 서비스는 기존 배포 명령으로 시작하세요. 이 저장소는 로컬
Dolphin 1.5·Paddle FastAPI와 라우터 진입점을 제공합니다. v2/vLLM과 Triton의
계약은 [제공자 안내](providers.md#자체-운영-모델-엔드포인트)를 참고하세요.
[권장 모델 조합과 Dolphin v2 사양](README.md#권장-설정)은 목표 구성이고,
아래 예제는 제공된 YAML의 현재 기본값을 따릅니다.

## `.env` 작성

저장소 루트의 [`.env.example`](../../.env.example)을 참고해 `.env`를 작성합니다.
선택한 프로필에 필요한 값만 채우고, 예제 파일에 없는 변수는 추가하세요.
자격 증명은 `.env`에 보관합니다.

파서는 YAML의 `${NAME}` 참조를 읽을 때 `.env`를 자동으로 로드합니다.
이미 셸에서 내보낸 환경변수는 `.env`보다 우선합니다. 독립 라우터·Dolphin·
Paddle 진입점은 프로세스 환경에서 옵션을 읽으므로 서버 터미널에서 명령 앞에
값을 붙이거나 `export`로 설정하세요. `source .env`는 필요하지 않습니다.

### 로컬 Dolphin 1.5 + Paddle FastAPI

`configs/local_quickstart.yaml`에 필요한 값입니다.

```dotenv
LOCAL_DOLPHIN_URL=http://127.0.0.1:8200
LOCAL_PADDLE_URL=http://127.0.0.1:8100

LOCAL_LLM_BASE_URL=https://api.openai.com/v1
LOCAL_LLM_API_KEY=replace-with-your-api-key
LOCAL_LIGHT_VLM_MODEL=gpt-6-luna
LOCAL_MEDIUM_VLM_MODEL=gpt-6-luna
LOCAL_HEAVY_VLM_MODEL=gpt-6.1-sol
```

light는 L1 페이지 전체와 L2 요소, medium은 L3 요소, heavy는 L2 global-context를 처리합니다. 모두 이미지 입력과 구조화 응답을 지원해야 합니다. L1 native text는 whole-page/global-context 호출을 생략합니다. `ROUTER_SERVER_URL=http://127.0.0.1:8001`도 설정하세요.

### 라우터 + Dolphin v2 + Paddle Triton

`default`, `managed_endpoints`에 필요한 값입니다.

```dotenv
ROUTER_SERVER_URL=http://127.0.0.1:8001
DOLPHIN_SERVER_URL=http://127.0.0.1:8000/v1
DOLPHIN_MODEL=dolphinv2
PADDLE_SERVER_URL=127.0.0.1:8002
PADDLE_MODEL=paddle
PADDLE_TOKEN=

LOCAL_LLM_BASE_URL=https://api.openai.com/v1
LOCAL_LLM_API_KEY=replace-with-your-api-key
LOCAL_LLM_MODEL=gpt-6-luna
LOCAL_LIGHT_VLM_MODEL=gpt-6-luna
LOCAL_MEDIUM_VLM_MODEL=gpt-6-luna
LOCAL_HEAVY_VLM_MODEL=gpt-6.1-sol
```

Dolphin·Paddle 주소와 모델 ID를 실행 중인 서비스에 맞게 바꾸세요.
`DOLPHIN_SERVER_URL`은 OpenAI 호환 기본 경로 `/v1`을 포함합니다.
`PADDLE_SERVER_URL`은 URL 스킴이 없는 Triton `host:port` 형식입니다.
서비스에 bearer 인증이 필요하면 `PADDLE_TOKEN`을 설정합니다.

OCR TLS는 Triton 엔드포인트에 맞춰야 합니다. default·managed_endpoints·
group_internal은 `${PADDLE_SSL:-true}`를 사용합니다. 위 예제처럼 일반 HTTP
Paddle 주소라면 `.env`에 `PADDLE_SSL=false`를 설정하세요. [엔드포인트 계약](providers.md#triton을-통한-paddle-ocr)을 참고하세요.

`default`와 `managed_endpoints`는 `skip_levels: [1]`에 해당하지 않는 페이지의
global-context 비전에 heavy 모델을 사용합니다.
모든 VLM 역할은 이미지 입력을 지원해야 합니다.

default·local_quickstart·managed_endpoints·group_internal은 Stage 1 L1의 추가 Global Context
요청만 생략합니다. 이미지가 있거나 직접 텍스트를 얻지 못한 페이지의 기존 경량
VLM 호출은 유지합니다. 다른 페이지를 위한 heavy 모델·인증 설정도 유지하세요.
`global_context_page.node_config.skip_levels: []`로 전체 대상 후처리를 복원할 수
있습니다. [설정 정책](configuration.md#단순-페이지의-global-context-호출-생략)을
참고하세요. 정책을 비교할 때는 새 출력 디렉터리를 사용합니다. 최종 Markdown이
이미 있으면 해당 입력을 건너뜁니다.

### 그룹/내부 API

`configs/group_internal.yaml`은 위의 router·Dolphin·Paddle 연결 변수를 동일하게
설정하고, 비전 API에는 아래 값을 사용합니다.

```dotenv
LLM_INTERNAL_API_BASE_URL=https://your-internal-api.example
LLM_INTERNAL_API_KEY=replace-with-your-internal-api-key
LLM_INTERNAL_API_PROJECT_ID=
LLM_INTERNAL_API_LIGHT_VLM_MODEL=gpt-6-luna
LLM_INTERNAL_API_MEDIUM_VLM_MODEL=gemini-3.8-flash
LLM_INTERNAL_API_HEAVY_VLM_MODEL=gemini-3.8-flash
```

내부 서비스에서 제공한 기본 URL·모델 ID·프로젝트 ID를 사용합니다. 프로젝트 ID가
필요 없는 서비스라면 빈 값으로 두어도 됩니다. 이 프로필은 비전 호출에 내부 API
자격 증명을 사용합니다. light는 `api_type: openai`, medium·heavy는
`api_type: gemini` 계약을 사용합니다. Paddle OCR의 기본값은 `ssl: true`이므로
일반 HTTP 엔드포인트를 사용한다면 변경하세요.

## 로컬 FastAPI 프로필 실행

기존 환경을 사용하는 수동 실행 순서이며,
[`verify_local_quickstart_clean_conda.sh`](../../scripts/verify_local_quickstart_clean_conda.sh)에
대응합니다. 파서보다 먼저 라우터와 두 모델 서버를 시작합니다.

### 터미널 1: Dolphin 1.5

```bash
conda activate dolphin-15
DOLPHIN_15_DEVICE=cpu DOLPHIN_15_PORT=8200 \
  python tutorial/dolphin_15_fastapi/server.py
```

검증 스크립트와 같은 CPU 모드입니다. CUDA 환경이 준비돼 있다면
`DOLPHIN_15_DEVICE=cuda`를 사용하세요. 기본 모델은 `ByteDance/Dolphin-1.5`입니다.
로컬 모델 디렉터리를 사용하려면 시작 전에
`DOLPHIN_15_MODEL=/absolute/path/to/model`을 내보냅니다. 서버는 `127.0.0.1`에
바인딩됩니다. 포트를 바꾸면 `.env`의 `LOCAL_DOLPHIN_URL`도 변경하세요.

### 터미널 2: Paddle OCR

```bash
conda activate paddle-ocr-cpu
PADDLE_OCR_DEVICE=cpu PADDLE_OCR_HOST=127.0.0.1 PADDLE_OCR_PORT=8100 \
  PADDLE_PDX_LOCAL_FONT_FILE_PATH=/System/Library/Fonts/AppleSDGothicNeo.ttc \
  python tutorial/paddle_ocr_fastapi/server.py
```

위 폰트 경로는 macOS용입니다. Linux에서는 설치된 TTF/TTC 경로, 예를 들어
`/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`로 바꾸세요. PaddleX의 시각화
폰트를 로컬에서 제공합니다. 포트를 바꾸면 `.env`의 `LOCAL_PADDLE_URL`도 변경합니다.

두 서버는 첫 시작 시 모델을 다운로드할 수 있습니다. 초기화가 끝나고 상태
확인이 성공한 뒤 파서를 실행하세요. CPU 시작·추론에는 몇 분이 걸릴 수 있습니다.
[Dolphin 튜토리얼](tutorial/dolphin_15_fastapi/README.md)과
[Paddle 튜토리얼](tutorial/paddle_ocr_fastapi/README.md)을 참고하세요.

### 터미널 3: 라우터

```bash
conda activate pdf-parser
python tools/serve_router.py --check && \
  ROUTER_DEVICE=cpu python tools/serve_router.py --host 127.0.0.1 --port 8001
```

### 터미널 4: 상태 확인과 파서

먼저 `configs/local_quickstart.yaml`의 `input_dir`를 실제 PDF 경로로 지정하고
`output_dir`를 선택합니다. 기본 샘플 `inputs/smoke/mixed_source_9p.pdf`는
Git 무시 대상이므로 체크아웃에 없을 수 있습니다.

```bash
conda activate pdf-parser
curl --fail --noproxy '*' http://127.0.0.1:8001/health && \
  curl --fail --noproxy '*' http://127.0.0.1:8200/healthz && \
  curl --fail --noproxy '*' http://127.0.0.1:8100/healthz && \
  python main.py configs/local_quickstart.yaml
```

세 상태 응답 모두 `status: ok`를 포함해야 합니다. 포트를 바꿨다면 상태 확인
URL도 바꾸세요. CLI에는 설정 경로를 전달하고, PDF 경로는 두 번째 CLI 인자 대신
YAML에 지정합니다.

## 라우터 프로필 실행

설정된 Dolphin v2·Paddle Triton·LLM/VLM 서비스를 준비하고 위의 해당 `.env` 값을
작성합니다. 이 프로필들은 Dolphin v2·Triton 전송 방식을 사용하므로 앞 절의
로컬 FastAPI 서버는 엔드포인트 URL만 바꿔 연결할 수 없습니다.

### 터미널 1: 라우터

라우터 의존성이 설치된 기존 환경을 활성화하고 실행합니다.

```bash
python tools/serve_router.py --check && \
  python tools/serve_router.py --host 127.0.0.1 --port 8001
```

라우터는 기본적으로 CPU에서 실행하며 다음 체크포인트를 읽습니다.

| 모델 | 기본 체크포인트 | 선택적 셸 재정의 |
| --- | --- | --- |
| Stage 1 | `models/router/binary_router.pth` | `ROUTER_BINARY_CHECKPOINT` |
| Stage 2 그림 | `models/router/second_stage_fig.pth` | `ROUTER_FIG_CHECKPOINT` |
| Stage 2 표 | `models/router/second_stage_tab.pth` | `ROUTER_TAB_CHECKPOINT` |

필요하다면 두 명령을 실행하기 전에 해당 터미널에서 체크포인트 경로와
`ROUTER_DEVICE`를 내보냅니다. `--check`는 파일 존재를 확인하고, 서버 시작 시
모델을 로드합니다. `Application startup complete` 이후에도 서버를 실행해 두세요.
`--port`를 바꾸면 `.env`의 `ROUTER_SERVER_URL`도 변경합니다.

### 터미널 2: 파서

선택한 YAML의 `input_dir`와 `output_dir`를 지정하고 파서 환경을 활성화한 뒤,
프로필 **하나**를 선택합니다.

```bash
conda activate pdf-parser
curl --fail --noproxy '*' http://127.0.0.1:8001/health && \
  python main.py configs/group_internal.yaml
```

필요에 따라 설정 인자를 `configs/default.yaml`,
`configs/managed_endpoints.yaml`로 바꾸세요. 항상 설정을 명시하세요.
인자 없는 `python main.py`는 `default`를 선택합니다. 라우터 상태 응답에는
`status: ok`와 로드된 모델 3개가 표시돼야 합니다. 이 응답은 라우터만 검사하므로
다른 제공자 서비스는 별도로 확인하세요.

## 출력 확인과 서비스 종료

최종 문서는 `<output_dir>/<input-PDF-stem>.md`에 저장됩니다. 로컬 프로필의
기본 입력·출력 경로에서는 다음 명령으로 확인합니다.

```bash
ls -lh tmp/local_quickstart/*.md
```

내부 프로필은 `ls -lh tmp/group_internal/*.md`를 사용하거나 설정한 출력
디렉터리로 바꾸세요. 최종 Markdown이 비어 있지 않고 `[Error]` 표시가 없는지
확인합니다. CLI의 정상 종료만으로 모든 노드의 성공을 판단할 수는 없습니다.
텍스트·표·이미지를 PDF와 비교하고 [출력과 실패](outputs-and-failures.md)를 확인하세요.

파싱이 끝나면 시작한 서버의 각 터미널에서 `Ctrl+C`로 앱을 종료합니다.
수동 명령으로 시작한 서버는 직접 종료할 때까지 계속 실행됩니다.

## 선택: 새 환경 검증 재현

준비된 환경을 재사용하는 대신 검증 환경을 새로 재현하려면 실행합니다.

```bash
bash scripts/verify_local_quickstart_clean_conda.sh \
  configs/local_quickstart.yaml /absolute/path/to/input.pdf
```

스크립트는 격리된 새 Conda 환경(파서·Dolphin Python 3.12, Paddle Python 3.11)을
만들고, 필요한 로컬 CPU 제공자를 시작하고, CLI 실행과 최종 Markdown 검사를
수행합니다. 종료 시 자신이 시작한 프로세스를 멈추며 로그·환경 기록·생성된
YAML·출력은 `tmp/clean_conda_local_quickstart/<run-id>/` 아래에 보존합니다.
`.env`에 LLM/VLM 자격 증명이 미리 설정돼 있어야 합니다. 사용하지 않는 포트를
선택하세요. 스크립트는 로컬 제공자 URL을 재정의하며 포트는 `DOLPHIN_15_PORT`와
`PADDLE_OCR_PORT`로 지정합니다. 다른 옵션은
`bash scripts/verify_local_quickstart_clean_conda.sh --help`로 확인하세요.
설치된 폰트를 자동으로 찾으며, 사용 가능한 폰트가 없으면 체크섬을 검증한
Noto Sans KR과 OFL 라이선스를 `tmp/paddle_fonts/`에 내려받아 재사용합니다.
환경변수나 `.env`의 `PADDLE_PDX_LOCAL_FONT_FILE_PATH`로 직접 지정할 수도 있습니다.
`sh`로 실행해도 자동으로 Bash 문법을 사용합니다.

### Dolphin 모델 다운로드가 타임아웃되는 경우

Hugging Face는 모델 다운로드를 CDN으로 리다이렉트합니다. `huggingface.co`에
접속할 수 있어도 `us.aws.cdn.hf.co` 연결이 타임아웃되면 `model.safetensors`를
받지 못할 수 있습니다. HTTP 302 이후 연결 타임아웃은 리다이렉트 응답은
받았지만 실제 다운로드 서버에는 연결하지 못했다는 뜻입니다.

모델을 다운로드할 수 있는 다른 컴퓨터에서 실행합니다.

```bash
python -m pip install huggingface_hub
hf download ByteDance/Dolphin-1.5 --local-dir ./Dolphin-1.5
```

다운로드가 끝나면 `Dolphin-1.5` 디렉터리의 내용 전체를 서버의 프로젝트 아래
`models/dolphin/`으로 복사합니다. 가중치뿐 아니라 설정·토크나이저·프로세서
파일도 함께 필요합니다. 이후 서버의 프로젝트 루트에서 실행합니다.

```bash
DOLPHIN_15_MODEL="$PWD/models/dolphin" \
  bash scripts/verify_local_quickstart_clean_conda.sh
```

`DOLPHIN_15_MODEL=/home/6901188/hmg-docparser-main/models/dolphin`처럼
절대 경로로 지정해도 됩니다. 인자를 생략하면 `configs/local_quickstart.yaml`의
`input_dir`를 사용하며, 해당 입력은 실제 존재하는 PDF 파일이어야 합니다.
Dolphin 서버에 전달되도록 `DOLPHIN_15_MODEL`은 위 예시처럼 셸에서 지정하세요.
이렇게 하면 Dolphin을 로컬 파일에서 읽습니다. 패키지 설치·Paddle 모델 다운로드·
LLM/VLM 호출에 필요한 네트워크 접속은 별도로 필요합니다.

### Paddle 모델 다운로드가 멈추는 경우

한국어 인식 모델을 받을 때 `Fetching 6 files`가 표시됩니다. 텍스트 검출 모델·
한국어 인식 모델·한국어 디코더 사전을 다른 컴퓨터에서 받아 서버로 옮길 수
있습니다. 다운로드가 가능한 컴퓨터의 프로젝트 루트에서 실행합니다.

```bash
python -m pip install 'huggingface_hub>=0.24,<1' truststore
python tools/quickstart/download_paddle_models.py
```

생성된 `models/paddle/` 디렉터리 전체를 서버 프로젝트의 같은 위치로 복사합니다.
이 디렉터리에는 `PP-OCRv5_mobile_det/`, `korean_PP-OCRv5_mobile_rec/`
(`ppocrv5_korean_dict.txt` 포함), 다운로드 출처 기록이 들어 있습니다.
서버의 프로젝트 루트에서 실행합니다.

```bash
DOLPHIN_15_MODEL="$PWD/models/dolphin" \
PADDLE_OCR_MODEL_ROOT="$PWD/models/paddle" \
  bash scripts/verify_local_quickstart_clean_conda.sh
```

`PADDLE_OCR_MODEL_ROOT`를 지정하면 Paddle 서버는 이 경로의 로컬 모델과 사전을
사용합니다. 파일이 누락된 경우 다운로드를 다시 시도하지 않고 오류를 출력합니다.
패키지 설치와 LLM/VLM 호출에 필요한 네트워크 접속은 별도로 필요합니다.

## 모델과 샘플 조건

설정된 개발 fixture가 없으면 사용 권한이 있는 PDF를 직접 지정하세요. 동봉 자료의
권리는 [자산 안내](model-and-data-assets.md), 전송·보관은
[데이터 처리](privacy-and-data-handling.md)를 참고하세요. 상업적 레이아웃 분석에는
PP-DocLayoutV3를 권장합니다. 제공 라우터 프로필은 Dolphin v2 연구 라이선스의
조건을 따르며 PP-DocLayoutV3 사용에는 호환 어댑터가 필요합니다.
