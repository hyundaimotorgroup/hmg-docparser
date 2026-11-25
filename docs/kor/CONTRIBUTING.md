# 기여 안내

> 원문: [CONTRIBUTING.md](../../.github/CONTRIBUTING.md).

버그 신고, 문서 개선, 테스트, 오류 수정, 새 노드와 제공자 어댑터 기여를 환영합니다.
이 프로젝트는 한국어 업무 PDF와 Markdown 출력에 초점을 둡니다.
[기존 이슈](https://github.com/hyundaimotorgroup/hmg-doc-parser/issues)와 PR을 먼저
검색하고, 파이프라인이나 공개 계약을 크게 바꾸려면 이슈에서 제안을 논의하세요.
참여자는 [행동 강령](CODE_OF_CONDUCT.md)을 따릅니다. 취약점은 공개하지 말고
[보안 정책](SECURITY.md)의 비공개 경로로 신고하세요.

## 신고와 제안

버그·기능 요청·질문 양식을 사용합니다. 재현 명령, 기대/실제 동작, OS/Python 버전,
YAML 프로필, 제공자·모델 ID, 관련 오류를 적습니다. 합성 문서나 공유 권한이 있는
샘플을 사용하고 설정·스크린샷·로그의 자격 증명, 내부 주소, 개인정보, 문서 유래
내용을 제거하세요. 기밀 PDF나 체크포인트는 첨부하지 마세요.

## 개발과 PR 절차

1. [저장소](https://github.com/hyundaimotorgroup/hmg-doc-parser)를 fork하고 `main`에서
   `fix/layout-boxes`, `docs/quickstart`처럼 목적이 드러나는 브랜치를 만듭니다.
2. [설치](installation.md)와 [개발·검증](development.md)을 따릅니다. 파서는 Python
   3.12를 사용하고 Dolphin/Paddle 튜토리얼은 별도 환경에 설치합니다.
3. 변경 범위를 작게 유지하고 주변 Python 스타일과 타입 표기를 따릅니다. 새 노드와
   설정 스키마는 [노드 추가 안내](development.md#노드-추가와-변경)에 따라 등록합니다.
4. 관련 검사를 실행하고 계약·실패 동작을 바꾼 경우 적절한 테스트를 추가합니다.
   오프라인 컴파일 검사는 제공자 자격 증명이 필요 없습니다. 실제 추론은 문서를
   전송하고 비용을 발생시킬 수 있으므로 사용 권한이 있는 서비스·문서를 선택합니다.
5. DTO·설정·제공자·출력·데이터 처리 등 영향받는 문서와 한국어 대응 문서를 갱신합니다.
6. PR 양식에 문제, 변경 내용, 관련 이슈, 검증 결과, 호환성 영향을 적어 제출합니다.

커밋은 `fix(layout): preserve reading order`처럼
[Conventional Commits](https://www.conventionalcommits.org/) 형식을 권장합니다.
의무화된 저장소 전체 포맷터·린터 명령은 없습니다. 유지관리자는 기술 품질·보안·
라이선스·범위를 검토하고 수정 요청이나 PR 거절을 할 수 있습니다.

## 기여자 라이선스 동의서

기여에는 현대자동차그룹 CLA가 적용됩니다. 조직 원문을 먼저 읽으세요.

- [CLA 한국어](https://github.com/hyundaimotorgroup/.github/blob/main/legal/CLA-KOR.md)
- [CLA 영어](https://github.com/hyundaimotorgroup/.github/blob/main/legal/CLA-ENG.md)

CLA는 기여에 사용하는 인증된 GitHub 계정의 전자 동의를 설명합니다. PR에 안내되는
절차를 따르며, 유지관리자는 병합 전에 해당 동의를 확인해야 합니다. 안내가 없으면
[opensource@hyundai.com](mailto:opensource@hyundai.com)에 CLA 절차를 문의하세요.
PR 제출 자체가 전자 동의 기록은 아니며 자동 CLA 검사가 설치되어 있다는 의미도 아닙니다.

고용주의 필요한 허가를 포함해 기여할 권한이 있는 작업만 제출하세요. 제3자 자료의
출처·라이선스를 공개하고 필요한 고지를 보존하세요. 파서 코드 기여는
[Apache-2.0](../../LICENSE)으로 배포됩니다. 모델·데이터·제3자 자료에는 별도 조건이
있을 수 있으므로 [제3자 고지](../../THIRD_PARTY_NOTICES)와
[모델·데이터 자산](model-and-data-assets.md)을 확인하세요.

## 문의

기술 질문·기능 요청은 [GitHub Issues](https://github.com/hyundaimotorgroup/hmg-doc-parser/issues)를
사용합니다. 비공개 그룹 서비스 접근은 [제공자 안내](providers.md#그룹-및-내부-설정),
취약점은 [보안 신고](SECURITY.md), 커뮤니티 행동 문제는
[행동 강령 신고](CODE_OF_CONDUCT.md#집행) 경로로 접수합니다.
