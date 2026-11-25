#!/usr/bin/env bash
# Bootstrap Conda, start isolated CPU providers, and run the real parser CLI.
# Usage: bash scripts/verify_local_quickstart_clean_conda.sh [CONFIG] [INPUT_PDF]
# Keep this bootstrap POSIX-compatible so `sh script.sh` works too.
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi
# macOS /bin/sh is Bash 3.2 in POSIX mode, which rejects process substitution.
set +o posix
set -Eeuo pipefail

usage() {
    cat <<'HELP'
Usage: bash scripts/verify_local_quickstart_clean_conda.sh [CONFIG] [INPUT_PDF]

Default config: configs/local_quickstart.yaml
Default PDF: input_dir in the selected YAML (must be an existing PDF file).
Set LLM/VLM credentials and models in .env before running.

Conda is reused if installed; otherwise checksum-verified Miniforge is installed
under tmp/miniforge3 (override with QUICKSTART_CONDA_ROOT).
Each run creates fresh parser (3.12), Dolphin (3.12), and Paddle (3.11) environments.
Enabled router nodes use the parser environment on CPU.
Local FastAPI nodes use CPU servers on 127.0.0.1, overriding their YAML/.env URLs.
Other configs retain their provider settings and require those providers to be ready.

Optional environment variables:
  CONDA_EXE                      Existing conda executable
  QUICKSTART_CONDA_ROOT           Miniforge install prefix
  QUICKSTART_MINIFORGE_VERSION    Installer release (default 26.9.4-1)
  DOLPHIN_15_PORT                 Dolphin port (default 8200)
  PADDLE_OCR_PORT                 Paddle port (default 8100)
  ROUTER_PORT                     Router CPU port (default 8001)
  QUICKSTART_READY_TIMEOUT        Server startup timeout in seconds (default 1200)
  PADDLE_PDX_LOCAL_FONT_FILE_PATH  Optional font override (also read from .env).
                                Otherwise detect installed fonts, or download
                                verified Noto Sans KR into tmp/paddle_fonts.
  DOLPHIN_15_MODEL                Existing model directory or Hugging Face model ID
  PADDLE_OCR_MODEL_ROOT           Local Paddle models + dictionary, prepared by
                                tools/quickstart/download_paddle_models.py (optional)

Servers started by this script stop on success, failure, or interruption.
Environments, private logs, generated quickstart.yaml, and Markdown remain under
tmp/clean_conda_<config-name>/<run-id>/. No existing environment is removed.
HELP
}

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then usage; exit 0; fi
[[ $# -le 2 ]] || { usage >&2; exit 2; }

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
config_path="${1:-configs/local_quickstart.yaml}"
input_path="${2:-}"
[[ -f "$config_path" ]] || fail "config file not found: $config_path"
[[ -z "$input_path" || -f "$input_path" ]] || fail "input PDF not found: $input_path"
command -v curl >/dev/null 2>&1 || fail 'curl is required for downloads and health checks'

dolphin_port="${DOLPHIN_15_PORT:-8200}"
paddle_port="${PADDLE_OCR_PORT:-8100}"
router_port="${ROUTER_PORT:-8001}"
ready_timeout="${QUICKSTART_READY_TIMEOUT:-1200}"
for port in "$dolphin_port" "$paddle_port" "$router_port"; do
    [[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || fail "invalid port: $port"
done
[[ "$dolphin_port" != "$paddle_port" && "$router_port" != "$dolphin_port" && "$router_port" != "$paddle_port" ]] || fail 'Router, Dolphin and Paddle must use different ports'
[[ "$ready_timeout" =~ ^[1-9][0-9]{0,5}$ ]] || fail 'QUICKSTART_READY_TIMEOUT must be a positive integer (at most six digits)'

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
config_label="$(basename "$config_path")"
config_label="${config_label%.*}"
evidence_dir="$repo_root/tmp/clean_conda_${config_label}/$run_id"
env_prefix="$evidence_dir/conda-env"
dolphin_prefix="$evidence_dir/dolphin-env"
paddle_prefix="$evidence_dir/paddle-env"
parser_python="$env_prefix/bin/python"
output_dir="$evidence_dir/output"
run_config="$evidence_dir/quickstart.yaml"
process_pids=()
# Logs may contain provider diagnostics and document content; keep them private.
umask 077
mkdir -p "$evidence_dir"
exec > >(tee -a "$evidence_dir/verification.log") 2>&1
printf 'Evidence: %s\n' "$evidence_dir"

cleanup() {
    local exit_code=$? pid attempt alive
    trap - EXIT INT TERM
    # Bash 3.2 (macOS) treats an empty array as unset with nounset enabled.
    for pid in ${process_pids[@]+"${process_pids[@]}"}; do kill "$pid" 2>/dev/null || true; done
    for attempt in 1 2 3 4 5; do
        alive=0
        for pid in ${process_pids[@]+"${process_pids[@]}"}; do
            if kill -0 "$pid" 2>/dev/null; then alive=1; fi
        done
        [[ "$alive" == 1 ]] || break
        sleep 1
    done
    for pid in ${process_pids[@]+"${process_pids[@]}"}; do
        if kill -0 "$pid" 2>/dev/null; then kill -9 "$pid" 2>/dev/null || true; fi
        wait "$pid" 2>/dev/null || true
    done
    if [[ -x "$parser_python" ]]; then "$parser_python" - "$evidence_dir" "$exit_code" ${process_pids[@]+"${process_pids[@]}"} <<'PY_CLEAN' || true
import json, sys
from pathlib import Path
Path(sys.argv[1], 'cleanup.json').write_text(json.dumps({
    'exit_code': int(sys.argv[2]), 'owned_pids': [int(p) for p in sys.argv[3:]],
    'cleanup_completed': True,
}, indent=2) + '\n')
PY_CLEAN
    fi
    printf 'Exit status: %s; evidence retained at %s\n' "$exit_code" "$evidence_dir"
    exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

conda_bin="${CONDA_EXE:-}"
if [[ -n "$conda_bin" ]]; then
    [[ -x "$conda_bin" ]] || fail 'CONDA_EXE must point to an executable'
elif command -v conda >/dev/null 2>&1; then
    conda_bin="$(command -v conda)"
else
    conda_root="${QUICKSTART_CONDA_ROOT:-$repo_root/tmp/miniforge3}"
    for candidate in "$conda_root/bin/conda" /opt/miniconda3/bin/conda \
        "$HOME/miniforge3/bin/conda" "$HOME/miniconda3/bin/conda" \
        /opt/anaconda3/bin/conda "$HOME/anaconda3/bin/conda"; do
        if [[ -x "$candidate" ]]; then conda_bin="$candidate"; break; fi
    done
    if [[ -z "$conda_bin" ]]; then
        platform="$(uname -s)"
        architecture="$(uname -m)"
        case "$platform/$architecture" in
            Darwin/arm64|Darwin/x86_64|Linux/x86_64|Linux/aarch64) ;;
            *) fail "unsupported Conda bootstrap platform: $platform/$architecture" ;;
        esac
        if [[ "$platform" == Darwin ]]; then platform=MacOSX; fi
        miniforge_version="${QUICKSTART_MINIFORGE_VERSION:-26.9.4-1}"
        [[ "$miniforge_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+-[0-9]+$ ]] || fail 'invalid QUICKSTART_MINIFORGE_VERSION'
        # Only versioned release assets have matching .sha256 sidecars.
        installer_name="Miniforge3-${miniforge_version}-${platform}-${architecture}.sh"
        installer_url="https://github.com/conda-forge/miniforge/releases/download/$miniforge_version/$installer_name"
        printf 'Installing Conda (Miniforge) at %s...\n' "$conda_root"
        curl --fail --location --show-error --retry 3 "$installer_url" -o "$evidence_dir/$installer_name"
        curl --fail --location --show-error --retry 3 "$installer_url.sha256" -o "$evidence_dir/$installer_name.sha256"
        if command -v shasum >/dev/null 2>&1; then
            (cd "$evidence_dir" && shasum -a 256 -c "$installer_name.sha256")
        elif command -v sha256sum >/dev/null 2>&1; then
            (cd "$evidence_dir" && sha256sum -c "$installer_name.sha256")
        else
            fail 'shasum or sha256sum is required to verify the Conda installer'
        fi
        bash "$evidence_dir/$installer_name" -b -p "$conda_root"
        conda_bin="$conda_root/bin/conda"
    fi
fi
"$conda_bin" --version

create_environment() {
    local prefix="$1" version="$2"
    # Explicit conda-forge avoids relying on the user's configured channels.
    "$conda_bin" create --override-channels --channel conda-forge --prefix "$prefix" "python=$version" pip -y
    "$prefix/bin/python" -m pip install --upgrade pip
}

record_environment() {
    local prefix="$1" label="$2"
    "$prefix/bin/python" -m pip check
    "$prefix/bin/python" -m pip freeze > "$evidence_dir/$label-pip-freeze.txt"
    "$prefix/bin/python" --version > "$evidence_dir/$label-python-version.txt"
    "$conda_bin" list --prefix "$prefix" --explicit > "$evidence_dir/$label-conda-explicit.txt"
}

printf 'Creating fresh parser environment (Python 3.12)...\n'
create_environment "$env_prefix" 3.12
"$parser_python" -m pip install -r "$repo_root/requirements.txt"
record_environment "$env_prefix" parser
"$parser_python" main.py --help > "$evidence_dir/cli-help.txt"

# Never source .env. The parser resolves it using python-dotenv; override only
# the two endpoints owned by this run. Save the unresolved YAML, never API keys.
export LOCAL_DOLPHIN_URL="http://127.0.0.1:$dolphin_port"
export LOCAL_PADDLE_URL="http://127.0.0.1:$paddle_port"
export ROUTER_SERVER_URL="http://127.0.0.1:$router_port"
"$parser_python" - "$config_path" "$input_path" "$evidence_dir" "$output_dir" <<'PY'
from pathlib import Path
import hashlib
import os
import sys
import yaml

from core.engine.config.runtime_config import load_yaml_with_env
from core.engine.config.translator import load_native_runtime_config
from core.engine.config.compiler import compile_pipeline_graph
from core.engine.registry import build_node_registry_for_graph

source = Path(sys.argv[1]).resolve()
evidence, output = map(Path, sys.argv[3:])
template = yaml.safe_load(source.read_text(encoding='utf-8'))
services = set()
for node in template['pipeline']['nodes']:
    settings = node.get('node_config', {})
    if node['node'] in {'stage1_page_router', 'stage2_element_router'} and settings.get('enabled', True):
        settings['server_url'] = os.environ['ROUTER_SERVER_URL']
        services.add('router')
    if node['node'] == 'dolphin_layout_parser' and settings.get('v1_transport') == 'fastapi':
        settings['v1_server_url'] = os.environ['LOCAL_DOLPHIN_URL']
        services.add('dolphin')
    if node['node'] == 'paddle_triton_ocr' and settings.get('transport') == 'fastapi':
        settings['server_url'] = os.environ['LOCAL_PADDLE_URL']
        services.add('paddle')
if template.get('pricing_file') is not None:
    # Resolve environment references for the path only, never credentials.
    from core.engine.config.runtime_config import load_yaml_with_env
    pricing = Path(load_yaml_with_env(str(source))['pricing_file'])
    template['pricing_file'] = str((source.parent / pricing).resolve())
run_config = evidence / 'quickstart.yaml'
run_config.write_text(yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding='utf-8')
raw = load_yaml_with_env(str(run_config))
fixture = Path(sys.argv[2] or raw['input_dir']).resolve()
if not fixture.is_file() or fixture.suffix.lower() != '.pdf':
    raise SystemExit('ERROR: input PDF not found; supply an existing PDF as the second argument')
for node in raw['pipeline']['nodes']:
    settings = node.get('node_config', {})
    if 'api_key' in settings and not str(settings['api_key'] or '').strip():
        raise SystemExit(f'ERROR: API key is empty for node {node["id"]}; configure .env')
template['input_dir'] = str(fixture)
template['output_dir'] = str(output)
run_config.write_text(yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding='utf-8')
native = load_native_runtime_config(load_yaml_with_env(str(run_config)))
compile_pipeline_graph(native.pipeline, registry=build_node_registry_for_graph(native.pipeline))
for label, path in [('fixture', fixture), ('config', source)]:
    (evidence / f'{label}-sha256.txt').write_text(
        f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n', encoding='utf-8')
(evidence / 'services.txt').write_text('\n'.join(sorted(services)) + '\n', encoding='utf-8')
print('Config, input PDF, and credentials validated; native DAG compiled.')
PY

needs_service() {
    local target="$1" service
    while IFS= read -r service; do
        [[ "$service" != "$target" ]] || return 0
    done < "$evidence_dir/services.txt"
    return 1
}

check_port() {
    "$parser_python" - "$1" <<'PY'
import socket
import sys
with socket.socket() as sock:
    try:
        sock.bind(('127.0.0.1', int(sys.argv[1])))
    except OSError:
        raise SystemExit(f'ERROR: port {sys.argv[1]} is occupied; choose another provider port') from None
PY
}

if needs_service dolphin; then check_port "$dolphin_port"; fi
if needs_service paddle; then check_port "$paddle_port"; fi
if needs_service router; then
    check_port "$router_port"
    "$parser_python" tools/serve_router.py --check > "$evidence_dir/router-checkpoints.txt"
    "$parser_python" - "$evidence_dir" <<'PY_HASH'
import hashlib, json, sys
from pathlib import Path
from router_server.settings import checkpoint_paths
Path(sys.argv[1], "router-checkpoint-sha256.json").write_text(json.dumps({
    name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    for name, path in checkpoint_paths().items()
}, indent=2) + "\n")
PY_HASH
fi

if needs_service paddle; then
    local_font_path="$("$parser_python" "$repo_root/tools/quickstart/resolve_paddle_font.py" "$repo_root/tmp/paddle_fonts")"
    printf 'Using PaddleX font: %s\n' "$local_font_path"
fi

if needs_service dolphin; then
    printf 'Creating fresh Dolphin CPU environment (Python 3.12)...\n'
    create_environment "$dolphin_prefix" 3.12
    if [[ "$(uname -s)" == Linux ]]; then
        "$dolphin_prefix/bin/python" -m pip install torch==2.2.2 torchvision==0.17.2 --index-url https://download.pytorch.org/whl/cpu
    else
        "$dolphin_prefix/bin/python" -m pip install torch==2.2.2 torchvision==0.17.2
    fi
    "$dolphin_prefix/bin/python" -m pip install -r "$repo_root/tutorial/dolphin_15_fastapi/requirements.txt"
    record_environment "$dolphin_prefix" dolphin
fi
if needs_service paddle; then
    printf 'Creating fresh Paddle CPU environment (Python 3.11)...\n'
    create_environment "$paddle_prefix" 3.11
    "$paddle_prefix/bin/python" -m pip install paddlepaddle==3.0.0 --index-url https://pypi.org/simple
    "$paddle_prefix/bin/python" -m pip install -r "$repo_root/tutorial/paddle_ocr_fastapi/requirements.txt"
    record_environment "$paddle_prefix" paddle
fi

wait_for_server() {
    local name="$1" port="$2" pid="$3" instance="$4" health_path="${5:-/healthz}" deadline=$((SECONDS + ready_timeout))
    while (( SECONDS < deadline )); do
        kill -0 "$pid" 2>/dev/null || fail "$name exited during startup; see $evidence_dir/$name-server.log"
        if curl --silent --fail --noproxy '*' --connect-timeout 1 --max-time 2 \
            "http://127.0.0.1:$port$health_path" -o "$evidence_dir/$name-health.pending.json"; then
            if "$parser_python" - "$evidence_dir/$name-health.pending.json" "$instance" "$name" <<'PY'
import json
import sys
try:
    with open(sys.argv[1], encoding='utf-8') as file:
        payload = json.load(file)
    valid = payload.get('status') == 'ok' and payload.get('instance_id') == sys.argv[2]
    if sys.argv[3] == 'router':
        valid = valid and payload.get('device') == 'cpu' and set(payload.get('models_loaded', [])) == {'binary', 'fig', 'tab'}
except (ValueError, AttributeError):
    valid = False
raise SystemExit(0 if valid else 1)
PY
            then
                mv "$evidence_dir/$name-health.pending.json" "$evidence_dir/$name-health.json"
                printf '%s ready on 127.0.0.1:%s\n' "$name" "$port"
                return
            fi
        fi
        if (( SECONDS % 30 == 0 )); then printf 'Waiting for %s model initialization...\n' "$name"; fi
        sleep 1
    done
    fail "$name startup timed out after ${ready_timeout}s; see $evidence_dir/$name-server.log"
}

if needs_service router; then
    printf 'Starting router CPU server in parser environment...\n'
    env PYTHONUNBUFFERED=1 ROUTER_DEVICE=cpu ROUTER_INSTANCE_ID="$run_id-router" \
        "$parser_python" tools/serve_router.py --host 127.0.0.1 --port "$router_port" > "$evidence_dir/router-server.log" 2>&1 &
    router_pid=$!
    process_pids+=("$router_pid")
fi
if needs_service dolphin; then
    printf 'Starting Dolphin CPU server (first start downloads the model)...\n'
    env PYTHONUNBUFFERED=1 DOLPHIN_15_DEVICE=cpu DOLPHIN_15_PORT="$dolphin_port" \
        DOLPHIN_15_INSTANCE_ID="$run_id-dolphin" \
        "$dolphin_prefix/bin/python" "$repo_root/tutorial/dolphin_15_fastapi/server.py" > "$evidence_dir/dolphin-server.log" 2>&1 &
    dolphin_pid=$!
    process_pids+=("$dolphin_pid")
fi
if needs_service paddle; then
    printf 'Starting Paddle CPU server (first start downloads the models)...\n'
    env PYTHONUNBUFFERED=1 PADDLE_OCR_DEVICE=cpu PADDLE_OCR_HOST=127.0.0.1 \
        PADDLE_OCR_PORT="$paddle_port" PADDLE_OCR_INSTANCE_ID="$run_id-paddle" \
        PADDLE_PDX_LOCAL_FONT_FILE_PATH="$local_font_path" \
        "$paddle_prefix/bin/python" "$repo_root/tutorial/paddle_ocr_fastapi/server.py" > "$evidence_dir/paddle-server.log" 2>&1 &
    paddle_pid=$!
    process_pids+=("$paddle_pid")
fi
if needs_service router; then wait_for_server router "$router_port" "$router_pid" "$run_id-router" /health; fi
if needs_service dolphin; then wait_for_server dolphin "$dolphin_port" "$dolphin_pid" "$run_id-dolphin"; fi
if needs_service paddle; then wait_for_server paddle "$paddle_port" "$paddle_pid" "$run_id-paddle"; fi

printf 'Running: python main.py %s\n' "$run_config"
# Waiting on a background CLI lets INT/TERM interrupt it and clean up promptly.
PYTHONUNBUFFERED=1 "$parser_python" main.py "$run_config" > >(tee "$evidence_dir/main.log") 2>&1 &
cli_pid=$!
process_pids+=("$cli_pid")
wait "$cli_pid"

# Verify actual routing, model usage, page completeness and native text preservation.
"$parser_python" tools/quickstart/verify_quickstart_result.py "$run_config" "$evidence_dir"
