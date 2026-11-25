from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from PIL import Image

from core.domain.inference.models import OCRResultDTO
from core.domain.layout.models import LayoutBlockDTO, PageEnrichedDTO, PageLayoutDTO


def load_block_crop_images(page_layout: PageLayoutDTO) -> tuple[list[LayoutBlockDTO], list[Image.Image]]:
    target_blocks: list[LayoutBlockDTO] = []
    images: list[Image.Image] = []
    for block in page_layout.blocks:
        if block.crop_artifact is None:
            continue
        with Image.open(block.crop_artifact.path) as image:
            image.load()
            copy = image.copy()
        target_blocks.append(block)
        images.append(copy)
    return target_blocks, images


def apply_ocr_results_to_page_layout(
    page_layout: PageLayoutDTO,
    *,
    target_blocks: Sequence[LayoutBlockDTO],
    ocr_results: Sequence[OCRResultDTO],
    source_node_id: str | None = None,
    min_score: float = 0.9,
) -> PageEnrichedDTO:
    if len(target_blocks) != len(ocr_results):
        raise ValueError(
            "OCR target block count does not match OCR result count "
            f"({len(target_blocks)} != {len(ocr_results)})"
        )

    result_by_block_id = {
        block.block_id: result
        for block, result in zip(target_blocks, ocr_results)
    }
    enriched_blocks = [
        _apply_ocr_to_block(block, result_by_block_id.get(block.block_id), min_score=min_score)
        for block in page_layout.blocks
    ]
    return PageEnrichedDTO(
        page=page_layout.page,
        blocks=enriched_blocks,
        source_node_id=source_node_id,
    )


def _apply_ocr_to_block(
    block: LayoutBlockDTO,
    result: OCRResultDTO | None,
    *,
    min_score: float,
) -> LayoutBlockDTO:
    if result is None:
        return block

    accepted_lines = [
        line.text
        for line in result.lines
        if line.score is None or line.score >= min_score
    ]
    metadata = dict(block.metadata)
    metadata["ocr_line_count"] = len(result.lines)
    metadata["ocr_min_score"] = min_score
    if not accepted_lines:
        return replace(block, metadata=metadata)
    return replace(
        block,
        text="\n".join(accepted_lines),
        score=result.average_score or 0.0,
        metadata=metadata,
    )
