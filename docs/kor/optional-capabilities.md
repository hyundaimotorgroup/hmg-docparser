# 선택적 로컬 기능

> 원문: [optional-capabilities.md](../optional-capabilities.md). 한국어 번역본입니다.

주력 `default.yaml`에는 별도 router 프로세스가 필요합니다. CLI는 서버를 자동으로 시작하지 않으며 local_quickstart는 router를 사용하지 않습니다. 편집기·telemetry·Confluence는 별도로 선택합니다.

## 선택적 로컬 라우터

주력 [CLI 설치](installation.md)에는 별도로 시작한 라우터가 필요합니다. 라우터는 local_quickstart·default·managed·group 프로필에 필요한 FastAPI 프로세스이며 세 개의 로컬 이미지 분류기를 루프백으로 파서에 제공합니다. 호스팅 API나 네트워크 배포 안내가 아닙니다. 두 프로필에는 설정된 레이아웃, OCR, LLM/VLM 엔드포인트도 필요합니다. 라우터만 시작해서는 실행할 수 없습니다. [제공자](providers.md)와 [설정](configuration.md)을 참고하세요.

### 체크포인트와 요구사항

저장소 루트에서 통합 의존성을 설치한 뒤, 라우터 프로필을 쓸 때 체크포인트를 확인합니다.

```bash
python -m pip install -r requirements.txt
python tools/serve_router.py --check
```

서버는 EfficientNet B0 체크포인트 세 개를 로드합니다. 기본 경로는 `models/router/binary_router.pth`, `models/router/second_stage_fig.pth`, `models/router/second_stage_tab.pth`입니다. 이미 가진 파일을 사용하려면 `ROUTER_BINARY_CHECKPOINT`, `ROUTER_FIG_CHECKPOINT`, `ROUTER_TAB_CHECKPOINT`에 경로를 지정하세요. `--check`는 파일 존재 여부만 확인하며 내용, 라이선스, 체크섬은 검증하지 않습니다. 시작 시 PyTorch로 로드하며 호환되지 않으면 실패합니다. 신뢰할 수 있는 로컬 위치에 보관하세요. 세 체크포인트는 [Apache-2.0](router-models.md)으로 공개하며 상업적 이용·수정·재배포가 가능합니다. 저작권·라이선스·SHA-256은 [자산 안내](model-and-data-assets.md)에 기록합니다. 기본 장치는 CPU이고 `ROUTER_DEVICE`로 로컬 PyTorch가 사용할 수 있는 장치를 선택할 수 있습니다. 공개 후보의 메모리·가속기 요구량은 측정되지 않았습니다.

### 로컬 실행

`--check` 성공 후 한 터미널에서 서버를 시작합니다.

```bash
python tools/serve_router.py
```

기본 주소는 `127.0.0.1:8001`입니다. `--host`에는 `127.0.0.1`, `::1`, `localhost`만 허용하며 외부 바인딩은 거부합니다. 다른 터미널에서 비공개 `.env` 또는 셸에 `ROUTER_SERVER_URL=http://127.0.0.1:8001`을 설정하고 프로필을 명시적으로 선택합니다.

```bash
python main.py configs/local_quickstart.yaml
```

