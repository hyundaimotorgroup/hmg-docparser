# 변경 이력

> 원문: [CHANGELOG.md](../../CHANGELOG.md).

주요 사용자 변경을 [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) 형식으로
기록합니다. 공개 릴리스에는 [Semantic Versioning](https://semver.org/spec/v2.0.0.html)을
사용합니다. 최초 릴리스 버전·날짜는 여기서 지정하지 않았습니다.

## [Unreleased]

### 추가

- 기본 모델 capability 로딩 실패가 기본 호출을 막지 않도록 처리하고 운영자 규칙 파일의 검증·기본 규칙 상속을 지원합니다. 명시한 미지원 reasoning은 호출 전에 오류로 처리합니다. [사용법](llm-inference.md#모델-capability와-운영자-확장).

- 사용량과 선택적 가격 계산을 분리하고 네 줄 운영자 가격표·cache read·입력 구간을 지원합니다. 회계 실패는 정상 파싱을 보존하며 snapshot 없는 기록도 재계산할 수 있습니다. [설정 안내](llm-inference.md).

- 타입 DTO·엄격한 컴파일·페이지 스케줄링·동시성 설정·문서 조립을 갖춘 YAML DAG.
- PDF 텍스트 추출, Dolphin 레이아웃, PaddleOCR, 표·이미지 VLM 해석, Markdown·이미지·
  구조화 표 출력.
- 로컬 Dolphin 1.5/Paddle 튜토리얼, 라우터, 설정 편집기, 선택적 Langfuse 사용량
  전송, 별도 Confluence 업로드 파이프라인.
- 영문·한국어 기여·보안·행동 강령·데이터 처리·릴리스·모델/데이터·제3자·평가 문서와
  Issue/PR 양식.

### 변경

- Global Context에 0 이상의 엄격한 정수 목록 `skip_levels`를 추가했습니다. 기본값은
  `[]`이며 default·managed_endpoints·group_internal은 `[1]`로 Stage 1 L1의
  추가 렌더링·VLM 요청 없이 기존 내용을 유지합니다. 오류·페이지 순서·표·이미지 링크·
  구조화 블록·디버그 내용을 보존합니다. `[]`로 전체 대상 후처리를 복원할 수 있고
  필요한 경량 페이지 호출은 유지됩니다.

### 수정

- Whole-page VLM에 본문 전용 응답 스키마를 지정해 JSON 포장이 최종 Markdown에
  노출되지 않도록 했습니다. 내장 텍스트 추출과 L1 Global Context 생략은 유지합니다.
- OpenAI chat은 명시된 경우에만 `temperature`를 전송합니다.
- 종료 이유가 없는 스트림은 기존 횟수·시간 한도 내에서 재요청하고, 부분 출력을
  완료된 페이지로 처리하지 않습니다.
- Global Context 정제 실패 시 성공한 본문·표·이미지를 보존하면서 오류를 기록합니다.
  Dolphin 실패에는 비공개 진단 산출물을 남깁니다.
- 모델 설명과 본문에 같은 표 참조가 있어도 잘못된 표 복원 실패를 기록하지 않습니다.
- default·managed_endpoints·group_internal의 Paddle SSL은 `PADDLE_SSL`로
  설정하며 기본값은 `true`입니다. HTTP 서버에는 `false`를 지정할 수 있습니다.

### 보안

- 로컬 HTTP 서버의 본문·이미지·픽셀·배치·프롬프트·대기열·본문 수신 시간 한도,
  YAML 확장 한도.
- 의존성 버전 고정과 secret-scan workflow 설정.

### 문서

- 파서의 Apache-2.0 라이선스와 조직 CLA 링크.
- EfficientNet B0 라우터 가중치 세 개의 Apache-2.0·저작권 고지와 상업적 이용·수정·재배포 허용.
- 상업적 활용용 PP-DocLayoutV3(Apache 2.0) 권장, Dolphin v2 연구 라이선스 조건과
  벤치마크 설정 구분.

### 알려진 제한

- PP-DocLayoutV3는 호환 레이아웃 어댑터가 필요하며 제공 프로필·보고된 벤치마크에
  포함되어 있지 않습니다.
- managed/group 전체 실행, 실제 Langfuse 전달, Confluence 갱신·첨부 교체에는
  별도 검증이 필요합니다.
- 샘플·평가 자료 권리는 별도 기록이 필요합니다. 저장소 포함이 파서의
  라이선스를 모든 제3자 자료에 적용한다는 뜻은 아닙니다.
