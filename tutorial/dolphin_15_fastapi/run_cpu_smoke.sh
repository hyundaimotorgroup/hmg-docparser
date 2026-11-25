#!/usr/bin/env bash
# Fresh CPU environment, real Dolphin 1.5 inference, and saved evidence.
set -Eeuo pipefail
export UV_SYSTEM_CERTS=true

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tutorial_dir="$repo_root/tutorial/dolphin_15_fastapi"
fixture_pdf="$repo_root/inputs/smoke/dp_evalset_general_3p.pdf"
venv_dir="$tutorial_dir/.venv-smoke"
smoke_python="$venv_dir/bin/python"
host="127.0.0.1"
port="${DOLPHIN_15_PORT:-18200}"
instance_id="smoke-$$-${RANDOM}"
max_length="${DOLPHIN_15_SMOKE_MAX_LENGTH:-1024}"
fixture_png="$tutorial_dir/layout_smoke_page.png"
overlay_png="$tutorial_dir/layout_smoke.overlay.png"
response_file="$tutorial_dir/layout_smoke.response.json"
server_log_output="$tutorial_dir/layout_smoke.server.log"
server_log="$(mktemp -t dolphin-15-server.XXXXXX)"
request_file="$(mktemp -t dolphin-15-request.XXXXXX)"
http_response_file="$(mktemp -t dolphin-15-response.XXXXXX)"
server_pid=""

cleanup() {
    local exit_code=$?
    if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
        kill "$server_pid" 2>/dev/null || true
        for _ in 1 2 3 4 5; do
            if ! kill -0 "$server_pid" 2>/dev/null; then
                break
            fi
            sleep 1
        done
        if kill -0 "$server_pid" 2>/dev/null; then
            kill -9 "$server_pid" 2>/dev/null || true
        fi
        wait "$server_pid" 2>/dev/null || true
    fi
    if [[ -s "$server_log" ]]; then
        cp "$server_log" "$server_log_output"
    fi
    rm -f "$server_log" "$request_file" "$http_response_file"
    exit "$exit_code"
}
trap cleanup EXIT INT TERM

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || fail "invalid DOLPHIN_15_PORT: $port"
[[ "$max_length" =~ ^[1-9][0-9]*$ ]] || fail "invalid DOLPHIN_15_SMOKE_MAX_LENGTH: $max_length"
[[ -f "$fixture_pdf" ]] || fail "approved fixture is missing: $fixture_pdf"
command -v uv >/dev/null 2>&1 || fail "uv is required (https://docs.astral.sh/uv/)"
command -v curl >/dev/null 2>&1 || fail "curl is required"

if curl --silent --fail "http://$host:$port/healthz" >/dev/null 2>&1; then
    fail "port $port already has an HTTP server; choose another DOLPHIN_15_PORT"
fi
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >&2 || true
    fail "port $port is already listening; choose another DOLPHIN_15_PORT"
fi

rm -f "$response_file" "$server_log_output" "$overlay_png"
printf 'Creating fresh Python 3.12 CPU environment with uv...\n'
uv venv --clear --python 3.12 "$venv_dir"
if [[ "$(uname -s)" == "Linux" ]]; then
    uv pip install --python "$smoke_python" torch==2.2.2 torchvision==0.17.2 \
        --index-url https://download.pytorch.org/whl/cpu
else
    uv pip install --python "$smoke_python" torch==2.2.2 torchvision==0.17.2
fi
uv pip install --python "$smoke_python" -r "$tutorial_dir/requirements.txt"

printf 'Rendering page 1 of the approved PDF at 2048-pixel long edge...\n'
"$smoke_python" -c '
import pathlib, sys
from contextlib import closing
import pypdfium2 as pdfium
source, target = map(pathlib.Path, sys.argv[1:])
with closing(pdfium.PdfDocument(str(source))) as document:
    document.init_forms()
    with closing(document[0]) as page:
        scale = 2048 / max(page.get_size())
        with closing(page.render(scale=scale, rev_byteorder=True, prefer_bgrx=True)) as bitmap:
            image = bitmap.to_pil().convert("RGB")
with image:
    image.save(target, "PNG")
    print(f"Fixture image: {target} ({image.width}x{image.height})")
' "$fixture_pdf" "$fixture_png"

"$smoke_python" -c '
import base64, hashlib, json, pathlib, sys
image_path, request_path, pdf_path = map(pathlib.Path, sys.argv[1:])
request_path.write_text(json.dumps({
    "image_base64": base64.b64encode(image_path.read_bytes()).decode("ascii"),
    "prompt": "Parse the reading order of this document.",
}), encoding="utf-8")
print(f"Fixture PDF SHA-256: {hashlib.sha256(pdf_path.read_bytes()).hexdigest()}")
' "$fixture_png" "$request_file" "$fixture_pdf"
[[ -s "$request_file" ]] || fail "failed to create Dolphin request body"

