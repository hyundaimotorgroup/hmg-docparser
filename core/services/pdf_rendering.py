from __future__ import annotations

import math
from contextlib import closing
from pathlib import Path
from threading import RLock

import pypdfium2 as pdfium
from PIL import Image


# PDFium calls must be serialized even when operating on different documents.
# Keep provider requests outside this lock so page processing can remain parallel.
_PDFIUM_LOCK = RLock()


def _render_page(document, page_index: int, *, dpi: int, target_size: int | None) -> Image.Image:
    with closing(document[page_index]) as page:
        width, height = page.get_size()
        scale = target_size / max(width, height) if target_size is not None else dpi / 72
        with closing(page.render(
            scale=scale,
            rev_byteorder=True,
            prefer_bgrx=True,
            fill_color=(255, 255, 255, 255),
            draw_annots=True,
            may_draw_forms=True,
        )) as bitmap:
            # RGB conversion allocates independent storage before the bitmap closes.
            image = bitmap.to_pil().convert("RGB")
        if target_size is None:
            image.info["dpi"] = (dpi, dpi)
        return image


def _validate_size(dpi: int, target_size: int | None) -> None:
    value = dpi if target_size is None else target_size
    if not math.isfinite(value) or value <= 0:
        raise ValueError("PDF rendering size must be finite and positive")


def render_pdf_page(
    pdf_path: str | Path,
    *,
    page_index: int = 0,
    dpi: int = 300,
    target_size: int | None = None,
    require_single_page: bool = False,
) -> Image.Image:
    """Render a detached RGB image using the page's rotation and CropBox."""
    _validate_size(dpi, target_size)
    with _PDFIUM_LOCK, closing(pdfium.PdfDocument(str(pdf_path))) as document:
        if require_single_page and len(document) != 1:
            raise ValueError(f"page input must be a single-page PDF: {pdf_path}")
        if not 0 <= page_index < len(document):
            raise IndexError(f"PDF page index out of range: {page_index}")
        document.init_forms()
        return _render_page(document, page_index, dpi=dpi, target_size=target_size)


def render_pdf_pages(
    pdf_path: str | Path,
    *,
    dpi: int = 300,
    target_size: int | None = None,
) -> list[Image.Image]:
    """Render all pages; close any completed images if a later page fails."""
    _validate_size(dpi, target_size)
    images: list[Image.Image] = []
    try:
        with _PDFIUM_LOCK, closing(pdfium.PdfDocument(str(pdf_path))) as document:
            document.init_forms()
            for index in range(len(document)):
                images.append(_render_page(document, index, dpi=dpi, target_size=target_size))
        return images
    except Exception:
        for image in images:
            image.close()
        raise


def pdf_has_images(pdf_path: str | Path, *, page_index: int | None = None) -> bool:
    """Check drawn raster images, including inline images and nested forms."""
    with _PDFIUM_LOCK, closing(pdfium.PdfDocument(str(pdf_path))) as document:
        indexes = range(len(document)) if page_index is None else [page_index]
        for index in indexes:
            with closing(document[index]) as page:
                if any(page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE], max_depth=64)):
                    return True
    return False
