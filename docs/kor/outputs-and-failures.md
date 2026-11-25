# 출력과 실패

> 원문: [outputs-and-failures.md](../outputs-and-failures.md). 한국어 번역본입니다.

선택한 YAML의 `output_dir`가 출력 루트입니다. local 기본 입력은 `mixed_source_9p.pdf`이며 최종 파일은 `tmp/local_quickstart/mixed_source_9p.md`, 중간 조립 파일은 `mixed_source_9p_GLOBAL_CONTEXT_EXT.md`입니다. 출력 노드는 `global_context_assemble`입니다. 예전 local의 pdfplumber/LAYOUT/COMBINE_TEXT 파일과 3페이지 실행 기록은 이전 그래프에 해당합니다.

| `output_dir` 아래 경로 | 생성 조건 |
| --- | --- |
| `<stem>.md` | 출력 노드의 문서 결과에 Markdown이 있을 때 생성하는 최종 문서 |
| `<stem>_<task_name><save_suffix>.md` | 설정된 Markdown 저장 또는 조립 노드가 실행될 때 |
| `imgs/` | 이미지 VLM 분기가 Markdown에서 참조하는 이미지 영역을 저장할 때 |
| `table_imgs/` | 표 VLM 분기가 표 영역을 저장할 때. `include_table_crop_images`가 참이면 Markdown에 링크할 수 있습니다. |
| `_llm_usage.jsonl` | LLM/VLM 공급자 사용량을 기록할 때. 가격은 선택적 로컬 추정이며 누락 토큰은 null입니다. |
| `_private/*_debug*.md` | 저장/조립 노드의 `save_debug_artifacts: true`가 디버그 내용을 저장할 때 |
| `_private/structured-recovery/*_structured_recovery.json` | 구조화된 표 토큰을 복원하지 못할 때. 미해결 토큰과 원본 표 내용을 포함합니다. |
| `_private/dolphin_failures/page_<N>_<phase>.json` | Dolphin 렌더링·요청·레이아웃 검증이 실패할 때. 검증 진단에는 원본 레이아웃 응답과 이미지 크기가 포함되며 산출물 ZIP에서 제외합니다. |
| `_page_split/`, `_layout_crops/` | 임시 분할 PDF와 레이아웃 영역. 해당 노드의 `keep_page_artifacts: true`가 아니면 입력별 처리 후 삭제합니다. |

임시 레이아웃 영역을 삭제해도 이미지·표 영역 디렉터리는 남을 수 있습니다. 기존 로컬 결과에는 `imgs/`와 `table_imgs/`가 있었습니다. 로컬 출력 파일은 자동으로 모두 삭제되지 않습니다. 보관하거나 공유하기 전에 [데이터 처리](privacy-and-data-handling.md)를 참고하세요.

## Global Context를 생략한 페이지

default·managed_endpoints·group_internal은
`global_context_page.node_config.skip_levels: [1]`로 Stage 1 L1의 Markdown을
유지합니다. 페이지 노드는 본문·표·이미지 링크·구조화 블록·디버그 내용·DTO `failures`를
반환합니다. 조립기는 페이지를 순서대로 포함하고 `@page:N`을 한 번씩 붙입니다.
앞 단계 페이지 오류는 기존 오류 경로를 유지하며 정상 페이지로 바뀌지 않습니다.
생략 페이지의 추가 Global Context 사용량 기록은 없고 앞 단계 모델 호출의 기록은
유지합니다. `[]`로 전체 대상 후처리를 복원하는 방법은
[설정 안내](configuration.md#단순-페이지의-global-context-호출-생략)에 있습니다.

## 표와 페이지 오류

앞 단계 추출이 성공한 뒤 Global Context 정제만 실패하면 기존 Markdown·복원된
표·이미지 참조를 보존하고 뒤에 오류 표시를 붙입니다. 페이지 실패 메타데이터도
유지합니다. 앞 단계 레이아웃·OCR·표·이미지 오류는 기존 실패 경로를 따르며,
정제 입력을 보존한다고 정제 실패가 성공으로 바뀌지는 않습니다.

`table_vlm_caption_maker.node_config.table_output_format`에는 `markdown`, `html`, `json`, `toon`을 지정할 수 있습니다. PDF 프로필 5개 모두 `markdown`을 사용합니다. 표 HTML은 정제된 후 선택한 형식으로 변환됩니다. 구조화된 표 자리표시자는 텍스트 병합 후 복원됩니다. 제공자 토큰이 누락되면 검증된 표 텍스트가 뒤에 추가될 수 있으며, 해결되지 않은 토큰은 보존되고 복구 산출물에 기록됩니다.


오류 문구, 디버그 Markdown, 복구 JSON, 이미지는 원문 내용이나 제공자 오류 세부 정보를 담을 수 있습니다. 로그·산출물을 게시하기 전에 자격 증명과 문서 내용을 제거하세요. 최종 `<stem>.md`가 `output_dir`에 있으면 입력 스캐너가 해당 파일을 건너뜁니다. 재실행 결과를 비교하려면 새 출력 디렉터리를 사용하세요.

## 예제 출력 공유

공유 전 최종·중간 Markdown, 이미지·표·오류·디버그·복구 산출물을
[데이터 처리](privacy-and-data-handling.md)에 따라 함께 검토하세요. 원본 PDF와 파생
결과의 재배포 조건은 [자산 안내](model-and-data-assets.md)에서 확인합니다. 후보
검증에는 허가된 원본과 결과 대조, 비공개 내용 검사가 포함되며 근거는
[릴리스 점검표](release-checklist.md)에 기록합니다.


clean Conda 검증은 `stage1_report.jsonl`의 모든 페이지 결과, `stage2_report.jsonl`의 필요한 요소 분류, `_llm_usage.jsonl`, 최종 페이지 누락·중복·오류와 내장 텍스트 보존을 검사합니다. health 성공만으로 사용 성공을 판단하지 않습니다.

## Beta 출력과 보조 실패

beta 최종 출력은 `<stem>.md`, 중간 조립은 `<stem>_BLOCK_CONTEXT.md`이며 출력 노드는 `block_context_assemble`입니다. `block_context_report.jsonl`의 역할·페이지·블록별 restored/failed/attempts를 함께 확인하세요. 모델 요청 성공과 원문 보존 검사 성공은 별도입니다. 실패한 복원은 원문을 유지하고 정상 추출 페이지를 오류 페이지로 바꾸지 않습니다. 기본 debug는 꺼져 있으며 켜면 reasoning·원본 HTML은 `_private`에만 저장합니다.


2026-11-25 새 그래프 검증: mixed_source_9p의 local clean Conda 실행은 parser/router 3.12·Dolphin 3.12·Paddle 3.11을 새로 설치해 9페이지, Stage 1/2 페이지 기록 각 9개, Stage 2 요소 35개, 실제 LLM/VLM 요청 35회를 확인했습니다. default는 동일 PDF에서 9페이지·Stage 2 요소 16개·모델 요청 17회를 확인했습니다. 두 실행 모두 6·7·8페이지 요청 0회와 내장 텍스트 보존, 누락·중복·페이지 오류 없음 및 소유 라우터 정리를 확인했습니다. 제공자 모델과 Dolphin 버전 차이로 요청 수·본문이 달라질 수 있습니다. beta의 성능 평가는 별도입니다.
