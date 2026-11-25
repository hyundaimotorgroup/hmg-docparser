from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from core.domain.document.models import PageDTO
from core.domain.layout.models import LayoutBlockDTO, PageEnrichedDTO
from core.interfaces.node import Node, NodeContext, NodeResult
from core.interfaces.adapters import ChatModelRequest
from core.adapters.models import build_chat_model_adapter
from core.engine.runtime.time_budget import remaining_timeout_seconds
from core.observability.llm_usage import build_llm_observability
from core.services.model_routing import node_inference_options
from core.prompts.task import TaskPrompt
from core.prompts.vlm import get_schema_vlm
from core.prompts.utils import strip_code_fence
from core.services.model_output import validate_model_output
from core.services.prompt_policy import DEFAULT_PROMPT_POLICY
from core.services.pdf_rendering import render_pdf_page
from core.services.pdfplumber_extraction import extract_pdfplumber_text_if_no_images
from core.observability.router_reports import append_jsonl
from core.services.page_failures import record_page_failure

_DEFAULT_PROMPT = "Please convert this document page to Markdown. Extract the text exactly as it appears. Do not use backticks."
_DEFAULT_DPI = 150
_OUTPUT_CONTRACT = (
    "\nReturn a JSON object with exactly one field, output, containing the complete "
    "page Markdown as a string. Do not include reasoning or wrap the response in code fences."
)


def _whole_page_text(response: object, *, policy=DEFAULT_PROMPT_POLICY) -> str:
    """Keep the page body, including envelopes from older custom adapters."""
    if isinstance(response, str):
        candidate = strip_code_fence(response).strip()
        if candidate.startswith(("{", "[")):
            try:
                response = json.loads(candidate)
            except json.JSONDecodeError:
                # A broken JSON envelope must not become the document body.
                if candidate.startswith("{"):
                    raise ValueError("whole-page response contains invalid JSON") from None
    if isinstance(response, dict):
        response = next(
            (response[key] for key in ("output", "markdown", "text", "content") if key in response),
            None,
        )
    return validate_model_output(response, policy=policy)


def _render_page(page: PageDTO, dpi: int = _DEFAULT_DPI) -> Image.Image:
    return render_pdf_page(Path(page.pdf_artifact.path), dpi=dpi)


def _extract_text_if_no_images(page: PageDTO) -> str | None:
    """Extract native text only when the page has no raster images."""
    try:
        return extract_pdfplumber_text_if_no_images(page)
    except Exception:
        return None


def _page_to_enriched(
    page: PageDTO, text: str | None, source_node_id: str, metadata: dict | None = None
) -> PageEnrichedDTO:
    block = LayoutBlockDTO(
        block_id=f"{page.document_id}:{page.page_no}:whole_page",
        label="whole_page",
        bbox=None,
        reading_order=0,
        text=text or "",
        metadata=metadata or {"whole_page_llm": True},
    )
    return PageEnrichedDTO(page=page, blocks=[block], source_node_id=source_node_id)


