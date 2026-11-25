# 평가 자료와 방법

> 원문: [tools/eval/README.md](../../tools/eval/README.md).

[README 성능표](README.md#성능)는 사실 단위 보존율을 보고합니다. 평가 디렉토리에는
PDF 3개, 사람이 읽을 수 있는 정답, 직렬화된 사실 사전, judge 프롬프트·예제가 있습니다.

| 세트 | 내용 | PDF | 정답 | 직렬화 사전 |
| --- | --- | --- | --- | --- |
| Simple | 비교적 쉬운 ebook | [PDF](../../tools/eval/dp_evalset_simple.pdf) | [Markdown](../../tools/eval/dp_evalset_simple_gt.md) | `fact_dict_simple.pkl` |
| Design | 가명화된 디자인·검토 문서 | [PDF](../../tools/eval/dp_evalset_design.pdf) | [Markdown](../../tools/eval/dp_evalset_design_gt.md) | `fact_dict_design.pkl` |
| External | 어려운 혼합 샘플 | [PDF](../../tools/eval/dp_evalset_external.pdf) | [Markdown](../../tools/eval/dp_evalset_external_gt.md) | `fact_dict_external.pkl` |

내부 general/manufacturing PDF는 공개 데이터가 아닙니다. 동봉 파일의 출처·라이선스·
허가는 [자산 목록](../assets/manifest.json)에서 기록하며 미기록 필드가 허가를 뜻하지
않습니다. 재게시 전 권리를 확인하세요. pickle은 신뢰하는 파일만 역직렬화하고
내용 확인에는 Markdown 정답을 사용할 수 있습니다.

## 재현 절차

1. [자산 안내](model-and-data-assets.md#무결성과-안전한-사용)에 따라 해시를 확인합니다.
2. 명시한 그래프·허가된 모델·새 출력 디렉토리로 PDF를 파싱하고 커밋·YAML/입력 해시·
   노드/모델·프롬프트 버전·추론 설정·최종 출력을 기록합니다.
3. 정답 사실과 페이지 출력을 일관되게 맞춥니다. 사전·분류 범위는
   [eval_prompt.md](../../tools/eval/eval_prompt.md)에 있습니다.
4. judge callable을 준비해 사실/출력 쌍마다 `judge_fact_from_text` 예제를 실행합니다.
   보고된 평가는 `gpt-5.4-mini`를 사용했습니다. 사용할 수 있는 모델로 대체하면 이를
   기록하세요. 사실·파싱 텍스트 전송에는 공개 위험과 비용이 있을 수 있습니다.
5. 모든 기대 사실에 유효한 판정이 있는지 확인하고 실패·누락·잘못된 응답을 별도
   기록합니다. 분모에서 조용히 제외하지 말고 이유·결과와 집계 방법을 보존합니다.

`eval_prompt.md`는 실행 CLI가 아닌 프롬프트·코드 발췌입니다. `llm(prompt)` callable,
시간 초과 예외와 Tenacity retry import, 사실/페이지 연결, 결과 수집은 실행 환경에서
준비해야 합니다. 원본 출력은 `이유`, `결과` 키가 있는 Python dict이며
`ast.literal_eval` 등으로 안전하게 파싱하고 스키마를 확인하세요. `eval`을 사용하지
마세요. 이 저장소에는 완전한 judge runner가 없습니다.

Global Context가 있는 프로필은 `skip_levels: [1]`을 사용합니다. 새 평가에는 이 값을
그래프·모델 버전과 함께 기록하세요. `[]`로 전체 대상 후처리를 복원할 수 있습니다.
과거 README 점수·비용·속도는 생략 정책의 실측 결과가 아닙니다.

## 점수의 의미와 한계

점수는 기준 사실 중 `True` 판정 비율이며 별도 precision/recall이나 시각적 재현
보장이 아닙니다. 예제는 추론·모순·누락·표의 행/빈 셀 의미를 다룹니다. LLM 판정과
출력은 달라질 수 있으므로 분모·누락 판정·데이터/페이지 범위·설정을 기록하세요.
예제 집계기는 제공된 판정만 세므로 전체 데이터 점수로 쓰려면 누락을 먼저 확인합니다.

README 설정1은 Dolphin v2, 설정2는 Dolphin 1.5입니다. PP-DocLayoutV3는 상업적
활용 권장 모델이며 해당 점수에 포함되지 않습니다. [모델 조건](model-and-data-assets.md),
[데이터 처리](privacy-and-data-handling.md), [공개 점검](release-checklist.md)을 참고하세요.
