"""Restore blocks with bounded page-local concurrency and per-block retries."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import closing
from copy import deepcopy
import json
import logging
import math
from pathlib import Path
import re
from threading import Event

from core.adapters.models import build_chat_model_adapter
from core.adapters.models.unified_client import ProviderRequestError
from core.adapters.models.reasoning import resolve_reasoning
from core.adapters.models.capabilities import DEFAULT_CAPABILITIES
from core.adapters.models.unified_client import normalize_provider, _resolve_api_type
from core.domain.layout.models import LayoutBlockDTO, PageEnrichedDTO
from core.engine.runtime.cancellation import PipelineCancelled
from core.engine.runtime.block_context_budget import BlockContextDeadlineExceeded, BlockContextBudget
from core.services.page_failures import page_failures
from core.services.prompt_policy import DEFAULT_PROMPT_POLICY
from core.interfaces.adapters import ChatModelAdapter, ChatModelRequest
from core.prompts.block_context import PROMPT_VERSION, RESPONSE_SCHEMA, build_block_context_prompt
from core.prompts.utils import VLM_CAPTION_START_TAG, VLM_CAPTION_END_TAG
from core.services.layout_markdown import build_structured_markdown_blocks
from core.services.pdf_rendering import render_pdf_page

TABLE_LABELS = {"table", "tab"}
IMAGE_LABELS = {"img", "fig", "figure", "image", "picture", "chart"}
REFERENCES = re.compile(r"\[\[(?:TABLE|IMAGE)_BLOCK:[^\]\n]+\]\]")


class BlockResponseError(ValueError):
    """Code-verified response/schema or content preservation failure."""


def validate_role_model(block_kind: str, model_name: str, provider: str | None, api_type: str | None,
                        reasoning=None, extra_body=None, capability_registry=None, deployment=None) -> None:
    expected = "gpt-6-luna" if block_kind == "text" else "gemini-3.8-flash"
    api = "openai" if block_kind == "text" else "gemini"
    if block_kind not in {"text", "table", "image"} or model_name != expected or api_type != api:
        raise ValueError(f"{block_kind} requires {expected} / {api}")
    normalized = normalize_provider(provider or "openai-compatible")
    resolved_api = _resolve_api_type(normalized, api_type)
    resolved = resolve_reasoning(normalized, resolved_api, model_name, reasoning, extra_body, registry=capability_registry or DEFAULT_CAPABILITIES, deployment=deployment)
    if resolved.request_model != expected or resolved_api != api:
        raise ValueError("resolved model does not match block restoration role")
    if any(key in (extra_body or {}) for key in ("model", "model_name", "provider", "api_type")):
        raise ValueError("extra_body cannot override the restoration model connection")


def is_restore_target(block: LayoutBlockDTO, block_kind: str) -> bool:
    label = (block.label or "").strip().lower()
    if (label == "whole_page" or block.metadata.get("native_text_direct")
            or block.metadata.get("whole_page_llm")):
        return False
    if not (block.text or "").strip():
        return False
    table = label in TABLE_LABELS or bool((block.table_html_raw or "").strip())
    image = label in IMAGE_LABELS
    if block_kind == "table":
        return table
    if block_kind == "image":
        if not image:
            return False
        # Link-only logos and captions without actual content have no restoration target.
        text = block.text or ""
        if VLM_CAPTION_START_TAG.strip() in text:
            _, _, caption = text.partition(VLM_CAPTION_START_TAG.strip())
            caption, end, _ = caption.partition(VLM_CAPTION_END_TAG.strip())
            return bool(end and caption.strip())
        description = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text).strip(" `\n\t")
        return bool(description)
    return not table and not image


def count_reference_tokens(text: str) -> tuple[int, str]:
    """A local input estimate, never the provider's billable token count."""
    # Deterministic and offline, including on machines without tokenizer caches.
    return math.ceil(len(text.encode("utf-8")) / 3), "utf8_bytes_div_3_estimate"


def compress_table_reference(placeholder: str, summary: str | None, max_tokens: int) -> tuple[str, str, int, str]:
    # Keep whole representative rows. Never truncate a value or date mid-row.
    selected: list[str] = []
    count, method = count_reference_tokens(placeholder)
    if count > max_tokens:
        raise BlockResponseError("table_reference_budget_too_small")
    for row in (summary or "").splitlines():
        candidate = placeholder + "\n" + "\n".join([*selected, row])
        candidate_count, method = count_reference_tokens(candidate)
        if candidate_count <= max_tokens:
            selected.append(row)
            count = candidate_count
    transmitted = "\n".join(selected)
    reference = placeholder + ("\n" + transmitted if transmitted else "")
    return reference, transmitted, count, method