class WholePageLLMProcessorNode(Node):
    """Stage1 라우터가 지정한 레벨의 페이지를 처리.

    순수 텍스트 페이지는 PDF 내장 텍스트 추출 → LLM 호출 없음.
    이미지/테이블이 있는 페이지만 경량 LLM으로 전송.
    """

    node_name = "whole_page_llm_processor"
    input_type = "page_dto@v1"
    output_type = "page_enriched_dto@v1"
    is_page_parallel = True

    def run(self, context: NodeContext, value: object) -> NodeResult:
        pages: list[PageDTO] = value if isinstance(value, list) else [value]
        trigger_levels: list[int] = list(context.config.get("trigger_levels", [1]))

        model_name = _str_config(context, "model_name", "vlm_model_name", "")
        if not model_name:
            raise ValueError("whole_page_llm_processor requires model_name")

        provider = _optional_str(context.config.get("provider"))
        base_url = _optional_str(context.config.get("base_url"))
        api_key = _optional_str(context.config.get("api_key"))
        api_version = _optional_str(context.config.get("api_version"))
        project_id = _optional_str(context.config.get("project_id"))
        api_type = _optional_str(context.config.get("api_type")) or _optional_str(
            _runtime_config(context).get("vlm_api_type")
        )
        extra_body = _dict_config(context.config.get("extra_body"))

        runtime_config = _runtime_config(context)
        usage_callback, trace_metadata = build_llm_observability(context)
        adapter = build_chat_model_adapter(provider)

        prompt = context.config.get("prompt", _DEFAULT_PROMPT)
        options = node_inference_options(context)
        dpi = int(context.config.get("dpi", _DEFAULT_DPI))
        timeout = remaining_timeout_seconds(runtime_config, reserve_seconds=5.0)

        route_report_path = _resolve_report_path(context)
        report_entries: list[dict] = []

        enriched: list[PageEnrichedDTO] = []
        n_native_text = 0
        n_llm = 0

        # 벤치마크/비교용: 텍스트온리 게이트를 강제로 끄고 항상 LLM 호출
        disable_text_only_gate = bool(
            context.config.get("disable_text_only_gate", False)
        )

        for page in pages:
            stage1_level = page.metadata.get("stage1_level", 0)
            if stage1_level not in trigger_levels:
                enriched.append(
                    PageEnrichedDTO(
                        page=page, blocks=[], source_node_id=context.node_id
                    )
                )
                continue

            # ── PDF 내장 텍스트 추출 시도 ──────────────────────────────
            native_text = (
                None if disable_text_only_gate else _extract_text_if_no_images(page)
            )
            if native_text is not None:
                enriched.append(
                    _page_to_enriched(
                        page,
                        native_text,
                        context.node_id,
                        metadata={"whole_page_llm": False, "native_text_direct": True},
                    )
                )
                report_entries.append(_make_report_entry(page, "level1_text"))
                _save_page_pdf(page, "level1_text", route_report_path)
                n_native_text += 1
                continue

            # ── 경량 LLM 호출 ───────────────────────────────────────
            img: Image.Image | None = None
            try:
                img = _render_page(page, dpi=dpi)
                request = ChatModelRequest(
                    prompt="",
                    task_prompt=TaskPrompt.build(
                        "WHOLE_PAGE",
                        prompt + _OUTPUT_CONTRACT,
                        user_prompt=options.get("user_prompt"),
                        policy=options.get("prompt_policy"),
                    ),
                    **options,
                    model_name=model_name,
                    schema=get_schema_vlm("WHOLE_PAGE"),
                    images=[img],
                    base_url=base_url,
                    api_key=api_key,
                    api_version=api_version,
                    project_id=project_id,
                    api_type=api_type,
                    extra_body=extra_body,
                    usage_callback=usage_callback,
                    trace_metadata={**(trace_metadata or {}), "page_no": page.page_no},
                    timeout_seconds=timeout,
                )
                response = adapter.invoke(request)
                text = _whole_page_text(response, policy=options["prompt_policy"])
            except Exception as exc:
                record_page_failure(page, "whole_page_llm", exc)
                text = ""
            finally:
                if img is not None:
                    img.close()

            enriched.append(_page_to_enriched(page, text, context.node_id))
            report_entries.append(_make_report_entry(page, "level1_llm"))
            _save_page_pdf(page, "level1_llm", route_report_path)
            n_llm += 1

        if route_report_path and report_entries:
            append_jsonl(route_report_path, report_entries)

        out = enriched[0] if not isinstance(value, list) else enriched
        return NodeResult(
            value=out,
            metadata={"native_text_direct": n_native_text, "llm_called": n_llm},
        )


def _save_page_pdf(page: PageDTO, stage1_class: str, report_path: str | None) -> None:
    if not report_path or not page.pdf_artifact:
        return
    src = Path(page.pdf_artifact.path)
    if not src.exists():
        return
    dst_dir = Path(report_path).parent / "stage1_classes" / stage1_class
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_dir / src.name)


def _make_report_entry(page: PageDTO, stage1_class: str) -> dict:
    """stage1_class: 'level1_text' | 'level1_llm' | 'level2'"""
    return {
        "document_id": page.document_id,
        "page_no": page.page_no,
        "stage1_level": page.metadata.get("stage1_level"),
        "stage1_class": stage1_class,
    }


def _resolve_report_path(context: NodeContext) -> str | None:
    configured = context.config.get("route_report_path")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    runtime_config = context.metadata.get("runtime_config", {})
    if isinstance(runtime_config, dict):
        outputs = runtime_config.get("outputs")
        if isinstance(outputs, str) and outputs.strip():
            return str(Path(outputs) / "route_report.jsonl")
    return None


def _runtime_config(context: NodeContext) -> dict[str, object]:
    v = context.metadata.get("runtime_config", {})
    return v if isinstance(v, dict) else {}


def _str_config(
    context: NodeContext, node_key: str, runtime_key: str, default: str
) -> str:
    v = _optional_str(context.config.get(node_key))
    if v:
        return v
    v = _optional_str(_runtime_config(context).get(runtime_key))
    return v or default


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _dict_config(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}
