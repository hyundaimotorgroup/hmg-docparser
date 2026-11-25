from __future__ import annotations

import dataclasses
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from core.adapters.router_infer import infer_stage2
from core.domain.layout.models import LayoutBlockDTO, PageLayoutDTO
from core.interfaces.node import Node, NodeContext, NodeResult
from core.services.dolphin_layout import (
    DEFAULT_DOLPHIN_V2_TARGET_SIZE,
    render_page_pdf_for_dolphin,
)
from core.services.page_failures import record_page_failure
from core.observability.router_reports import append_router_records, append_jsonl

_TAB_LABELS = {"table", "tab"}
_FIG_LABELS = {"fig", "figure", "image", "img", "picture", "chart"}


def _get_crop(block: LayoutBlockDTO, page_image: Image.Image | None) -> Image.Image | None:
    if block.crop_artifact:
        crop_path = Path(block.crop_artifact.path)
        if crop_path.exists():
            with Image.open(crop_path) as image:
                image.load()
                return image.copy()
    if page_image is not None and block.bbox is not None:
        return page_image.crop(block.bbox)
    return None


def _render_page_if_needed(page_layout: PageLayoutDTO, target_size: int) -> Image.Image | None:
    relevant = [b for b in page_layout.blocks if (b.label or "").lower() in _TAB_LABELS | _FIG_LABELS]
    if not relevant:
        return None
    if all(b.crop_artifact and Path(b.crop_artifact.path).exists() for b in relevant):
        return None
    try:
        return render_page_pdf_for_dolphin(page_layout.page, target_size=target_size)
    except Exception:
        return None


