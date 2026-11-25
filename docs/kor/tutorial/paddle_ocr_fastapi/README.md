# 로컬 PaddleOCR FastAPI 튜토리얼

> 원문: [tutorial/paddle_ocr_fastapi/README.md](../../../../tutorial/paddle_ocr_fastapi/README.md). 한국어 번역본입니다. 아래 명령은 저장소 루트에서 실행합니다.

이 독립형 루프백 OCR 서비스는 파서 `core/` 어댑터를 수정하거나 대체하지 않습니다. PaddleOCR의 공개 PP-OCRv5 모바일 모델 두 개를 사용합니다.

- `PP-OCRv5_mobile_det`
- `korean_PP-OCRv5_mobile_rec`(로컬에는 `korean_PP-OCRv5_mobile_rec_infer`로 다운로드)

첫 시작 시 [`PaddlePaddle/korean_PP-OCRv5_mobile_rec`](https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec)에서 한국어 인식 모델을, PaddleOCR의 [`ppocrv5_korean_dict.txt`](https://github.com/PaddlePaddle/PaddleOCR/blob/main/ppocr/utils/dict/ppocrv5_korean_dict.txt)에서 디코더 사전을 다운로드합니다. Git에서 무시되는 `tutorial/paddle_ocr_fastapi/.cache/`에 캐시합니다. 서버는 로컬 추론 설정에 이 사전을 연결합니다. 중국어 중심인 일반 `PP-OCRv5_mobile_rec` 사전을 사용하면 한국어를 안정적으로 인식할 수 없습니다.

## 설치(CPU)

Paddle 런타임이 파서 환경에 영향을 주지 않도록 별도 환경을 사용합니다.

```bash
conda create -n paddle-ocr-cpu python=3.11 -y
conda activate paddle-ocr-cpu
python -m pip install --upgrade pip
python -m pip install paddlepaddle==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install -r tutorial/paddle_ocr_fastapi/requirements.txt
```

의존성 파일은 PaddleOCR과 PaddleX를 모두 3.1.0으로 고정합니다. 이 PaddleOCR 버전에 더 새로운 PaddleX를 설치하지 마세요. PaddleX 3.7의 predictor 옵션 API는 호환되지 않습니다.

운영 환경에 쓰기 전에 대상 문서에서 한국어 PP-OCRv5의 품질을 검사하세요. 원본 이미지에 공백이 있어도 인식 결과에서 한국어 단어 사이 공백이 빠질 수 있습니다.

## 새 환경 스모크 검사

저장소 루트에서 다음 스크립트를 실행합니다. `paddle-ocr-cpu-smoke`라는 새 Conda 환경을 만들고 고정된 CPU 의존성을 설치한 후 루프백 서버를 시작합니다. `paddle_test.png`를 보내 텍스트 줄 반환을 검증하고 서버를 중지합니다. 첫 실행은 모델을 다운로드하므로 몇 분 걸릴 수 있습니다.

```bash
bash tutorial/paddle_ocr_fastapi/run_cpu_smoke.sh
```

같은 이름의 환경이 이미 있으면 스크립트가 제거하고 다시 만들어 새 환경 검사로 유지합니다. 다른 이름은 `PADDLE_OCR_ENV_NAME`으로 지정하세요. 성공한 JSON 응답은 `tutorial/paddle_ocr_fastapi/paddle_test.response.json`, 전체 서버 로그는 `tutorial/paddle_ocr_fastapi/paddle_test.server.log`에 남으며 둘 다 Git에서 무시됩니다.

성공 시 초기화된 PaddleX 파이프라인의 `PADDLE_OCR_MODEL_PROVENANCE`도 출력합니다. `requested_detection_model`이 `PP-OCRv5_mobile_det`, `requested_recognition_model`이 `korean_PP-OCRv5_mobile_rec`인지 확인하세요. PaddleX가 제공하면 로컬 캐시 경로도 `reported_models`에 표시됩니다. 각 실행은 고유한 `instance_id`를 사용하고 이미 HTTP 응답을 내는 포트를 거부해 오래된 서버를 새 v5 프로세스로 오인하지 않습니다. 필요하면 사용하지 않는 포트를 선택하세요.

```bash
PADDLE_OCR_PORT=18101 bash tutorial/paddle_ocr_fastapi/run_cpu_smoke.sh
```

모델 초기화 중에는 다운로드·네트워크 문제를 볼 수 있도록 30초마다 최근 서버 로그를 출력합니다.

스모크 스크립트는 PaddleX가 import 시각화 폰트를 다운로드하지 않도록 합니다. macOS에서는 `/System/Library/Fonts/AppleSDGothicNeo.ttc`를 자동으로 사용하며 OCR 모델 출력에는 영향이 없습니다. 다른 플랫폼에서는 설치된 TTF/TTC 파일 경로를 `PADDLE_PDX_LOCAL_FONT_FILE_PATH`로 지정하세요.

```bash
PADDLE_PDX_LOCAL_FONT_FILE_PATH=/path/to/installed-font.ttf \
  bash tutorial/paddle_ocr_fastapi/run_cpu_smoke.sh
```

PaddleX는 첫 시작 시 OCR 모델을 HTTPS로 다운로드합니다. 튜토리얼은 운영체제 신뢰 저장소를 사용하므로 macOS 키체인의 조직 CA를 신뢰합니다. CA를 PEM 파일로 제공한다면 TLS 검증을 끄지 말고 경로를 전달하세요.

```bash
REQUESTS_CA_BUNDLE=/path/to/organization-ca.pem \
  bash tutorial/paddle_ocr_fastapi/run_cpu_smoke.sh
```

## 시작

저장소 루트에서 실행합니다.

```bash
PADDLE_PDX_LOCAL_FONT_FILE_PATH=/System/Library/Fonts/AppleSDGothicNeo.ttc \
  python tutorial/paddle_ocr_fastapi/server.py
```

`PADDLE_OCR_HOST` 또는 `PADDLE_OCR_PORT`를 명시하지 않으면 서버는 `127.0.0.1:8100`에서 듣습니다. macOS가 아니면 위 폰트 경로를 설치된 TTF/TTC로 바꾸세요.

```bash
curl http://127.0.0.1:8100/healthz
```

## 요청 계약

`POST /v1/ocr`은 base64 인코딩 이미지 한 개(data URL 아님)를 받아 인식 텍스트 줄과 신뢰도 점수를 반환합니다.

```bash
IMAGE_B64="$(base64 < crop.png | tr -d '\n')"
curl -X POST http://127.0.0.1:8100/v1/ocr \
  -H 'Content-Type: application/json' \
  -d "{\"image_base64\":\"${IMAGE_B64}\"}"
```

예상 응답 형태:

```json
{"lines": [{"text": "Example", "score": 0.98}]}
```

서비스는 base64 디코딩 후 최대 20 MiB의 이미지를 받습니다. 요청 이미지를 디스크에 쓰지 않으며 기본 설정으로 루프백 외부에 노출하지 않습니다.

`PADDLE_OCR_HOST`는 `127.0.0.1`, `::1`, `localhost`만 허용합니다.

## 라이선스와 샘플 공유

[모델·데이터 자산](../../model-and-data-assets.md),
[제3자 고지](../../../../THIRD_PARTY_NOTICES), [HTTP 입력 한도](../../http-input-limits.md)를
확인하세요. 모델·사전을 재배포하기 전에 리비전·라이선스를 기록합니다. 동봉 스모크
이미지에는 별도 권리 기록이 적용되므로 결과 공유에는 허가된 샘플을 사용하세요.
다운로드·캐시·출력·전체 파서의 제공자 전송은
[데이터 처리](../../privacy-and-data-handling.md)를 참고하세요.