def validate_block_response(response: object, original: str, block_kind: str) -> dict[str, str]:
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except (json.JSONDecodeError, TypeError) as exc:
            raise BlockResponseError("invalid_json") from exc
    if (not isinstance(response, dict) or set(response) != {"reasoning", "output"}
            or any(not isinstance(response[key], str) for key in ("reasoning", "output"))):
        raise BlockResponseError("invalid_two_string_schema")
    output = response["output"]
    if not output.strip():
        raise BlockResponseError("empty_output")
    if REFERENCES.findall(output) != REFERENCES.findall(original):
        raise BlockResponseError("changed_or_invented_reference")
    if block_kind in {"table", "image"}:
        # Ignore only trailing whitespace for caption fixtures ending in a newline.
        reference = original if block_kind == "table" else original.rstrip()
        if not output.startswith(reference):
            raise BlockResponseError("changed_table_reference" if block_kind == "table" else "changed_image_caption")
        tail = output[len(reference):]
        if tail and not tail.startswith(("\n", "\r")) and tail.strip():
            raise BlockResponseError("context_must_follow_reference")
        if block_kind == "image":
            if (VLM_CAPTION_START_TAG.strip() in tail or VLM_CAPTION_END_TAG.strip() in tail
                    or re.search(r"!\[[^\]]*\]\([^)]*\)", tail)):
                raise BlockResponseError("duplicated_image_caption_or_link")
        elif re.search(r"(?:^|\n)(?:header|first_row|last_row):|<table\b|(?:^|\n)\|", tail, re.I):
            raise BlockResponseError("duplicated_table_or_summary")
    else:
        # Allow Markdown and inserted context while requiring original words, numbers,
        # names and negations in their original order. Visual accuracy needs live eval.
        def tokens(text):
            # Markdown emphasis may divide Korean words; remove it before lexing.
            text = re.sub(r"[~*`]+", "", text)
            return re.findall(r"[+-]?\d+(?:[.,]\d+)*(?:%|‰)?|[^\W\d]+|[^\w\s]", text)
        remaining = iter(tokens(output))
        if any(not any(candidate == token for candidate in remaining) for token in tokens(original)):
            raise BlockResponseError("changed_or_missing_text")
        links = r"!?\[[^\]]*\]\([^)]*\)"
        if re.findall(links, output) != re.findall(links, original):
            raise BlockResponseError("changed_or_invented_link")
    if re.findall(r"(?m)^@page:.*$", output) != re.findall(r"(?m)^@page:.*$", original):
        raise BlockResponseError("changed_page_marker")
    return response


