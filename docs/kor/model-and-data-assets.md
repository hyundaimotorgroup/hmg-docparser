# 모델·데이터 자산

> 원문: [model-and-data-assets.md](../model-and-data-assets.md).

[파서 라이선스](../../LICENSE)는 코드에 적용됩니다. 모델·사전·PDF·이미지·파생 정답에는
별도 출처·권리 기록이 필요합니다. 온라인 공개·가명처리만으로 재배포가 허가되지는 않습니다.
다운로드 모델과 동봉 파일을 구분합니다.

## 모델 선택

| 모델 | 조건 | 연동 |
| --- | --- | --- |
| [PP-DocLayoutV3](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3) | 모델 카드의 Apache-2.0. 상업적 활용 권장. | 호환 어댑터 필요. 제공 프로필·벤치마크에 포함되지 않음. |
| [Dolphin 1.5](https://huggingface.co/ByteDance/Dolphin-1.5) | 모델 카드의 MIT | 로컬 FastAPI 다운로드 또는 `DOLPHIN_15_MODEL`. [과거 예제 MIT 고지](../../third_party/licenses/Dolphin-1.5-demo-MIT.txt)는 별도로 보존. |
| [Dolphin v2](https://huggingface.co/ByteDance/Dolphin-v2) | [Qwen 연구 라이선스](https://huggingface.co/ByteDance/Dolphin-v2/blob/main/LICENSE). 비상업 연구·평가, 상업 이용은 별도 라이선스. | vLLM/제공자 연동·벤치마크 설정1. |
| Paddle [검출](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det)·[한국어 인식](https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec) | 모델 카드의 Apache-2.0 | 튜토리얼 모델·사전 다운로드, 운영자 관리 Triton. |
| [Router EfficientNet B0](router-models.md) | Apache-2.0, Copyright (c) 2026 Hyundai Motor Group. 조건에 따른 상업적 이용·수정·재배포 허용. | [LICENSE](../../models/router/LICENSE)·[NOTICE](../../models/router/NOTICE)를 동봉한 `.pth` 세 개. |
| LLM/VLM | 제공자 약관 또는 자체 모델의 라이선스 | YAML 모델명은 접근·보관·권리·비용·호환성 보장이 아님. |

다운로드 리비전·라이선스 사본/고지·해시·필요한 상업 허가를 기록하세요. 원본의 모든
리비전이 같은 조건이라고 가정하지 않습니다. 캐시는 파서 소스와 별개이며 체크포인트는
신뢰하는 파일만 로드합니다.

## 참조 코드와 의존성

검토된 의존성 이름·버전·출처·저작권과 라이선스 전문은
[THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES)에 있습니다. 소스코드 공개 시
이 파일과 [LICENSE](../../LICENSE)를 포함하세요.

| 자료 | 출처와 고지 |
| --- | --- |
| Dolphin 1.5 예제 | [참조 리비전](https://github.com/bytedance/Dolphin/blob/b6c7978ffd/demo_page.py), MIT, Copyright 2025 ByteDance Ltd. and/or its affiliates. [MIT 전문](../../third_party/licenses/Dolphin-1.5-demo-MIT.txt) 보존. |
| PaddleOCR | [프로젝트](https://github.com/PaddlePaddle/PaddleOCR), [Apache-2.0](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE). 다운로드하는 [한국어 사전](https://github.com/PaddlePaddle/PaddleOCR/blob/main/ppocr/utils/dict/ppocrv5_korean_dict.txt)의 원본 조건도 보존. |
| TOON | 선택적 표 출력의 [형식 명세](https://github.com/toon-format/toon). |
| py-toon-format 0.1.0 | [Python 구현](https://github.com/ErtugrulKra/py-toon-format), [MIT 메타데이터](https://pypi.org/project/py-toon-format/0.1.0/). 재배포 시 배포물의 고지를 보존. |
| pypdfium2/PDFium | [프로젝트](https://github.com/pypdfium2-team/pypdfium2), [라이선스](https://pypdfium2.readthedocs.io/en/stable/readme.html#licensing). 바인딩·PDFium·동봉 의존성의 고지를 구분하고 바이너리 재배포 시 실제 빌드에 포함된 라이선스를 보존. |

## 라우터 체크포인트 라이선스

EfficientNet B0 가중치 세 개는 Apache-2.0으로 공개하며 상업적 이용·미세조정·재배포가
가능합니다. 라이선스·고지를 보존하고 변경 사실을 표시하세요. 적용 범위와 전체 조건은
[라우터 모델 안내](router-models.md)에 있습니다. 다른 모델과 샘플 데이터에는
각각의 조건이 적용됩니다.

## 동봉 목록

[assets/manifest.json](../assets/manifest.json)에 경로·크기·SHA-256·출처/권리를 기록합니다.
`not_recorded`는 자산별 허가 기록이 동봉되어 있지 않다는 뜻입니다. 출처·권리자·
라이선스의 null은 증거 부재 표시이며 재배포 허가가 아닙니다.

| 그룹 | 파일·용도 |
| --- | --- |
| 라우터 | `models/router/binary_router.pth`, `second_stage_fig.pth`, `second_stage_tab.pth`: 페이지·요소 분류. |
| 입력 PDF | `inputs/test_KIA_EV9_price.pdf`. |
| 튜토리얼 이미지 | `tutorial/dolphin_15_fastapi/layout_smoke_page.png`, `tutorial/paddle_ocr_fastapi/paddle_test.png`. |
| 평가 PDF | `tools/eval/dp_evalset_simple.pdf`, `dp_evalset_design.pdf`, `dp_evalset_external.pdf`: 공개 릴리스 후보 자료. |
| 평가 정답 | `tools/eval/*_gt.md`, `fact_dict_*.pkl`: 기준 사실. `eval_prompt.md`: judge 프롬프트·예제. |

포함된 파일이라도 허가 증거는 아닙니다. 자산·출력을 재게시하기 전에 원출처·제작/권리
주체·라이선스·허가 범위·편집·공개 검토를 기록하거나 제외하세요. 파생 Markdown·크롭·
사실에 원문이 남을 수 있습니다. 내부 general/manufacturing 세트는 공개하지 않습니다.

## 무결성과 안전한 사용

저장소 루트에서 [영문 해시 확인 명령](../model-and-data-assets.md#integrity-and-safe-use)을
실행하면 모델·pickle을 로드하지 않고 크기·SHA-256을 대조합니다. 해시는 동일성의
근거이며 권리나 직렬화 안전성 보장은 아닙니다. Router `--check`는 존재만 확인합니다.
교체 파일·메타데이터를 함께 갱신하고 회귀 기준을 조용히 바꾸지 마세요.
[평가](evaluation.md), [데이터 처리](privacy-and-data-handling.md),
[릴리스 점검표](release-checklist.md)를 참고하세요.
