# 로컬 Dolphin 1.5 레이아웃 서버

> 원문: [tutorial/dolphin_15_fastapi/README.md](../../../../tutorial/dolphin_15_fastapi/README.md). 한국어 번역본입니다. 아래 명령은 저장소 루트에서 실행합니다.

이 튜토리얼은 [`ByteDance/Dolphin-1.5`](https://huggingface.co/ByteDance/Dolphin-1.5)의 레이아웃 단계를 사용자 컴퓨터에서 실행하고 `configs/local_quickstart.yaml`용 루프백 API를 제공합니다. 모델 로딩과 생성 설정은 [Dolphin 1.5 원본 데모](https://github.com/bytedance/Dolphin/blob/b6c7978ffd/demo_page.py)를 따릅니다. 서버는 읽기 순서의 원시 레이아웃 문자열을 반환하며 파서는 896 좌표계의 박스를 PDF 페이지 좌표로 변환합니다.

## 하드웨어와 소프트웨어

초기 **Dolphin 서버만의** Linux/NVIDIA 설정에 GPU VRAM 8 GiB, 시스템 RAM 16 GiB, 디스크 여유 10 GiB 이상을 계획하세요. 이는 여유를 둔 계획값이며 **측정된 최솟값이 아닙니다**. 원본 모델은 약 0.3B 파라미터이며 공개 추론 데모는 CUDA half precision 또는 CPU float precision을 사용합니다. 로컬 LLM과 비전 모델에는 추가 메모리가 필요하므로 각 서버 용량을 별도로 정하세요. 문서화한 시작 플랫폼은 Python 3.11과 CUDA 12.1 호환 NVIDIA 드라이버입니다. 시작 전에 `nvidia-smi`와 설치된 PyTorch CUDA 런타임을 확인하세요. CPU 추론은 느릴 수 있습니다. 기록된 macOS arm64 CPU 서버로 local_quickstart 파서 실행 3회를 통과했으며 Linux/NVIDIA 지원 검증을 의미하지는 않습니다.

## 설치 및 시작

### 새 환경 CPU 스모크 검사(실제 모델)

저장소 루트에서 실행합니다.

```bash
bash tutorial/dolphin_15_fastapi/run_cpu_smoke.sh
```

스크립트는 `uv`로 별도의 새 Python 3.12 환경을 만들고 CPU PyTorch와 고정된 튜토리얼 의존성을 설치합니다. 최초 사용 시 Dolphin 1.5를 다운로드하고 승인된 샘플 PDF의 첫 페이지를 렌더링한 뒤 루프백 FastAPI 서버를 시작해 `POST /v1/layout`에 해당 페이지를 보냅니다. `uv`, `curl`, 최초 패키지/모델 다운로드를 위한 네트워크, 모델에 충분한 RAM과 디스크가 필요합니다. CPU 추론은 오래 걸릴 수 있습니다. 기본 포트가 사용 중이면 실행 전에 `DOLPHIN_15_PORT=18201`을 설정하세요.

증빙은 `tutorial/dolphin_15_fastapi/`에 남습니다.

- `layout_smoke_page.png`: 렌더링된 원본 페이지
- `layout_smoke.overlay.png`: 시각적 검토를 위해 정사각형 패딩 페이지에 표시한 박스
- `layout_smoke.response.json`: 원시 레이아웃 응답. HTTP 실패 시에도 보존됩니다.
- `layout_smoke.server.log`: 시작, 모델 출처, 추론 로그

스크립트는 응답에 896 좌표계의 유효한 Dolphin 1.5 박스가 하나 이상 있는지 확인합니다. 이는 모델/API 스모크 검사이며 전체 파서 퀵스타트가 아닙니다. 2026-10-20 macOS arm64 CPU 검사에서는 `dp_evalset_general_3p.pdf` 첫 페이지에서 파싱 가능한 박스 15개를 얻었습니다(SHA-256 `96e9abc68f717c7b2c3223fce2d757c5e7de6df9698face41d554957958f12b7`). 다운로드한 모델 리비전은 `0fe42a93fa2a8f7b537606710ea45ad8b2b0f349`, PyTorch는 2.2.2, Transformers는 4.47.0이었습니다. 이는 해당 기기의 CPU 스모크 결과이며 최소 RAM이나 Linux/NVIDIA 결과가 아닙니다.

전용 `.venv-smoke/`는 매번 교체되고 Git에서 무시됩니다. 모델 캐시는 재사용됩니다. `DOLPHIN_15_SMOKE_MAX_LENGTH`로 생성 상한을 바꿀 수 있으며 스모크 기본값은 1024입니다. `DOLPHIN_15_MODEL`은 이미 다운로드한 모델 디렉터리를 가리킬 수 있습니다. `uv`와 모델 다운로더는 운영체제 인증서 저장소를 사용하므로 TLS 검증을 끄지 않고 승인된 조직 CA를 신뢰할 수 있습니다.

### 수동 GPU 서버

저장소 루트에서 전용 환경에 설치합니다.

```bash
conda create -n dolphin-15 python=3.11 -y
conda activate dolphin-15
python -m pip install --upgrade pip
python -m pip install torch==2.1.0 torchvision==0.16.0 --index-url https://download.pytorch.org/whl/cu121
python -m pip install -r tutorial/dolphin_15_fastapi/requirements.txt
python tutorial/dolphin_15_fastapi/server.py
```

첫 시작 시 Hugging Face에서 모델을 일반 로컬 캐시로 다운로드합니다. 기존 모델 디렉터리를 사용하려면 시작 전 `DOLPHIN_15_MODEL=/absolute/path/to/model`을 설정하세요. 수동 Linux/NVIDIA 설치와 GPU 사용량은 미검증입니다. 별도 macOS CPU local_quickstart 파서 실행 3회는 통과했으며 [제공자 안내](../../providers.md#로컬-dolphin과-paddle-및-openai)를 참고하세요.

다른 터미널에서 확인합니다.

```bash
curl --fail http://127.0.0.1:8200/healthz
```

응답에는 `status`, 실행 `instance_id`, 장치·패키지 버전·확인 가능한 모델 리비전을 포함한 모델 출처가 있습니다. 기본 수신 주소는 `127.0.0.1:8200`입니다. `DOLPHIN_15_PORT`를 바꾸면 `.env`의 `LOCAL_DOLPHIN_URL`도 갱신하세요. 인증이 없는 이 튜토리얼 서버를 외부 네트워크에 노출하지 마세요.

`POST /v1/layout`은 `image_base64`(data URL 접두사 없이 표준 base64로 인코딩한 PNG/JPEG 바이트)와 선택적 `prompt`를 담은 JSON을 받습니다. 응답은 `{"layout_text": "..."}`입니다. 디코딩한 이미지 크기는 최대 20 MiB입니다. 파서는 렌더링한 PDF 페이지를 한 번에 하나씩 보내고 프롬프트 `Parse the reading order of this document.`를 사용합니다.

## 라이선스와 샘플 공유

[모델·데이터 자산](../../model-and-data-assets.md),
[제3자 고지](../../../../THIRD_PARTY_NOTICES), [HTTP 입력 한도](../../http-input-limits.md)를
확인하세요. 모델·사전을 재배포하기 전에 리비전·라이선스를 기록합니다. 동봉 스모크
이미지에는 별도 권리 기록이 적용되므로 결과 공유에는 허가된 샘플을 사용하세요.
다운로드·캐시·출력·전체 파서의 제공자 전송은
[데이터 처리](../../privacy-and-data-handling.md)를 참고하세요.
