from __future__ import annotations

import time as _time
from dataclasses import replace
from pathlib import Path

from PIL import Image

from core.adapters.router_infer import infer_stage1
from core.domain.document.models import PageDTO
from core.interfaces.node import Node, NodeContext, NodeResult
from core.services.page_failures import record_page_failure
from core.observability.router_reports import append_router_records
from core.services.pdf_rendering import render_pdf_page


def _render_page(page: PageDTO, dpi: int = 150) -> Image.Image:
    return render_pdf_page(Path(page.pdf_artifact.path), dpi=dpi)


class Stage1PageRouterNode(Node):
    node_name = "stage1_page_router"
    input_type = "page_dto@v1"
    output_type = "page_dto@v1"

    def run(self, context: NodeContext, value: object) -> NodeResult:
        if not context.config.get("enabled", True):
            return NodeResult(value=value, metadata={"skipped": True})

        pages: list[PageDTO] = value if isinstance(value, list) else [value]
        if not all(isinstance(page, PageDTO) for page in pages):
            raise TypeError("stage1_page_router expects PageDTO or list[PageDTO]")
        server_url = context.config.get("server_url", "")
        if not server_url:
            # 추론 서버 주소가 없으면 통과 (라우팅 없이 전체 처리)
            return NodeResult(value=value, metadata={"skipped": True, "reason": "no server_url"})

        t0 = _time.time()
        images: list[Image.Image] = []
        try:
            images = [_render_page(page) for page in pages]
            levels = infer_stage1(
                server_url,
                images,
                ssl=bool(context.config.get("ssl", False)),
                token=context.config.get("token"),
                timeout_seconds=context.config.get("timeout_seconds"),
                max_batch_size=int(context.config.get("max_batch_size", 16)),
            )
            if len(levels) != len(pages):
                raise RuntimeError(
                    "stage1 router response count does not match page count "
                    f"({len(levels)} != {len(pages)})"
                )
            invalid_levels = [level for level in levels if level not in {1, 2}]
            if invalid_levels:
                raise ValueError(f"stage1 router returned unsupported levels: {invalid_levels!r}")
        except Exception as exc:
            append_router_records(context, "stage1_report.jsonl", [
                {"document_id": page.document_id, "page_no": page.page_no,
                 "status": "failed", "stage1_level": None}
                for page in pages
            ])
            for page in pages:
                record_page_failure(page, "stage1_router", exc)
            return NodeResult(
                value=value,
                metadata={"failed_pages": len(pages), "error": str(exc)},
            )
        finally:
            for image in images:
                image.close()
        elapsed = _time.time() - t0

        annotated = []
        level_counts: dict[int, int] = {}
        for page, level in zip(pages, levels):
            level_counts[level] = level_counts.get(level, 0) + 1
            annotated.append(replace(page, metadata={**page.metadata, "stage1_level": level}))

        append_router_records(context, "stage1_report.jsonl", [
            {"document_id": page.document_id, "page_no": page.page_no,
             "status": "ok", "stage1_level": level, "elapsed_seconds": elapsed}
            for page, level in zip(pages, levels)
        ])
        avg = elapsed / len(pages) if pages else 0
        # print(f"  [Stage1] 요약: " + " | ".join(f"L{lv}={cnt}" for lv, cnt in sorted(level_counts.items()))
        #       + f"  |  요청소요={elapsed*1000:.0f}ms  페이지당평균={avg*1000:.0f}ms")
        out = annotated[0] if not isinstance(value, list) else annotated
        return NodeResult(value=out, metadata={"level_counts": level_counts, "elapsed_seconds": elapsed, "average_seconds": avg})