class Stage2ElementRouterNode(Node):
    node_name = "stage2_element_router"
    input_type = "page_layout_dto@v1"
    output_type = "page_layout_dto@v1"

    def run(self, context: NodeContext, value: object) -> NodeResult:
        if not context.config.get("enabled", True):
            return NodeResult(value=value, metadata={"skipped": True})

        # 라우팅 결과 저장 경로: node_config.route_report_path 또는 runtime outputs 기반 자동 결정
        route_report_path = _resolve_report_path(context)

        pages: list[PageLayoutDTO] = value if isinstance(value, list) else [value]
        if not all(isinstance(page, PageLayoutDTO) for page in pages):
            raise TypeError("stage2_element_router expects PageLayoutDTO or list[PageLayoutDTO]")
        server_url = context.config.get("server_url", "")
        if not server_url:
            return NodeResult(value=value, metadata={"skipped": True, "reason": "no server_url"})

        target_size = int(context.config.get("target_size", DEFAULT_DOLPHIN_V2_TARGET_SIZE))
        ssl = bool(context.config.get("ssl", False))
        token = context.config.get("token")
        timeout_seconds = context.config.get("timeout_seconds")
        max_batch_size = int(context.config.get("max_batch_size", 16))

        page_images: list[Image.Image | None] = []
        try:
            page_images = [_render_page_if_needed(page_layout, target_size) for page_layout in pages]

            # 1차 패스: fig/tab 크롭을 모아서 배치로 추론 요청 보낼 준비
            fig_items: list[tuple[int, int, Image.Image]] = []
            tab_items: list[tuple[int, int, Image.Image]] = []
            for page_idx, page_layout in enumerate(pages):
                page_image = page_images[page_idx]
                for block_idx, block in enumerate(page_layout.blocks):
                    label = (block.label or "").lower()
                    crop = _get_crop(block, page_image)
                    if crop is None:
                        continue
                    if label in _TAB_LABELS:
                        tab_items.append((page_idx, block_idx, crop))
                    elif label in _FIG_LABELS:
                        fig_items.append((page_idx, block_idx, crop))
            groups = [(block_type, items) for block_type, items in (("fig", fig_items), ("tab", tab_items)) if items]

            def _infer_group(group: tuple[str, list[tuple[int, int, Image.Image]]]):
                block_type, items = group
                return items, infer_stage2(
                    server_url, block_type, [crop for _, _, crop in items], ssl=ssl,
                    token=token, timeout_seconds=timeout_seconds, max_batch_size=max_batch_size,
                )

            levels_by_position: dict[tuple[int, int], int] = {}
            try:
                if groups:
                    with ThreadPoolExecutor(max_workers=len(groups)) as executor:
                        for items, levels in executor.map(_infer_group, groups):
                            if len(levels) != len(items):
                                raise RuntimeError("stage2 router response count does not match block count " f"({len(levels)} != {len(items)})")
                            invalid_levels = [level for level in levels if level not in {1, 2, 3}]
                            if invalid_levels:
                                raise ValueError(f"stage2 router returned unsupported levels: {invalid_levels!r}")
                            for (page_idx, block_idx, _), level in zip(items, levels):
                                levels_by_position[(page_idx, block_idx)] = level
            finally:
                for _, _, crop in fig_items + tab_items:
                    crop.close()
        except Exception as exc:
            append_router_records(context, "stage2_report.jsonl", [
                {"document_id": item.page.document_id, "page_no": item.page.page_no,
                 "status": "failed"} for item in pages
            ])
            for page_layout in pages:
                record_page_failure(page_layout.page, "stage2_router", exc)
            return NodeResult(value=value, metadata={"failed_pages": len(pages), "error": str(exc)})
        finally:
            for page_image in page_images:
                if page_image is not None:
                    page_image.close()

        classes_dir = Path(route_report_path).parent / "stage1_classes" / "level2" if route_report_path else None

        report_entries: list[dict] = []
        annotated_pages = []
        for page_idx, page_layout in enumerate(pages):
            page = page_layout.page
            stage1_level = page.metadata.get("stage1_level")
            if classes_dir and page.pdf_artifact:
                src = Path(page.pdf_artifact.path)
                if src.exists():
                    classes_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, classes_dir / src.name)

            new_blocks = []
            routed: list[str] = []
            for block_idx, block in enumerate(page_layout.blocks):
                stage2_level = levels_by_position.get((page_idx, block_idx))
                annotated = (
                    dataclasses.replace(block, metadata={**block.metadata, "stage2_level": stage2_level})
                    if stage2_level is not None
                    else block
                )
                new_blocks.append(annotated)
                if stage2_level is not None:
                    routed.append(f"r{block.reading_order}({block.label})→L{stage2_level}")
                # 크롭 파일이 있는 블록만 기록
                crop_path = block.crop_artifact.path if block.crop_artifact else None
                report_entries.append({
                    "document_id":   page.document_id,
                    "page_no":       page.page_no,
                    "block_id":      block.block_id,
                    "reading_order": block.reading_order,
                    "label":         block.label,
                    "bbox":          list(block.bbox) if block.bbox else None,
                    "page_width":    page_layout.page.width,
                    "page_height":   page_layout.page.height,
                    "crop_file":     os.path.basename(crop_path) if crop_path else None,
                    "crop_path":     crop_path,
                    "stage1_level":  stage1_level,
                    "stage1_class":  "level2",
                    "stage2_level":  stage2_level,
                })

            if routed:
                pass
                # print(f"  [Stage2] {page.document_id} p{page.page_no:03d}: {' | '.join(routed)}")

            annotated_pages.append(PageLayoutDTO(page=page, blocks=new_blocks))

        append_router_records(context, "stage2_report.jsonl", [
            {"document_id": item.page.document_id, "page_no": item.page.page_no,
             "status": "ok", "blocks": [
                 {"block_id": block.block_id, "label": block.label,
                  "stage2_level": block.metadata.get("stage2_level")}
                 for block in item.blocks
                 if (block.label or "").lower() in _TAB_LABELS | _FIG_LABELS
             ]} for item in annotated_pages
        ])
        if route_report_path and report_entries:
            append_jsonl(route_report_path, report_entries)

        out = annotated_pages[0] if not isinstance(value, list) else annotated_pages
        return NodeResult(value=out, metadata={"route_report_path": route_report_path})


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
