#!/usr/bin/env python3
"""Launch the loopback-only native YAML graph configuration editor."""

from __future__ import annotations

# ruff: noqa: E402 -- direct script invocation requires repository path bootstrap

import argparse
from copy import deepcopy
import json
import re
import sys
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml
from pydantic import ValidationError

from core.engine.config.compiler import compile_pipeline_graph
from core.engine.config.editor_metadata import build_editor_catalog
from core.engine.config.runtime_config import ALLOWED_CONFIGS
from core.engine.config.translator import load_native_runtime_config
from core.engine.registry.bootstrap import build_node_registry_for_graph
from core.services.input_limits import InputTooLarge, configured_limit
from core.services.prompt_policy import safe_validation_details

STATIC_DIR = ROOT / "tools" / "config_editor_static"
MAX_REQUEST_BYTES = configured_limit("CONFIG_EDITOR_MAX_REQUEST_BYTES", 2_000_000)
MAX_YAML_DEPTH = configured_limit("CONFIG_EDITOR_MAX_YAML_DEPTH", 128)
MAX_YAML_NODES = configured_limit("CONFIG_EDITOR_MAX_YAML_NODES", 100_000)
MAX_YAML_ALIASES = configured_limit("CONFIG_EDITOR_MAX_YAML_ALIASES", 10_000)
MAX_EXPANDED_NODES = configured_limit("CONFIG_EDITOR_MAX_EXPANDED_NODES", 1_000_000)
MAX_EXPANDED_BYTES = configured_limit(
    "CONFIG_EDITOR_MAX_EXPANDED_BYTES", 64 * 1024 * 1024
)
MAX_CONCURRENT_REQUESTS = configured_limit("CONFIG_EDITOR_MAX_CONCURRENT_REQUESTS", 8)
MAX_QUEUED_REQUESTS = configured_limit("CONFIG_EDITOR_MAX_QUEUED_REQUESTS", 64)
READ_TIMEOUT_SECONDS = configured_limit("CONFIG_EDITOR_READ_TIMEOUT_SECONDS", 120)


class ConfigEditorServer(ThreadingHTTPServer):
    """Bound worker/queued connections without changing the editor's bind policy."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.workers = (
            threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
            if MAX_CONCURRENT_REQUESTS
            else None
        )
        self.connections = (
            threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS + MAX_QUEUED_REQUESTS)
            if MAX_CONCURRENT_REQUESTS
            else None
        )
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address) -> None:
        if self.connections is not None and not self.connections.acquire(
            blocking=False
        ):
            try:
                request.settimeout(1)
                request.sendall(
                    b"HTTP/1.0 503 Service Unavailable\r\nRetry-After: 1\r\nContent-Length: 0\r\n\r\n"
                )
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            if self.connections is not None:
                self.connections.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        acquired = False
        try:
            if self.workers is not None:
                self.workers.acquire()
                acquired = True
            super().process_request_thread(request, client_address)
        finally:
            if acquired:
                self.workers.release()
            if self.connections is not None:
                self.connections.release()


def shipped_configs() -> dict[str, Any]:
    """Load public YAML templates without resolving their environment references."""
    return {
        name: yaml.safe_load((ROOT / "configs" / filename).read_text(encoding="utf-8"))
        for name, filename in ALLOWED_CONFIGS.items()
    }


def validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Use the same strict validation and compiler as the CLI, without executing a pipeline."""
    try:
        preview = deepcopy(raw)
        # Validate typed SSL references using their public defaults, never .env.
        pipeline = preview.get("pipeline")
        nodes = pipeline.get("nodes") if isinstance(pipeline, dict) else None
        for node in nodes if isinstance(nodes, list) else []:
            options = node.get("node_config") if isinstance(node, dict) else None
            for key, value in options.items() if isinstance(options, dict) else []:
                if key in {"ssl", "v1_ssl", "v2_ssl"} and isinstance(value, str):
                    match = re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-(true|false)\}", value, re.IGNORECASE)
                    if match:
                        node["node_config"][key] = match[1].lower() == "true"
        config = load_native_runtime_config(preview)
        registry = build_node_registry_for_graph(config.pipeline)
        compiled = compile_pipeline_graph(config.pipeline, registry=registry)
    except (ValidationError, ValueError, TypeError) as exc:
        details = safe_validation_details(exc)
        return {
            "valid": False,
            "message": "configuration validation failed",
            "details": details,
        }
    return {"valid": True, "topological_order": compiled.topological_order}


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