def restore_page_block_context(
    page: PageEnrichedDTO, *, block_kind: str, model_name: str, api_type: str,
    source_node_id: str | None = None, provider: str | None = None,
    base_url: str | None = None, api_key: str | None = None, api_version: str | None = None,
    project_id: str | None = None, extra_body: dict | None = None, reasoning: dict | None = None,
    user_prompt: str | None = None, skip_levels: Sequence[int] = (1,),
    table_input_max_tokens: int = 256, max_processing_attempts_per_block: int = 2,
    few_shot_examples: Sequence[int] = (1, 2), adapter: ChatModelAdapter | None = None,
    usage_callback: Callable | None = None, trace_metadata: dict | None = None,
    timeout_seconds: float | None = None, cancellation_check: Callable | None = None,
    deadline_monotonic: float | None = None,
    prompt_policy=None, pricing_snapshot=None, capability_registry=None, deployment=None,
    max_workers: int = 1,
) -> PageEnrichedDTO:
    if type(max_workers) is not int or max_workers < 1:
        raise ValueError("max_workers must be a positive integer")
    stopped = Event()

    def check_cancelled():
        return stopped.is_set() or (cancellation_check is not None and cancellation_check())

    control = BlockContextBudget(600.0 if timeout_seconds is None and deadline_monotonic is None else timeout_seconds, check_cancelled, deadline_monotonic)
    control.checkpoint()
    validate_role_model(block_kind, model_name, provider, api_type, reasoning, extra_body, capability_registry, deployment)
    if type(max_processing_attempts_per_block) is not int or not 1 <= max_processing_attempts_per_block <= 2:
        raise ValueError("actual calls per block must be between one and two")
    result = deepcopy(page)
    result.source_node_id = source_node_id or page.source_node_id
    if page_failures(page.page) or page.page.metadata.get("stage1_level") in skip_levels or page.page.metadata.get("native_text_direct"):
        return result
    targets = [block for block in result.blocks if is_restore_target(block, block_kind)]
    control.checkpoint()
    if not targets:
        return result
    tables = {}
    if block_kind == "table":
        tables = {item.block_id: item for item in build_structured_markdown_blocks(result, stable_table_ids=True)}
    prepared = []
    for block in targets:
        control.checkpoint()
        context = {"block_id": block.block_id, "role": block_kind, "prompt_version": PROMPT_VERSION,
                   "few_shot_examples": list(few_shot_examples), "original_text": block.text,
                   "model_name": model_name, "attempts": 0, "status": "failed"}
        block.metadata["block_context_restore"] = context
        reference = block.text
        if block_kind == "table":
            table = tables[block.block_id]
            if not table.rendered_text.strip():
                context["error_code"] = "invalid_rendered_table"
                continue
            try:
                reference, summary, token_count, method = compress_table_reference(
                    table.placeholder, table.summary, table_input_max_tokens)
            except BlockResponseError as exc:
                context["error_code"] = str(exc)
                continue
            context.update(placeholder=table.placeholder, transmitted_summary=summary,
                           input_reference=reference, input_tokens_estimate=token_count,
                           token_count_method=method)
        prepared.append((block, reference, context))
    if not prepared:
        return result
    model_adapter = adapter or build_chat_model_adapter(provider)
    control.checkpoint()
    if result.page.pdf_artifact is None:
        for _, _, context in prepared:
            context["error_code"] = "missing_pdf_artifact"
        return result
    # Renderer owns PDF handles; this service owns the image for this invocation.
    try:
        image = render_pdf_page(Path(result.page.pdf_artifact.path), dpi=300, require_single_page=True)
    except (PipelineCancelled, BlockContextDeadlineExceeded):
        raise
    except Exception as exc:
        for _, _, context in prepared:
            context["error_code"] = f"render_error:{type(exc).__name__}"
        return result

    def restore_block(block, reference, context, block_image):
        try:
            task = build_block_context_prompt(
                block_kind, reference, user_prompt=user_prompt,
                few_shot_examples=list(few_shot_examples), block_id=block.block_id,
                policy=prompt_policy or DEFAULT_PROMPT_POLICY,
            )
        except ValueError:
            context["error_code"] = "prompt_context_invalid"
            return
        for attempt in range(1, max_processing_attempts_per_block + 1):
            control.checkpoint()
            validate_role_model(block_kind, model_name, provider, api_type, reasoning, extra_body, capability_registry, deployment)
            context["attempts"] = attempt
            metadata = {**(trace_metadata or {}), "page_no": result.page.page_no,
                        "block_id": block.block_id, "block_kind": block_kind,
                        "prompt_version": PROMPT_VERSION, "few_shot_examples": list(few_shot_examples),
                        "processing_attempt": attempt, "restoration_model": model_name}
            if block_kind == "table":
                metadata.update(input_tokens_estimate=context["input_tokens_estimate"],
                                token_count_method=context["token_count_method"])

            def record_usage(record):
                if usage_callback is not None:
                    # Accounting retains actual tokens/costs, without copying document
                    # bodies or reasoning into every persisted usage event.
                    redacted = {key: value for key, value in record.items()
                                if key not in {"prompt", "output", "system_prompt", "messages"}}
                    redacted["metadata"] = {**metadata, **record.get("metadata", {})}
                    try:
                        usage_callback(redacted)
                    except Exception:
                        logging.getLogger(__name__).warning("block context usage callback failed")

            try:
                response = model_adapter.invoke(ChatModelRequest(
                    prompt="", task_prompt=task, model_name=model_name, images=[block_image],
                    schema=deepcopy(RESPONSE_SCHEMA), base_url=base_url, api_key=api_key,
                    api_version=api_version, project_id=project_id, api_type=api_type,
                    extra_body=deepcopy(extra_body or {}), reasoning=reasoning,
                    usage_callback=record_usage, trace_metadata=metadata,
                    timeout_seconds=control.remaining_seconds(), cancellation_check=check_cancelled,
                    prompt_policy=prompt_policy, pricing_snapshot=pricing_snapshot,
                    capability_registry=capability_registry, deployment=deployment,
                    deadline_monotonic=control.deadline_monotonic, retry_max_attempts=1,
                    strict_response=True,
                ))
            except (PipelineCancelled, BlockContextDeadlineExceeded):
                raise
            except Exception as exc:
                context["error_code"] = (str(exc) if isinstance(exc, BlockResponseError)
                                         else f"request_error:{type(exc).__name__}")
                if isinstance(exc, ValueError) or (isinstance(exc, ProviderRequestError)
                        and exc.details.get("http_status") in {400, 401, 403, 404}):
                    break
                continue
            control.checkpoint()
            try:
                validated = validate_block_response(response, reference, block_kind)
            except BlockResponseError as exc:
                context["error_code"] = str(exc)
                continue
            context.update(status="restored", reasoning=validated["reasoning"], output=validated["output"])
            context.pop("error_code", None)
            if block_kind != "table":
                block.text = validated["output"]
            break

    worker_count = min(max_workers, len(prepared))
    with closing(image):
        if worker_count == 1:
            for block, reference, context in prepared:
                restore_block(block, reference, context, image)
        else:
            def process_block(item):
                control.checkpoint()
                # PIL encoders may mutate image state; each worker owns its copy.
                with closing(image.copy()) as block_image:
                    restore_block(*item, block_image)

            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                pending = set()
                remaining = iter(prepared)
                try:
                    # Keep only worker_count tasks in flight so an abort does not
                    # leave a page's worth of queued requests running afterwards.
                    for _ in range(worker_count):
                        control.checkpoint()
                        pending.add(executor.submit(process_block, next(remaining)))
                    while pending:
                        control.checkpoint()
                        done, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                        for future in done:
                            future.result()
                        for _ in done:
                            item = next(remaining, None)
                            if item is None:
                                break
                            control.checkpoint()
                            pending.add(executor.submit(process_block, item))
                except BaseException:
                    stopped.set()
                    for future in pending:
                        future.cancel()
                    # Drain running calls before closing their shared source image.
                    raise
    control.checkpoint()
    return result