health_matches_started_server() {
    local payload
    payload="$(curl --silent --fail "http://$host:$port/healthz")" || return 1
    [[ "$payload" == *"\"instance_id\":\"$instance_id\""* ]]
}

printf 'Starting Dolphin 1.5 CPU server at http://%s:%s...\n' "$host" "$port"
env PYTHONUNBUFFERED=1 DOLPHIN_15_DEVICE=cpu DOLPHIN_15_PORT="$port" \
    DOLPHIN_15_INSTANCE_ID="$instance_id" DOLPHIN_15_MAX_LENGTH="$max_length" \
    "$smoke_python" "$tutorial_dir/server.py" >"$server_log" 2>&1 &
server_pid=$!

for attempt in $(seq 1 1200); do
    if health_matches_started_server; then
        break
    fi
    if ! kill -0 "$server_pid" 2>/dev/null; then
        sed -n '1,240p' "$server_log" >&2 || true
        fail "Dolphin server exited before becoming ready"
    fi
    if (( attempt % 30 == 0 )); then
        printf 'Waiting for model download/initialization (%ss elapsed)...\n' "$attempt"
        tail -n 60 "$server_log" || true
    fi
    sleep 1
done
health_matches_started_server || fail "Dolphin server was not ready after 20 minutes"
printf 'Health: %s\n' "$(curl --silent --fail "http://$host:$port/healthz")"

printf 'Submitting rendered PDF page for layout inference...\n'
if ! http_status="$(curl --silent --show-error --max-time 1200 \
    -X POST "http://$host:$port/v1/layout" \
    -H 'Content-Type: application/json' --data-binary "@$request_file" \
    -o "$http_response_file" --write-out '%{http_code}')"; then
    [[ ! -s "$http_response_file" ]] || cp "$http_response_file" "$response_file"
    sed -n '1,240p' "$server_log" >&2 || true
    fail "Dolphin request failed at the transport layer"
fi
cp "$http_response_file" "$response_file"
if [[ "$http_status" != 2* ]]; then
    printf 'HTTP status: %s\n' "$http_status" >&2
    sed -n '1,80p' "$response_file" >&2 || true
    sed -n '1,240p' "$server_log" >&2 || true
    fail "Dolphin layout request returned an error"
fi

"$smoke_python" - "$response_file" "$fixture_png" "$overlay_png" <<'PY'
import json
import pathlib
import re
import sys
from PIL import Image, ImageDraw

path = pathlib.Path(sys.argv[1])
response = json.loads(path.read_text(encoding="utf-8"))
layout_text = response.get("layout_text")
if not isinstance(layout_text, str) or not layout_text.strip():
    raise SystemExit(f"Dolphin returned empty layout_text: {response!r}")
pattern = r"\[(\d*\.?\d+),(\d*\.?\d+),(\d*\.?\d+),(\d*\.?\d+)\]\[([^\]]+)\]"
items = re.findall(pattern, layout_text)
if not items:
    raise SystemExit(f"Dolphin returned no parseable layout boxes: {layout_text[:1000]!r}")
for item in items:
    x1, y1, x2, y2 = map(float, item[:4])
    if not (0 <= x1 < x2 <= 896 and 0 <= y1 < y2 <= 896):
        raise SystemExit(f"Dolphin returned an invalid 896-space box: {item!r}")
source_image = Image.open(sys.argv[2]).convert("RGB")
side = max(source_image.size)
offset = ((side - source_image.width) // 2, (side - source_image.height) // 2)
overlay = Image.new("RGB", (side, side), (0, 0, 0))
overlay.paste(source_image, offset)
draw = ImageDraw.Draw(overlay)
for index, item in enumerate(items):
    x1, y1, x2, y2 = (round(float(value) / 896 * side) for value in item[:4])
    draw.rectangle((x1, y1, x2, y2), outline="red", width=4)
    draw.text((x1, max(y1 - 14, 0)), f"{index}: {item[4]}", fill="red")
overlay.save(sys.argv[3])
print(f"SUCCESS: received {len(items)} parseable Dolphin 1.5 layout box(es).")
print("First labels:", ", ".join(item[4] for item in items[:10]))
PY

grep -F 'DOLPHIN_MODEL_PROVENANCE=' "$server_log" || fail "model provenance was not logged"
printf 'Saved fixture image: %s\n' "$fixture_png"
printf 'Saved layout overlay: %s\n' "$overlay_png"
printf 'Saved response: %s\n' "$response_file"
printf 'Saved server log: %s\n' "$server_log_output"
