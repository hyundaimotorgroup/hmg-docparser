# HTTP 입력 검증과 자원 제한

> 원문: [http-input-limits.md](../http-input-limits.md).

이 설정은 구성 편집기와 로컬 Router/Dolphin/Paddle HTTP 서버에 적용됩니다.
제공 진입점은 루프백으로 바인딩합니다. 외부 서비스 배포에는 별도로 검토한 인증·
주소/출처·프록시 정책이 필요합니다. [보안 정책](SECURITY.md)을 함께 확인하세요.

## 기본값

일반 문서 처리를 수용하도록 넉넉하게 설정했습니다. 기존 Router 클라이언트의
배치 기본값은 16장, 동시 요청은 4개입니다. Dolphin/Paddle의 이미지 바이트 제한은 64MiB입니다. MiB는 1,048,576바이트입니다.

| 제한 | Router (`ROUTER_`) | Dolphin (`DOLPHIN_15_`) | Paddle (`PADDLE_OCR_`) |
| --- | --- | --- | --- |
| `MAX_REQUEST_BYTES` | 536870912 (512MiB) | 134217728 (128MiB) | 134217728 (128MiB) |
| `MAX_IMAGE_BYTES` | 67108864 (64MiB), 파일당 | 67108864 (64MiB), base64 디코딩 후 | 67108864 (64MiB), base64 디코딩 후 |
| `MAX_IMAGE_PIXELS` | 128000000, 이미지당 | 128000000 | 128000000 |
| `MAX_BATCH_PIXELS` | 256000000, 요청 전체 | 해당 없음 | 해당 없음 |
| `MAX_IMAGES` | 128, 요청당 | 이미지 1개 API | 이미지 1개 API |
| `MAX_PROMPT_CHARS` | 해당 없음 | 65536, 문자 수 | 해당 없음 |
| `MAX_CONCURRENT_REQUESTS` | 8 | 8 | 8 |
| `MAX_QUEUED_REQUESTS` | 64 | 64 | 64 |
| `READ_TIMEOUT_SECONDS` | 900 | 900 | 900 |

환경변수 이름은 접두사와 제한 이름을 붙입니다. 예: `ROUTER_MAX_IMAGES`.
전체 요청 크기는 JSON/base64 또는 multipart 포장까지 포함합니다. 픽셀 제한은
이미지를 RGB 메모리로 펼치기 전에 검사합니다. Pillow의 기존 대형 이미지 보호도
유지하므로 Pillow가 먼저 거절하는 이미지가 있을 수 있습니다.

모델 서버의 동시·대기 제한은 **서버 프로세스별**입니다. 대기 중인 요청은
애플리케이션에서 본문을 모으거나 이미지를 디코딩하지 않습니다. 운영체제·ASGI 서버·
프록시 자체의 수신 버퍼는 별도입니다. 처리 중인 요청에는 수신, 디코딩, 기존 모델
lock 대기와 추론이 포함됩니다. 본문 수신 시간 제한은 처리 슬롯을 받은 뒤 시작하며,
추론 시간을 제한하지 않습니다. 여러 worker를 쓰면 전체 동시 요청 상한도 늘어납니다.

| 편집기 환경변수 | 기본값 |
| --- | --- |
| `CONFIG_EDITOR_MAX_REQUEST_BYTES` | 2000000, 기존 요청 크기 한도 유지 |
| `CONFIG_EDITOR_MAX_YAML_DEPTH` | 128 |
| `CONFIG_EDITOR_MAX_YAML_NODES` | 100000 |
| `CONFIG_EDITOR_MAX_YAML_ALIASES` | 10000 |
| `CONFIG_EDITOR_MAX_EXPANDED_NODES` | 1000000 |
| `CONFIG_EDITOR_MAX_EXPANDED_BYTES` | 67108864, JSON 별칭 확장 크기의 보수적 추정치 |
| `CONFIG_EDITOR_MAX_CONCURRENT_REQUESTS` | 8, 연결 처리 슬롯 |
| `CONFIG_EDITOR_MAX_QUEUED_REQUESTS` | 64, 대기 연결 |
| `CONFIG_EDITOR_READ_TIMEOUT_SECONDS` | 120, 소켓 읽기 대기 시간 |

편집기는 YAML 깊이와 별칭 확장을 확인한 뒤 객체를 구성하고 JSON으로 변환합니다.
순환 별칭과 JSON으로 표현할 수 없는 YAML 값은 명시적으로 거절합니다.
실행 코드가 포함된 YAML 태그는 계속 SafeLoader로 거절합니다.

## 한도 조절

환경변수는 서버 시작 전에 설정하고 서버를 다시 시작합니다. 모든 새 제한은
음수가 아닌 정수이며 `0`은 해당 애플리케이션 제한을 해제합니다.
`MAX_CONCURRENT_REQUESTS=0`은 동시·대기 제한을 함께 해제합니다.
`MAX_QUEUED_REQUESTS=0`은 대기 없이 처리 슬롯 초과 요청을 거절합니다.
이미지 1개라는 API 형식, 기존 프레임워크 한도와 Pillow 보호는 환경변수 `0`으로 해제되지 않습니다.

```bash
# Router에서 한 요청당 최대 256장을 허용하는 예
ROUTER_MAX_IMAGES=256 python tools/serve_router.py

# Dolphin에서 이미지 크기 제한을 128MiB로 늘리는 예
# base64가 커지므로 전체 요청 한도도 함께 늘립니다.
DOLPHIN_15_MAX_IMAGE_BYTES=134217728 \
DOLPHIN_15_MAX_REQUEST_BYTES=268435456 \
python tutorial/dolphin_15_fastapi/server.py
```

잘못된 입력은 편집기/Router/Dolphin에서 400, Paddle에서 422로 응답합니다.
본문·이미지·픽셀·배치·prompt 상한 초과는 413, 대기열 초과는
`Retry-After: 1` 헤더를 포함한 503, 본문 수신 시간 초과는 408입니다.
편집기의 YAML 구조·별칭 확장 상한 초과는 400입니다.

이 한도는 요청 수와 입력 크기를 제한합니다. GPU/CPU 추론 비용이나 서버 전체
메모리를 일정 값 이하로 보장하는 기능은 아니므로 운영 환경의 메모리와 프록시
한도에 맞게 조절하세요. 매우 큰 정상 입력에는 한도 조정이 필요할 수 있습니다.

## 회귀 테스트

모델을 로드하지 않고 잘못된 입력, 상한, 대기열과 정상 요청 회복을 검증합니다.

```bash
python -m pytest tests/test_http_input_security.py -q
```

필요 패키지: pytest, FastAPI, httpx, Pillow, PyYAML, torch, torchvision, truststore 및
저장소의 구성 편집기 의존성. 테스트는 기존 모델 startup을 생략합니다.
