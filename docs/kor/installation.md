# 설치 및 검증

> 원문: [installation.md](../installation.md). 한국어 번역본입니다.

2026-10-23에 macOS arm64, Python 3.12.15의 새 Conda 환경에서 로컬 전체 실행을 마쳤습니다. 다른 플랫폼과 Python 버전의 전체 파이프라인은 아직 검증되지 않았습니다. 파서 CLI는 사용자의 컴퓨터에서 실행됩니다. Dolphin과 Paddle 튜토리얼 서버는 [로컬 안내](providers.md#로컬-dolphin과-paddle-및-openai)에 따라 각자의 환경에 설치합니다.

공개된 소스를 clone하고 저장소 루트에서 명령을 실행합니다.

```bash
git clone https://github.com/hyundaimotorgroup/hmg-doc-parser.git
cd hmg-doc-parser
```

파서를 설치하고 CLI를 확인합니다.

```bash
conda create -n pdf-parser python=3.12 -y
conda activate pdf-parser
python -m pip install -r requirements.txt
python main.py --help
```

[`requirements.txt`](../../requirements.txt)는 파서·로컬 라우터·Langfuse 내보내기의 의존성을 통합한 단일 파일입니다. 선택 기능의 패키지도 의존성 스캐너가 확인할 수 있도록 실제 설치 항목으로 포함하고, 주석으로 용도를 구분합니다. 설치만으로 라우터가 시작되거나 Langfuse 내보내기가 활성화되지는 않습니다. local_quickstart는 라우터를 사용하며 Langfuse는 비활성입니다. 두 모델 튜토리얼은 서버 환경의 의존성 버전이 달라 별도 requirements 파일을 유지합니다. 파서 환경에 합쳐 설치하지 말고 각각의 안내를 따르세요. [라우터](optional-capabilities.md#선택적-로컬-라우터), [설정 편집기](optional-capabilities.md#로컬-설정-편집기), [텔레메트리](optional-capabilities.md#선택적-langfuse-사용량-내보내기)를 참고하세요.

보안 조치에 필요한 버전은 각 환경의 requirements 파일에 직접 포함되어 별도 제약 파일을 배포할 필요가 없습니다. 기존 파서 환경은 `python -m pip install --upgrade -r requirements.txt` 실행 후 `python -m pip check`로 확인하세요.

## 오프라인 컴파일 스모크 검사

제공자를 시작하거나 PDF를 처리하지 않고 로컬 프로필의 네이티브 스키마, 레지스트리, DAG를 검사합니다. 이 검사는 `${NAME}` 참조를 설정값 그대로 둡니다. 실제 실행은 검증 전에 환경변수 값을 대입합니다.

```bash
python - <<'PY'
from pathlib import Path
import yaml
from tools.config_editor import validate_config

config = yaml.safe_load(Path("configs/local_quickstart.yaml").read_text(encoding="utf-8"))
print(validate_config(config))
PY
```

실제 실행에는 `.env.example`을 `.env`로 복사해 선택한 프로필의 변수만 채우고 커밋하지 마세요. 셸 환경값이 `.env`보다 우선합니다. 로컬 프로필에는 루프백 Dolphin/Paddle URL, OpenAI 텍스트·light/medium 비전 모델 ID 및 API 키가 필요합니다. [제공자 안내](providers.md)를 참고하세요. 제공자 호출은 요금을 발생시키고 문서 내용을 엔드포인트로 전송할 수 있습니다. 기존 로컬 실행은 로컬 Dolphin/Paddle과 VLM API를 사용했습니다. 검증 범위는 [개발 안내](development.md), 샘플 권리는 [자산 안내](model-and-data-assets.md)를 확인하세요.

CLI는 선택적인 설정 경로 하나를 위치 인자로 받습니다. 인자가 없을 때 기본값은 주력 `configs/default.yaml`입니다. router·Dolphin v2·Paddle Triton·로컬 LLM API의 OpenAI 호환 비전 호출이 필요합니다. 입문용 로컬 Dolphin/Paddle·OpenAI 실행은 `configs/local_quickstart.yaml`을 명시하세요. 자체 운영 서버는 `configs/managed_endpoints.yaml`, 비공개 서비스는 `configs/group_internal.yaml`을 명시하세요. YAML을 바꾸기 전에 [설정 안내](configuration.md)를 읽으세요.

설치를 마치면 [빠른 시작](quickstart.md)에 따라 필요한 서비스를 시작하고 PDF를
파싱하세요. [권장 모델 조합과 Dolphin v2 사양](README.md#권장-설정)은 입문용
로컬 FastAPI 구성과 구분해 참고하세요.

default·managed_endpoints·group_internal은 Global Context에 `skip_levels: [1]`을
지정하여 Stage 1 L1의 추가 후처리 요청 없이 앞 단계 내용을 유지합니다. 다른
페이지에는 설정한 VLM 엔드포인트가 필요합니다.
[정책과 복원 설정](configuration.md#단순-페이지의-global-context-호출-생략)을 참고하세요.

## 검증과 샘플 선택

기록된 전체 로컬 실행은 macOS arm64/Python 3.12를 다루며 모든 플랫폼 지원을
증명하지는 않습니다. 새 후보는 [개발 검사](development.md)와
[릴리스 점검표](release-checklist.md)에 따라 확인하세요.

비공개 개발 샘플은 clone에 없을 수 있습니다. 실제 실행 전에 `input_dir`를 사용
권한이 있는 PDF로 지정하고 새 `output_dir`를 선택하세요. 동봉 샘플·모델 조건은
[자산 안내](model-and-data-assets.md)에 있습니다. 상업적 레이아웃 분석에는
PP-DocLayoutV3를 권장하지만 제공 Dolphin 프로필에는 해당 모델의 조건이 적용되며
PP-DocLayoutV3 어댑터는 제공되어 있지 않습니다.
