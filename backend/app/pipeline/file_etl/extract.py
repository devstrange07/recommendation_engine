"""Orchestrator — detect format, run extractor, emit progress, return ExtractedDocument."""

from __future__ import annotations

from collections.abc import Callable

from .detect import detect_format, is_text_format
from .types import ExtractedDocument, ExtractionStats


def extract_file(
    data: bytes,
    filename: str,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> ExtractedDocument:
    """Extract content from a binary file into a unified ExtractedDocument.

    For text-native formats (csv/json/txt) returns a minimal document with
    the raw text so the caller can use existing fast-path parsers.
    """
    fmt = detect_format(filename)
    if fmt is None:
        raise ValueError(f"Unsupported file type: {filename}")

    if on_progress:
        on_progress(f"Detected format: {fmt.upper()}")

    if is_text_format(fmt):
        text = data.decode("utf-8", errors="replace")
        return ExtractedDocument(
            source_name=filename,
            format=fmt,
            text=text,
            stats=ExtractionStats(),
        )

    if fmt == "pdf":
        from .pdf import extract_pdf
        return extract_pdf(data, filename, on_progress=on_progress)

    if fmt == "docx":
        from .docx_extract import extract_docx
        return extract_docx(data, filename, on_progress=on_progress)

    if fmt == "pptx":
        from .pptx_extract import extract_pptx
        return extract_pptx(data, filename, on_progress=on_progress)

    if fmt == "xlsx":
        from .xlsx_extract import extract_xlsx
        return extract_xlsx(data, filename, on_progress=on_progress)

    if fmt == "image":
        from .image_extract import extract_image
        return extract_image(data, filename, on_progress=on_progress)

    if fmt == "html":
        from .html_extract import extract_html
        return extract_html(data, filename, on_progress=on_progress)

    raise ValueError(f"Unsupported file type: {filename}")
