#!/usr/bin/env bash
# Create a fresh CPU-only Conda environment and prove the local OCR API works.
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tutorial_dir="$repo_root/tutorial/paddle_ocr_fastapi"
environment_name="${PADDLE_OCR_ENV_NAME:-paddle-ocr-cpu-smoke}"
port="${PADDLE_OCR_PORT:-18100}"
host="127.0.0.1"
instance_id="smoke-$$-${RANDOM}"
local_font_path="${PADDLE_PDX_LOCAL_FONT_FILE_PATH:-}"
server_pid=""
server_log="$(mktemp -t paddle-ocr-server.XXXXXX)"
server_pid_file="$(mktemp -t paddle-ocr-pid.XXXXXX)"
request_file="$(mktemp -t paddle-ocr-request.XXXXXX)"
http_response_file="$(mktemp -t paddle-ocr-response.XXXXXX)"
response_file="$tutorial_dir/paddle_test.response.json"
server_log_output="$tutorial_dir/paddle_test.server.log"

cleanup() {
    local exit_code=$?
    local server_worker_pid=""
    if [[ -s "$server_pid_file" ]]; then
        read -r server_worker_pid < "$server_pid_file" || true
    fi
    if [[ "$server_worker_pid" =~ ^[1-9][0-9]*$ ]] && kill -0 "$server_worker_pid" 2>/dev/null; then
        kill "$server_worker_pid" 2>/dev/null || true
    fi
    if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    if [[ -s "$server_log" ]]; then
        cp "$server_log" "$server_log_output"
    fi
    rm -f "$server_log" "$server_pid_file" "$request_file" "$http_response_file"
    exit "$exit_code"
}
trap cleanup EXIT INT TERM

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[[ "$environment_name" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || fail "invalid PADDLE_OCR_ENV_NAME: $environment_name"
[[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || fail "invalid PADDLE_OCR_PORT: $port"
command -v conda >/dev/null 2>&1 || fail "conda is not on PATH; open a Conda-enabled shell and run this script again"
command -v curl >/dev/null 2>&1 || fail "curl is required"

if curl --silent --show-error --fail "http://$host:$port/healthz" >/dev/null 2>&1; then
    fail "port $port already has an HTTP server; stop it or rerun with PADDLE_OCR_PORT=$((port + 1))"
fi
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >&2 || true
    fail "port $port is already listening; stop that process or choose another PADDLE_OCR_PORT"
fi

health_matches_started_server() {
    local health_payload
    health_payload="$(curl --silent --fail "http://$host:$port/healthz")" || return 1
    [[ "$health_payload" == *"\"instance_id\":\"$instance_id\""* ]]
}

# PaddleX imports its visualization utilities with PaddleOCR and otherwise
# downloads PingFang and simfang before the server can start. OCR inference does
# not need those upstream font files. macOS includes a suitable Korean font;
# other platforms must provide an installed TTF/TTC explicitly.
if [[ -z "$local_font_path" && -f /System/Library/Fonts/AppleSDGothicNeo.ttc ]]; then
    local_font_path="/System/Library/Fonts/AppleSDGothicNeo.ttc"
fi
[[ -n "$local_font_path" ]] || fail "PaddleX font download is disabled; set PADDLE_PDX_LOCAL_FONT_FILE_PATH to an installed TTF or TTC file"
[[ -f "$local_font_path" ]] || fail "PADDLE_PDX_LOCAL_FONT_FILE_PATH is not a file: $local_font_path"
printf 'Using local PaddleX font: %s\n' "$local_font_path"

if conda env list | awk -v target="$environment_name" '$1 == target { found = 1 } END { exit !found }'; then
    printf 'Removing existing Conda environment: %s\n' "$environment_name"
    conda env remove -n "$environment_name" -y
fi

printf 'Creating fresh Conda environment: %s\n' "$environment_name"
conda create -n "$environment_name" python=3.11 -y

printf 'Installing PaddlePaddle CPU runtime...\n'
conda run -n "$environment_name" python -m pip install --upgrade pip
conda run -n "$environment_name" python -m pip install paddlepaddle==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
conda run -n "$environment_name" python -m pip install -r "$tutorial_dir/requirements.txt"

printf 'Starting local PaddleOCR server at http://%s:%s (first start downloads models)...\n' "$host" "$port"
conda run --no-capture-output -n "$environment_name" env \
    PYTHONUNBUFFERED=1 \
    PADDLE_OCR_DEVICE=cpu \
    PADDLE_OCR_HOST="$host" \
    PADDLE_OCR_PORT="$port" \
    PADDLE_OCR_INSTANCE_ID="$instance_id" \
    PADDLE_OCR_PID_FILE="$server_pid_file" \
    PADDLE_PDX_LOCAL_FONT_FILE_PATH="$local_font_path" \
    python "$tutorial_dir/server.py" >"$server_log" 2>&1 &
server_pid=$!

for attempt in $(seq 1 600); do
    if health_matches_started_server; then
        break
    fi
    if ! kill -0 "$server_pid" 2>/dev/null; then
        sed -n '1,240p' "$server_log" >&2 || true
        fail "server exited before becoming ready"
    fi
    if (( attempt % 30 == 0 )); then
        printf 'Still waiting for model initialization (%ss elapsed)...\n' "$attempt"
        printf '%s\n' '--- recent PaddleOCR server log ---'
        tail -n 80 "$server_log" || true
        printf '%s\n' '--- end server log ---'
    fi
    sleep 1
done

if ! health_matches_started_server; then
    sed -n '1,240p' "$server_log" >&2 || true
    fail "server was not ready after 10 minutes"
fi

conda run -n "$environment_name" python -c '
import base64
import json
import pathlib
import sys

image_path = pathlib.Path(sys.argv[1])
request_path = pathlib.Path(sys.argv[2])
request_path.write_text(
    json.dumps({"image_base64": base64.b64encode(image_path.read_bytes()).decode("ascii")}),
    encoding="utf-8",
)
' "$tutorial_dir/paddle_test.png" "$request_file"

[[ -s "$request_file" ]] || fail "failed to create the OCR request body"

printf 'Submitting paddle_test.png for OCR...\n'
if ! http_status="$(curl --silent --show-error \
    -X POST "http://$host:$port/v1/ocr" \
    -H 'Content-Type: application/json' \
    --data-binary "@$request_file" \
    -o "$http_response_file" \
    --write-out '%{http_code}')"; then
    printf '%s\n' '--- OCR request transport error ---' >&2
    if [[ -s "$http_response_file" ]]; then
        sed -n '1,80p' "$http_response_file" >&2
    fi
    printf '\n%s\n' '--- end OCR request transport error ---' >&2
    sed -n '1,240p' "$server_log" >&2 || true
    fail "OCR request could not be completed"
fi

if [[ "$http_status" != 2* ]]; then
    printf '%s\n' '--- OCR error response ---' >&2
    printf 'HTTP status: %s\n' "$http_status" >&2
    if [[ -s "$http_response_file" ]]; then
        sed -n '1,80p' "$http_response_file" >&2
    else
        printf '%s\n' '(server returned no response body)' >&2
    fi
    printf '\n%s\n' '--- end OCR error response ---' >&2
    sed -n '1,240p' "$server_log" >&2 || true
    fail "OCR request failed"
fi

mv "$http_response_file" "$response_file"

printf '%s\n' '--- PaddleOCR model provenance ---'
if ! health_matches_started_server; then
    sed -n '1,240p' "$server_log" >&2 || true
    fail "could not retrieve model provenance"
fi
printf '\n%s\n' '--- end PaddleOCR model provenance ---'

if ! grep -F 'PADDLE_OCR_MODEL_PROVENANCE=' "$server_log"; then
    sed -n '1,240p' "$server_log" >&2 || true
    fail "server did not report PaddleOCR model provenance"
fi

conda run -n "$environment_name" python - "$response_file" <<'PY'
import json
import pathlib
import sys

response_path = pathlib.Path(sys.argv[1])
payload = json.loads(response_path.read_text(encoding="utf-8"))
lines = payload.get("lines")
if not isinstance(lines, list) or not lines:
    raise SystemExit(f"OCR response did not contain recognized lines: {payload!r}")
if not all(isinstance(line, dict) and isinstance(line.get("text"), str) and line["text"] for line in lines):
    raise SystemExit(f"OCR response has an invalid line shape: {payload!r}")

print(f"SUCCESS: received {len(lines)} recognized line(s).")
for line in lines:
    print(f"- {line['text']} (score={line.get('score')})")
PY

printf 'Saved response: %s\n' "$response_file"
printf 'Saved server log: %s\n' "$server_log_output"
