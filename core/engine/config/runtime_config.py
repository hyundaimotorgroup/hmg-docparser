from __future__ import annotations

import os
import re
from pathlib import Path
from dataclasses import dataclass

import yaml
from dotenv import load_dotenv


CONFIG_DIR = "configs"
ALLOWED_CONFIGS = {
    "quickstart": "local_quickstart.yaml",
    "beta": "beta.yaml",
    "managed_endpoints": "managed_endpoints.yaml",
    "group_internal": "group_internal.yaml",
    "default": "default.yaml",
}


def _resolve_env_refs(value):
    """Resolve whole-value env references, with optional ``:-`` defaults."""
    if isinstance(value, str):
        match = re.fullmatch(
            r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*))?\}", value, re.DOTALL
        )
        if match:
            name, default = match.groups()
            resolved = os.getenv(name)
            if default is not None and not resolved:
                return _resolve_env_refs(default)
            if resolved is None:
                raise ValueError(
                    f"환경변수 미설정: {name} (config의 ${{{name}}} 참조). .env를 확인하세요."
                )
            return resolved
        return value
    if isinstance(value, dict):
        resolved = {}
        for key, item in value.items():
            entry = (
                item
                if key in {"user_prompt", "node_overrides", "prompt"}
                else _resolve_env_refs(item)
            )
            if (
                key in {"ssl", "v1_ssl", "v2_ssl"}
                and isinstance(item, str)
                and re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::-[^}]*)?\}", item)
                and isinstance(entry, str)
                and entry.lower() in {"true", "false"}
            ):
                entry = entry.lower() == "true"
            resolved[key] = entry
        return resolved
    if isinstance(value, list):
        return [_resolve_env_refs(item) for item in value]
    return value


class LoadedConfig(dict):
    """Mapping carrying source location without adding serialized config fields."""

    def __init__(self, data, config_dir):
        super().__init__(data)
        self.config_dir = Path(config_dir)


def load_yaml_with_env(config_path: str) -> dict:
    load_dotenv()  # repo .env -> os.environ (config의 ${} 치환용). 기존 환경변수는 덮지 않는다.
    with open(config_path, "r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    return LoadedConfig(_resolve_env_refs(raw), Path(config_path).resolve().parent)


@dataclass(slots=True)
class RuntimeConfig:
    """Minimal runtime state derived from a validated native YAML document."""

    inputs: str
    outputs: str
    job_id: str = "main"


def load_config_by_name(config_name: str) -> dict:
    """Load one of the shipped public YAML documents; validation occurs at execution."""
    if config_name not in ALLOWED_CONFIGS:
        raise ValueError(f"지원하지 않는 config명입니다: {config_name}")
    config_path = os.path.join(CONFIG_DIR, ALLOWED_CONFIGS[config_name])
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config 파일이 없습니다: {config_path}")
    return load_yaml_with_env(config_path)
