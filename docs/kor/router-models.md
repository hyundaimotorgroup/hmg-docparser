# Router EfficientNet B0 체크포인트

> 원문: [models/router/README.md](../../models/router/README.md).

Copyright (c) 2026 Hyundai Motor Group.

동봉 라우터 체크포인트 세 개는 [Apache License 2.0](../../models/router/LICENSE)으로
공개합니다. 라이선스 조건에 따라 상업적·비상업적 이용, 수정·미세조정, 원본 및 수정
가중치의 재배포가 가능합니다. 라이선스가 허용하는 이용에 프로젝트의 별도 승인은
필요하지 않습니다.

## 체크포인트

| 파일 | 아키텍처 | 용도 |
| --- | --- | --- |
| `binary_router.pth` | EfficientNet B0 | Stage 1 페이지 라우팅. |
| `second_stage_fig.pth` | EfficientNet B0 | Stage 2 그림·이미지 라우팅. |
| `second_stage_tab.pth` | EfficientNet B0 | Stage 2 표 라우팅. |

라우터는 `torchvision.models.efficientnet_b0(weights=None)`을 생성한 뒤 분류기
헤드를 포함한 체크포인트 상태를 로드합니다. 파일·크기·SHA-256·라이선스 정보는
[자산 목록](../assets/manifest.json)에 있습니다. 설치·경로 재정의·루프백 서버는
[로컬 라우터 안내](optional-capabilities.md#선택적-로컬-라우터)를 참고하세요.

## 재배포와 저작권 고지

가중치를 재배포할 때 [LICENSE](../../models/router/LICENSE)와
[NOTICE](../../models/router/NOTICE)를 포함하세요. 관련 저작권·출처 고지를 보존하고
Apache-2.0의 요구에 따라 변경한 파일에 변경 사실을 표시합니다. 의존성·다른 모델·
데이터의 별도 라이선스 조건은 그대로 적용됩니다.

체크포인트는 **있는 그대로(AS IS)** 제공하며 보증이나 조건을 부여하지 않습니다.
상표 사용 권한이나 정확도를 보장하지 않습니다. 사용·특허·재배포·책임의 전체 조건은
영문 라이선스를 확인하세요. 신뢰하는 파일만 로드하고, 해시는 동일성 확인이며
직렬화 안전성이나 문서에 대한 적합성을 보장하지 않는다는 점을 참고하세요.