`configs/default.yaml`은 추가 비전 모델 기능이 필요한 별도 라우터 프로필입니다. 두 프로필은 검증된 [로컬 퀵스타트](providers.md#로컬-dolphin과-paddle-및-openai)와 다릅니다. 유효한 체크포인트가 있으면 로컬 `GET http://127.0.0.1:8001/health`에서 장치와 로드 모델을 볼 수 있습니다. 라우터는 `/stage1/infer`와 `/stage2/infer`로 이미지 업로드를 받습니다. 사용자 인증이 없으므로 루프백에서만 사용하세요. 체크포인트 검사와 상태 경로는 진단 도구이며 전체 프로필 실행 검증은 별도입니다. 재배포는 동봉 [LICENSE](../../models/router/LICENSE)·[NOTICE](../../models/router/NOTICE)의 조건을 따릅니다.

## 로컬 설정 편집기

선택적 편집기는 브라우저에서 네이티브 YAML DAG를 열고 CLI와 같은 엄격한 설정 스키마 및 컴파일러로 검증합니다. 파이프라인을 실행하거나 모델 제공자를 호출하지 않습니다. 기본 [파서 CLI](installation.md)와 별도인 로컬 도구이며 호스팅 편집기 서비스는 없습니다.

`requirements.txt`를 설치한 뒤 저장소 루트에서 시작합니다.

```bash
python tools/config_editor.py
```

같은 컴퓨터에서 `http://127.0.0.1:8765`를 여세요. 진입점의 `--host`는 `127.0.0.1`만 허용하며 `--port`로 로컬 포트를 바꿀 수 있습니다. 기본 파서 의존성을 사용하고 별도 편집기 의존성은 없습니다.

### 편집과 검증

템플릿 메뉴에서 PDF 프로필 5개(default·local_quickstart·managed_endpoints·group_internal·beta)를 불러옵니다. YAML 가져오기, 노드 추가·삭제, 간선 연결·제거, 노드 ID와 엄격한 `node_config` 필드 편집, 문서 출력 노드 선택, YAML 내보내기가 가능합니다. UI는 편집 중 포트 유형과 목록 호환성을 확인합니다. **컴파일 검증** 버튼은 현재 그래프를 `/api/validate`에 보내 네이티브 스키마, 레지스트리, 컴파일러를 검사하고 실행 순서 또는 오류를 반환합니다. 파일을 처리하거나 제공자에 접속하지 않습니다. 가져오기는 YAML을 파싱한 뒤 검증합니다. 페이지를 다시 열면 그래프가 유지되지 않으므로 필요하면 `pipeline.yaml`을 내보내 저장하세요. 그래프 계약은 [설정 안내](configuration.md)를 참고하세요.

### 비밀값과 내보낸 파일

비밀 필드에는 `${API_KEY_NAME}` 같은 환경변수 참조 또는 직접 값을 넣을 수 있습니다. 직접 입력한 값은 브라우저 메모리의 그래프에 남고 검증·내보내기 요청에서 루프백 서버로 전송됩니다. 핸들러는 제출한 YAML이나 비밀값을 애플리케이션 저장소 또는 요청 로그에 쓰지 않고 요청 메모리에서 응답을 만듭니다. 내보내기는 직접 입력한 비밀값까지 전체 그래프를 다운로드되는 `pipeline.yaml`에 직렬화합니다. 가져온 파일의 전체 텍스트도 루프백 핸들러로 전송됩니다. 환경변수 참조를 사용하고 다운로드 파일을 공유·커밋하기 전에 확인하며 사용 후 탭을 닫으세요. 브라우저 다운로드와 사본의 관리는 사용자 책임입니다. 편집기는 비밀값 저장소를 제공하지 않습니다.

편집기 검증 시 일부 `${NAME}` 참조는 문자 그대로 남지만 실제 CLI 실행은 먼저 로컬 환경값으로 치환합니다. 따라서 유효한 HTTPS URL이 필요한 필드에는 편집기 검사 시 구체적인 로컬 시험값이 필요할 수 있습니다. [Confluence 절](#선택적-confluence-업로드)에 사례가 있습니다. 내보낼 시험 YAML에 실제 자격 증명을 넣지 마세요.

편집기의 Global Context `skip_levels`는 JSON 목록입니다.
default·managed_endpoints·group_internal은 `[1]`로 가져오며 `[]`는 기존 전체 대상
후처리를 복원합니다. 가져오기·내보내기·컴파일에서 설정을 유지합니다. layout의
`skip_levels`와는 별개이며
[설정 안내](configuration.md#단순-페이지의-global-context-호출-생략)를 참고하세요.
생략된 Global Context 페이지는 Langfuse에 내보낼 모델 사용량 이벤트를 만들지 않습니다.

## 선택적 Langfuse 사용량 내보내기

기본 CLI는 LLM 호출 시 사용량 메타데이터를 로컬 `<output_dir>/_llm_usage.jsonl`에 기록합니다. 현재 파서 프로필에서 외부 Langfuse 내보내기는 꺼져 있습니다. 패키지는 통합 `requirements.txt`에 포함되며, 내보내기를 사용하려면 선택한 YAML에 명시적으로 `langfuse.on: true`를 설정해야 합니다. [로컬 퀵스타트](providers.md#로컬-dolphin과-paddle-및-openai)나 다른 기본 CLI 경로에는 필요하지 않습니다.

```bash
python -m pip install -r requirements.txt
```

비공개 `.env` 또는 셸에 `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`를 설정합니다. `LANGFUSE_TRACE_NAME`은 선택값이며 기본값은 `pdf_parser_trace`입니다. YAML 설정:

```yaml
langfuse:
  on: true
```

연결값 세 개가 모두 있어야 내보내기를 사용할 수 있습니다. 내보내기는 모델/제공자, API 유형, 토큰 수, 추정 사용량, 캐시 토큰 수, 작업/노드 메타데이터를 전송합니다. generation payload에 프롬프트 텍스트, 모델 출력, 문서 본문은 넣지 않습니다. 작업 ID나 모델명도 문서 또는 제공자를 식별할 수 있으므로 활성화 전에 메타데이터와 대상지를 검토하세요. [데이터 처리](privacy-and-data-handling.md)를 참고하세요.

Langfuse import·전송 오류는 로컬 진행 상태에 기록되고 파싱 콜백은 계속됩니다. generation 내보내기 오류가 나면 이후 전송을 중단합니다. flush 오류도 파이프라인이 무시합니다. 이는 파싱이 계속된다는 뜻이며 사용량 전달을 보장하지 않습니다. 로컬 JSONL은 Langfuse와 무관하고 프롬프트·출력 텍스트를 담지 않습니다. 활성화하면 설정된 `LANGFUSE_HOST`로 메타데이터가 전송될 수 있으니 실제 실행 전에 승인된 엔드포인트와 자격 증명을 사용하세요.

Langfuse는 로컬 비용이 complete일 때만 모델명·숫자 usage·cost를 받습니다. 가격 비활성화·partial/unpriced에서는 이 필드를 생략합니다. 자동 비용 계산이 필요한 경우 [가격 설정과 제한](llm-inference.md)을 확인하세요. 백그라운드 전송 실패는 로컬 파서가 감지하지 못할 수 있습니다.

## 선택적 Confluence 업로드

Confluence 업로드는 별도 설정을 명시적으로 선택하는 로컬 CLI 파이프라인입니다. PDF 퀵스타트나 호스팅 서비스의 일부가 아닙니다. [`confluence_upload.yaml`](../../configs/optional/confluence_upload.yaml) 그래프는 로컬 `.md` 또는 `.markdown` 파일을 읽고 Markdown 및 참조한 로컬 첨부 파일을 설정된 HTTPS Confluence 사이트로 보냅니다. 페이지 생성·갱신과 첨부 파일 변경이 가능하므로 자격 증명, 허용된 외부 쓰기 권한, 검토된 대상 공간이 있을 때만 실행하세요.

### 로컬 설정

YAML은 프로세스 환경 또는 비공개 `.env`에서 다음 값을 읽습니다.

| 변수 | 용도 |
| --- | --- |
| `CONFLUENCE_INPUT_PATH` | 로컬 Markdown 파일 또는 디렉터리 |
| `CONFLUENCE_OUTPUT_DIR` | 로컬 결과 산출물·최종 Markdown 디렉터리. 입력과 분리하세요. |
| `CONFLUENCE_TOKEN` | Confluence 자격 증명 |
| `CONFLUENCE_EMAIL` | Cloud API token 계정의 email. 지원되는 Bearer 자격 증명일 때만 빈 값으로 설정하며 변수 자체는 YAML에서 필수입니다. |
| `CONFLUENCE_SPACE_ID` | 대상 공간 키 |
| `CONFLUENCE_PARENT_ID` | 새 페이지의 부모 페이지 ID |
| `CONFLUENCE_BASE_URL` | 쿼리·fragment가 없는 절대 HTTPS 사이트 URL. 필요하면 클라이언트가 `/wiki`를 추가합니다. |

제공된 그래프에는 `document_limits.allowed_extensions: [.md, .markdown]`와 `confluence_uploader`에 연결된 문서 범위 Markdown 로더가 있습니다. 루트 로더는 `depends_on`을 생략하며 런타임이 입력 `DocumentDTO`를 전달합니다. `__START__`는 fanout 루트 전용이므로 이 문서 범위 노드에서 쓰면 컴파일에 실패합니다. 업로더는 문서를 반환하고 로컬 `<title>_confluence_upload.json` 결과 파일을 씁니다. 이 파일에는 페이지 URL, 제목, ID, 오류가 들어갈 수 있으므로 공유 전에 검토하세요. 성공하면 `CONFLUENCE_OUTPUT_DIR` 아래에 `<input_stem>.md`도 씁니다. 이 파일이 이미 있으면 다음 실행에서 해당 입력을 건너뜁니다.

Markdown, 대상, 쓰기 권한을 검토한 권한 있는 운영자는 저장소 루트에서 별도 파이프라인을 실행할 수 있습니다.

```bash
python main.py configs/optional/confluence_upload.yaml
```

제공된 YAML은 `CONFLUENCE_EMAIL`을 클라이언트에 전달합니다. email이 있으면 email과 token으로 Basic 인증을, 빈 값이면 Bearer 인증을 사용합니다. Cloud API token에는 계정 email이 필요합니다. 개발 환경의 403은 email 누락으로 Bearer 인증을 사용한 것이 원인이었으며 동일 토큰에 맞는 email로 해결했습니다. 현재 클라이언트는 `/wiki`를 추가하며 Confluence Cloud에서 검증했습니다. 다른 배포 경로와 토큰 계약은 이 결과로 확인되지 않습니다.

TLS 검증은 유지합니다. Requests가 인증서 체인을 신뢰하지 못하면 비공개 `.env`의 `REQUESTS_CA_BUNDLE`에 신뢰할 수 있는 PEM CA bundle의 절대 경로를 지정하세요. 기록된 macOS 실행은 시스템 인증서를 넣은 bundle을 사용했으며 `verify=False`는 사용하지 않았습니다. 설정된 파일은 계속 보존하고 로컬 인증서 환경이 변경되면 갱신해야 합니다.

기본 `update_existing`은 `true`라 기존 페이지와 첨부를 갱신할 수 있습니다. 새 페이지 생성만 허용하려면 `node_config`에 `update_existing: false`를 지정하세요. 같은 제목이 있으면 실패합니다. 실제 자격 증명과 대상에 대한 쓰기 권한이 필요하며 설정 컴파일·로컬 로더 검사는 실제 업로드 검증이 아닙니다.

2026-10-23 승인된 개발 업로드는 새 Python 3.12 파서 환경에서 실제 uploader/client와 `update_existing: false`로 수행했습니다. 9페이지 default 결과를 페이지 1개·첨부 38개(1,043,256 bytes)로 생성했고 경고·기존 페이지 수정·삭제는 없었습니다. 다시 조회한 제목·공간·부모·본문 텍스트·표 4개·이미지 참조 38개가 일치했고 첨부를 내려받아 크기·SHA-256을 모두 확인했습니다. uploader/client 경로의 검증이며 Markdown CLI 그래프 전체를 별도로 실행한 결과는 아닙니다.

설정 편집기는 `${NAME}`을 치환하지 않고 원시 YAML을 검증합니다. 이 YAML의 `base_url`에는 구체적인 HTTPS 값이 필요해 `${CONFLUENCE_BASE_URL}` 상태로는 편집기 검증이 실패합니다. CLI는 환경변수 참조를 먼저 해석하고 그래프를 검증합니다. 안전한 오프라인 검사는 예제 환경값으로 YAML을 읽어 업로드 노드를 실행하지 않고 컴파일할 수 있습니다. 공유 YAML이나 증빙에 실제 토큰을 넣지 마세요.

## 검증과 릴리스 확인

| 기능 | 기록 범위와 별도 확인 |
| --- | --- |
| Router | 로컬 추론·health는 신뢰한 파일이 필요합니다. 가중치에 Apache-2.0·저작권 고지를 동봉합니다. 해시·후보 프로필·자원 측정은 릴리스 검사입니다. |
| 편집기 | 로컬 그래프·HTTP 계약 검사. 후보의 UI 링크·루프백 동작을 확인해야 하며 파서는 실행하지 않습니다. |
| Langfuse | 오류 처리는 위 설명과 같습니다. 허가된 실제 목적지 전달은 미검증입니다. |
| Confluence | 개발 신규 페이지·첨부 client 경로를 확인했습니다. 기존 페이지 갱신·첨부 교체·다른 배포·전체 Markdown CLI는 별도 검사입니다. |

자격 증명·보관은 [데이터 처리](privacy-and-data-handling.md), 가중치·fixture는
[자산 안내](model-and-data-assets.md), 후보 근거는 [릴리스 점검표](release-checklist.md)를
참고하세요. HTTP 본문·이미지·대기열은 [입력 한도](http-input-limits.md)에 설명합니다.


기본 local 라우터 시작은 [퀵스타트](quickstart.md)를 따르세요. 기본 capability는 프로젝트가 내부 리소스로 관리합니다. 고급 사용자 확장은 `configs/optional/model_capabilities.example.yaml`과 [LLM 안내](llm-inference.md)를 참고하며 자동 로드되지 않습니다.


`configs/beta.yaml`은 성능 검증 중인 block-context 프로필입니다. group_internal의 모델·라우터·layout/OCR 연결이 필요하며 자세한 역할·비용·실패 보존 계약은 [설정](configuration.md#성능-검증용-beta-프로필)을 참고하세요.
