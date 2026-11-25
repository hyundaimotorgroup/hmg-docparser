"""Read-only metadata used by the local native-config editor."""

from __future__ import annotations

from typing import Any

from core.engine.config.compiler import DEFAULT_KNOWN_DTO_TYPES
from core.engine.config.node_config import NODE_CONFIG_SCHEMAS
from core.engine.registry.bootstrap import register_node_by_name
from core.engine.registry.in_memory import InMemoryNodeRegistry

SECRET_FIELD_NAMES = frozenset(
    {"api_key", "token", "password", "secret", "client_secret"}
)
FIELD_DESCRIPTIONS = {
    "encoding": "입력 Markdown 파일을 해석할 문자 인코딩입니다.",
    "keep_page_artifacts": "페이지 이미지·중간 산출물을 debug artifact로 보존합니다.",
    "output_dir": "node가 만드는 선택적 debug artifact의 디렉터리입니다.",
    "version": "사용할 Dolphin layout provider 버전입니다.",
    "server_url": "해당 provider의 HTTPS/HTTP endpoint URL입니다.",
    "base_url": "LLM/VLM provider의 API base URL입니다.",
    "model_name": "provider에서 호출할 모델 이름입니다.",
    "prompt": "whole-page의 신뢰된 system 지시입니다.",
    "user_prompt": "추가 요청 · 기본 상한 8,192 Unicode code point / UTF-8 32 KiB. 빈 값·공백·null은 해제. ${NAME}은 문자 그대로 유지합니다.",
    "reasoning": "신뢰된 개발자 옵션. 지원 모델은 설정 생략 시 low, 미등록 모델은 옵션 생략.",
    "token": "provider 인증 token입니다.",
    "api_key": "provider API key입니다.",
    "project_id": "provider에서 사용할 선택적 project/tenant 식별자입니다.",
    "ssl": "endpoint 연결에 TLS 검증을 사용합니다.",
    "target_size": "layout/router 입력 이미지의 목표 픽셀 크기입니다.",
    "v1_max_batch_size": "Dolphin v1 한 요청의 최대 page batch 크기입니다.",
    "block_kind": "Beta 복원 역할: text/table/image. 역할별 모델과 API가 고정됩니다.",
    "restore_tables": "표 placeholder 대신 검증된 원본 표와 복원 문맥을 직접 출력합니다.",
    "include_page_marker": "formatter의 페이지 마커를 출력합니다. beta는 assembler에서만 붙입니다.",
    "max_processing_attempts_per_block": "블록당 실제 모델 요청 상한(1~2회). 실패 시 원문 유지.",
    "few_shot_examples": "역할별 가상 예제 ID를 서로 다르게 최대 2개 선택합니다.",
    "table_input_max_tokens": "표 입력 UTF-8 bytes/3 추정치 상한이며 실제 과금 토큰은 아닙니다.",
    "skip_levels": "해당 Stage 1 페이지 level의 layout 처리 또는 Global Context VLM 후처리를 생략합니다. Global Context는 기존 본문을 보존하며 []이면 모든 페이지를 후처리합니다.",
    "input_labels": "이 label을 가진 layout block만 다음 node로 보냅니다.",
    "input_exclude_labels": "이 label을 가진 layout block을 다음 node에서 제외합니다.",
    "provider": "LLM/VLM API 형식과 인증 방식을 결정하는 provider입니다.",
    "max_workers": "이 node가 동시에 보낼 수 있는 provider 요청 수입니다.",
    "concurrency": "이 node가 동시에 처리할 작업 수입니다.",
    "progress_weight": "전체 진행률에서 이 node가 차지하는 상대 비중입니다.",
    "table_output_format": "표 VLM 결과의 public rendering 형식입니다.",
    "use_vlm_parse": "이미지 block을 VLM으로 해석할지 결정합니다.",
    "merge_key": "여러 branch 결과를 병합할 때 같은 block으로 식별하는 key입니다.",
    "field_priority": "각 결과 field에 대해 branch를 적용할 우선순위입니다.",
    "include_table_crop_images": "최종 Markdown에 표 crop image 참조를 포함합니다.",
    "task_name": "저장 artifact에 사용하는 task 이름입니다.",
    "save_debug_artifacts": "debug용 중간 Markdown artifact를 저장합니다.",
    "save_suffix": "저장하는 Markdown 파일명에 덧붙일 suffix입니다.",
    "primary_node_id": "두 Markdown branch 중 primary로 취급할 첫 번째 dependency ID입니다.",
    "enabled": "router node를 활성화할지 결정합니다.",
    "timeout_seconds": "router 요청의 최대 대기 시간(초)입니다.",
    "max_batch_size": "router 한 요청의 최대 이미지 수입니다.",
    "trigger_levels": "whole-page LLM 처리를 트리거할 router level 목록입니다.",
}


def build_editor_catalog() -> dict[str, Any]:
    """Return schema and node metadata without loading any user configuration."""
    nodes: list[dict[str, Any]] = []
    for node_name in sorted(NODE_CONFIG_SCHEMAS):
        registry = InMemoryNodeRegistry()
        register_node_by_name(registry, node_name)
        node_cls = registry.get(node_name)
        input_type = node_cls.input_type
        output_type = node_cls.output_type
        scope = _infer_scope(input_type, output_type)
        config_schema = NODE_CONFIG_SCHEMAS[node_name].model_json_schema()
        required_fields = set(config_schema.get("required", []))
        for field_name, field_schema in config_schema.get("properties", {}).items():
            field_schema["x-editor"] = {
                "required": field_name in required_fields,
                "description": _field_description(field_name, field_schema),
            }
        nodes.append(
            {
                "name": node_name,
                "input": {"type": input_type, "is_list": scope in {"page", "fanin"}},
                "output": {"type": output_type, "is_list": scope in {"fanout", "page"}},
                "execution_scope": scope,
                "optional": node_name == "confluence_uploader",
                "config_schema": config_schema,
                "secret_fields": sorted(
                    name
                    for name in NODE_CONFIG_SCHEMAS[node_name].model_fields
                    if is_secret_field(name)
                ),
            }
        )
    return {"nodes": nodes, "dto_types": sorted(DEFAULT_KNOWN_DTO_TYPES)}


def _infer_scope(input_type: str, output_type: str) -> str:
    if input_type == "document_dto@v1" and output_type == "page_dto@v1":
        return "fanout"
    if input_type == "page_markdown_dto@v1" and output_type == "document_dto@v1":
        return "fanin"
    if input_type == "document_dto@v1" and output_type == "document_dto@v1":
        return "document"
    return "page"


def is_secret_field(name: str) -> bool:
    """Recognize explicit credential fields without treating endpoint URLs as secrets."""
    return name in SECRET_FIELD_NAMES or name.endswith(
        ("_token", "_api_key", "_password", "_secret")
    )


def _field_description(name: str, schema: dict[str, Any]) -> str:
    if name.startswith("v1_") or name.startswith("v2_"):
        version, field = name.split("_", maxsplit=1)
        base = FIELD_DESCRIPTIONS.get(field, field.replace("_", " "))
        return f"Dolphin {version} 설정: {base}"
    return FIELD_DESCRIPTIONS.get(
        name, schema.get("description", name.replace("_", " "))
    )
