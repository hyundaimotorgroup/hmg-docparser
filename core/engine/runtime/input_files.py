from __future__ import annotations

import os
from pathlib import Path

from core.services.document_guard_service import DEFAULT_MAX_PDF_BYTES, assert_processable_document
from core.services.document_limits import DocumentLimits
from core.services.pdf_rendering import render_pdf_pages


def prepare_input_files(
    input_path,
    output_path,
    *,
    max_pdf_bytes: int = DEFAULT_MAX_PDF_BYTES,
    limits: DocumentLimits | None = None,
):
    pdf_page_dict = {}

    if not Path(input_path).exists():
        raise FileNotFoundError("input path does not exist; check input_dir or the input override")

    if os.path.isdir(input_path):
        file_list = [os.path.join(input_path, fname) for fname in os.listdir(input_path)]
    else:
        file_list = [input_path]

    output_path = Path(output_path)
    candidate_files = [
        f for f in file_list
        if os.path.isfile(f) and not (output_path / f"{Path(f).stem}.md").exists()
    ]

    file_list = []
    for f in candidate_files:
        assert_processable_document(f, max_pdf_bytes=max_pdf_bytes, limits=limits)
        file_list.append(f)

    for f in file_list:
        path = Path(f)
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader

            with path.open("rb") as source:
                pdf_page_dict[path.stem] = len(PdfReader(source).pages)
        else:
            pdf_page_dict[path.stem] = 1

    return file_list, pdf_page_dict


def load_pdf_dolphin(pdf_path, target_size=896):
    try:
        return render_pdf_pages(pdf_path, target_size=target_size)
    except Exception as e:
        print(f"Error converting PDF to images: {str(e)}")
        return []


def pdf_to_pil_images(pdf_path, dpi=300):
    return render_pdf_pages(pdf_path, dpi=dpi)
