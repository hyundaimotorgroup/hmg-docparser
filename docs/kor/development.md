# 개발과 검증

> 원문: [development.md](../development.md).

[설치](installation.md)로 파서 환경을 준비하고 [기여 안내](CONTRIBUTING.md)의
검토 절차를 따릅니다. 저장소 루트에서 변경에 맞는 검사를 실행하세요. 오프라인
검사와 문서 전송·비용이 발생하는 실제 추론을 구분합니다.

## 오프라인 검사

```bash
python main.py --help
python -m pip check
```

[컴파일 예제](installation.md#오프라인-컴파일-스모크-검사)는 PDF·제공자 호출 없이
`configs/local_quickstart.yaml`을 검증합니다. 그래프 변경 시 노드 등록·스키마,
DTO·목록 여부·실행 범위·의존성·동시성·출력 노드를 확인하세요.

HTTP 회귀 파일은 `tests/test_http_input_security.py`입니다. 합성 입력과 대체한 모델
startup을 사용하며 체크포인트 다운로드·실제 API 호출을 하지 않습니다. 파서 의존성에
테스트 의존성을 더 설치합니다.

```bash
python -m pip install pytest httpx 'truststore>=0.10,<1'
python -m pytest tests/test_http_input_security.py -q
```

디코딩·본문·이미지·배치·프롬프트·대기열·시간 초과/회복·편집기의 안전한 YAML 처리를
검사합니다. 전체 파서·제공자·모델 정확도 검사와는 다릅니다. 이 명령을 안내하는
릴리스에는 테스트와 참조하는 보조 모듈을 포함하세요. 의무 포맷터·린터 명령은 없습니다.

## Global Context 생략 회귀

위 테스트 의존성을 설치한 뒤 저장소 루트에서 오프라인 전체 회귀를 실행합니다.

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider tests
```

생략 기능만 확인하려면 `tests/test_global_context_skip.py`를 선택합니다. 일치하는
Stage 1 페이지의 렌더링·요청 0회, L2·레벨 미상의 기존 호출, 기본값·복원,
본문·디버그·구조화 블록·오류 보존, 혼합 페이지 조립, 앞 단계 직접 텍스트/경량 VLM,
런타임 취소를 검사합니다. 설정은 엄격한 값·모델 필수 필드·노드 범위·프로필 3개·
편집기 catalog·루프백 YAML 왕복을 검사합니다. 모델 응답은 로컬 대체 객체이며
합성 파이프라인은 실제 PDF 분할기·스케줄러·Global Context 노드·문서 조립기를
실행합니다. 실제 제공자 품질·비용의 측정은 아닙니다.

## 실제 실행과 회귀

[Dolphin](tutorial/dolphin_15_fastapi/README.md)과 [Paddle](tutorial/paddle_ocr_fastapi/README.md)의
CPU 모델 스모크는 별도 환경에서 실행하며 모델을 다운로드할 수 있습니다. 권리가
기록된 fixture를 사용하세요.

클린 Conda 스크립트는 parser/Dolphin/Paddle 환경을 각각 만들고 CPU 서버의 모델 준비
상태를 확인한 뒤 파서를 실행합니다. 기존 Conda를 사용하거나 체크섬을 확인한
Miniforge를 `tmp/miniforge3`에 설치합니다. 먼저 `.env`에 텍스트·비전 모델 ID와
자격 증명을 설정하고 비공개 개발 fixture 기본값 대신 입력을 명시하세요.

```bash
bash scripts/verify_local_quickstart_clean_conda.sh --help
bash scripts/verify_local_quickstart_clean_conda.sh configs/local_quickstart.yaml /absolute/path/to/approved.pdf
```

사용 중인 포트는 거부하고 최종 Markdown의 존재·빈 내용·`[Error]`를 검사합니다.
직접 시작한 서버는 종료 시 정리하지만 환경·로그·실행 YAML·출력은
`tmp/clean_conda_<config-name>/<run-id>/`에 남습니다. `DOLPHIN_15_PORT`와
`PADDLE_OCR_PORT`는 8200/8100이며 생성 YAML의 루프백 주소에 적용됩니다.
`QUICKSTART_READY_TIMEOUT`은 서버별 1200초입니다. 폰트 자동 탐지가 부적합하면
`PADDLE_PDX_LOCAL_FONT_FILE_PATH`를 설정하세요. 전체 옵션은 `--help`를 참고하세요.

회귀 비교 전 옵션을 확인합니다.

```bash
python tools/default_config_regression.py --help
```

`--config`, `--input`, 프로필별 `--output-root`를 선택합니다. 최초 허가된 기준은
`--record-baseline`, 비교는 같은 선택에서 이 옵션 없이 실행합니다. 제공자 호출 전에
미치환 pipeline hash와 입력 hash를 확인하며 기준 누락·불일치, 빈 출력·페이지 오류를
거부합니다. quickstart와 default 기준을 섞지 마세요. 모델 변동은 토큰·문자열 유사도
외의 검토가 필요할 수 있습니다.

후보 커밋·명령·환경/의존성·설정/입력 해시·모델/서버 버전·문서/비용 전제·결과·산출물을
기록하고 공유 전 [데이터 처리](privacy-and-data-handling.md)를 따릅니다. Confluence
쓰기와 Langfuse 전달에는 허가된 대상과 별도 검증이 필요합니다.

## 노드 추가와 변경

1. 데이터 계약 변경 시 DTO·인터페이스를 갱신합니다. 조율은 `core/nodes/`, 재사용
   처리는 `core/services/`, 외부 호출은 `core/adapters/`에 둡니다.
2. `core/engine/registry/bootstrap.py`에 노드, `core/engine/config/node_config.py`에
   스키마를 등록하고 입력·출력·목록·범위·의존성·최종 출력 노드를 확인합니다.
3. 합성·허가된 fixture로 적절한 컴파일·실행·실패 테스트를 추가하고 페이지 복구·출력을 확인합니다.
4. [아키텍처](architecture.md), [설정](configuration.md), [제공자](providers.md),
   [출력](outputs-and-failures.md), [데이터 처리](privacy-and-data-handling.md)의
   영문·한국어를 함께 갱신합니다.

## 검증 범위

Global Context 생략 정책 적용 전 개발 실행은 macOS arm64/Python 3.12의 로컬 퀵스타트, default,
Confluence 신규 페이지·첨부 client 경로를 다룹니다. 모든 릴리스·플랫폼의 보장이
아닙니다. managed/group 전체 실행, 실제 Langfuse 전달, Confluence 갱신·첨부 교체,
PP-DocLayoutV3 연동은 별도 확인이 필요합니다. 현재 후보는
[릴리스 점검표](release-checklist.md), fixture·가중치 조건은
[자산 안내](model-and-data-assets.md)를 참고하세요.


기본 capability 갱신은 프로젝트 유지보수자가 내부 `core/adapters/models/resources/model_capabilities.yaml`의 정확한 identity·검증 출처·날짜를 확인하고 관련 reasoning/usage 회귀를 실행해 배포합니다. 일반 사용자에게 기본 YAML 편집을 요구하지 않습니다. clean Conda는 parser 환경에서 CPU 라우터를 시작하고 `/health`의 실행 instance·세 모델 로딩, checkpoint SHA-256, 페이지별 Stage 1/2·usage·원문 보존과 소유 PID cleanup을 기록합니다. `ROUTER_PORT` 기본값은 8001입니다.

## Beta 검증

beta는 성능 검증 중이며 기본 파이프라인으로 승격한 것이 아닙니다. 역할·schema·원문·재시도·병렬·취소·시간 예산·transport·formatter·DAG 검사는 `tests/test_block_context_*.py`를 실행합니다. 실모델 비교는 같은 upstream DTO를 재사용한 복원 비교와 전체 E2E를 구분하고 원문 사실 보존·문맥 품질·실패율·actual usage·지연·메모리를 기록합니다. 현재 실적과 제한은 실행 보고서에 분리해 기록하며 원본 프로젝트의 점수를 OSS 실적으로 재사용하지 않습니다.


2026-11-25 새 그래프 검증: mixed_source_9p의 local clean Conda 실행은 parser/router 3.12·Dolphin 3.12·Paddle 3.11을 새로 설치해 9페이지, Stage 1/2 페이지 기록 각 9개, Stage 2 요소 35개, 실제 LLM/VLM 요청 35회를 확인했습니다. default는 동일 PDF에서 9페이지·Stage 2 요소 16개·모델 요청 17회를 확인했습니다. 두 실행 모두 6·7·8페이지 요청 0회와 내장 텍스트 보존, 누락·중복·페이지 오류 없음 및 소유 라우터 정리를 확인했습니다. 제공자 모델과 Dolphin 버전 차이로 요청 수·본문이 달라질 수 있습니다. beta의 성능 평가는 별도입니다.

beta의 2026-11-25 실측은 공개 design 자료 앞 2페이지입니다. 전체 CLI 실행은 2페이지를 완료했으며 모델 요청 44회·보고된 토큰 143,070개, 복원 대상 23개 중 성공 14개·원문 유지 9개를 기록했습니다. 별도의 동일 추출 DTO·동일 judge 비교에서는 baseline 133/149, beta 130/149의 사실을 보존했고 판정 실패는 없었습니다. 이 표본에서는 개선이 확인되지 않았으며 복원 요청·토큰이 증가했습니다. 더 넓은 데이터셋과 worker 1/2/8 지연·메모리 비교는 아직 측정하지 않았습니다.