class ConfigEditorHandler(SimpleHTTPRequestHandler):
    """HTTP handler intentionally keeps submitted YAML and secrets in request memory only."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(READ_TIMEOUT_SECONDS or None)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Do not emit request data. In particular, direct secret values must not reach logs.
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/catalog":
            self._send_json(
                {"catalog": build_editor_catalog(), "configs": shipped_configs()}
            )
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/api/validate", "/api/export", "/api/import"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            body = self._read_json()
            if self.path == "/api/validate":
                self._send_json(validate_config(_require_mapping(body.get("config"))))
            elif self.path == "/api/export":
                self._send_yaml(_require_mapping(body.get("config")))
            else:
                self._send_json({"config": _load_yaml(body.get("yaml"))})
        except InputTooLarge as exc:
            self._send_json(
                {"valid": False, "message": str(exc)},
                status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
        except RecursionError:
            self._send_json(
                {"valid": False, "message": "configuration is too deeply nested"},
                status=HTTPStatus.BAD_REQUEST,
            )
        except TimeoutError:
            self._send_json(
                {"valid": False, "message": "request body read timed out"},
                status=HTTPStatus.REQUEST_TIMEOUT,
            )
        except (TypeError, ValueError, yaml.YAMLError):
            self._send_json(
                {"valid": False, "message": "invalid configuration request"},
                status=HTTPStatus.BAD_REQUEST,
            )

    def _read_json(self) -> dict[str, Any]:
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Transfer-Encoding is not supported; send Content-Length")
        if len(self.headers.get_all("Content-Length", [])) > 1:
            raise ValueError("multiple Content-Length headers are not supported")
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0:
            raise ValueError("Content-Length must not be negative")
        if MAX_REQUEST_BYTES and length > MAX_REQUEST_BYTES:
            raise InputTooLarge("request bytes exceed the configured limit")
        return _require_mapping(json.loads(self.rfile.read(length).decode("utf-8")))

    def _send_json(
        self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_yaml(self, config: dict[str, Any]) -> None:
        encoded = yaml.safe_dump(config, allow_unicode=True, sort_keys=False).encode(
            "utf-8"
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-yaml; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="pipeline.yaml"')
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def _require_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("a JSON object is required")
    return value


def _load_yaml(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        raise TypeError("yaml must be a string")
    loader = _BoundedSafeLoader(value)
    try:
        node = loader.get_single_node()
        # Check aliases/merge keys before SafeLoader constructs flattened mappings.
        _check_expansion(node)
        config = _require_mapping(
            (loader.construct_document(node) if node is not None else None) or {}
        )
    finally:
        loader.dispose()
    _check_expansion(config)
    return config


class _BoundedSafeLoader(yaml.SafeLoader):
    def __init__(self, stream) -> None:
        super().__init__(stream)
        self.depth = self.nodes = self.aliases = 0

    def compose_node(self, parent, index):
        self.nodes += 1
        if MAX_YAML_NODES and self.nodes > MAX_YAML_NODES:
            raise ValueError("YAML has too many nodes")
        if self.check_event(yaml.AliasEvent):
            self.aliases += 1
            if MAX_YAML_ALIASES and self.aliases > MAX_YAML_ALIASES:
                raise ValueError("YAML has too many aliases")
        self.depth += 1
        try:
            if MAX_YAML_DEPTH and self.depth > MAX_YAML_DEPTH:
                raise ValueError("YAML is too deeply nested")
            return super().compose_node(parent, index)
        finally:
            self.depth -= 1


def _check_expansion(value: Any) -> None:
    """Bound alias expansion before construction and before JSON serialization."""
    memo: dict[int, tuple[int, int]] = {}
    visiting: set[int] = set()

    def count(node: Any) -> tuple[int, int]:
        if isinstance(node, yaml.ScalarNode):
            return count(node.value)
        if not isinstance(
            node, (dict, list, tuple, yaml.MappingNode, yaml.SequenceNode)
        ):
            # Also reject SafeLoader scalars that cannot be represented by the JSON API.
            return 1, len(json.dumps(node, ensure_ascii=False).encode("utf-8"))
        identity = id(node)
        if identity in visiting:
            raise ValueError("cyclic YAML aliases are not supported")
        if identity in memo:
            return memo[identity]
        visiting.add(identity)
        total = 1
        size = 2
        try:
            if isinstance(node, (dict, yaml.MappingNode)):
                pairs = node.items() if isinstance(node, dict) else node.value
                children = (item for pair in pairs for item in pair)
            else:
                children = iter(
                    node.value if isinstance(node, yaml.SequenceNode) else node
                )
            for child in children:
                child_nodes, child_bytes = count(child)
                total += child_nodes
                size += child_bytes + 2
                if MAX_EXPANDED_NODES and total > MAX_EXPANDED_NODES:
                    raise ValueError("expanded YAML is too large")
                if MAX_EXPANDED_BYTES and size > MAX_EXPANDED_BYTES:
                    raise ValueError("expanded YAML bytes exceed the configured limit")
            memo[identity] = (total, size)
            return total, size
        finally:
            visiting.remove(identity)

    count(value)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the local native YAML graph configuration editor."
    )
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1"])
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ConfigEditorServer((args.host, args.port), ConfigEditorHandler)
    print(f"Config editor: http://{args.host}:{args.port}")
    print(
        "Submitted configuration and direct secrets are held only in request/browser memory."
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
