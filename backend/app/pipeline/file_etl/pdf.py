"""PDF extraction — text via PyMuPDF, tables via pdfplumber, images via vision."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from .types import ExtractionStats, ExtractedDocument, ImageNote, TableBlock
from .vision import MAX_IMAGES_PER_FILE, describe_image

if TYPE_CHECKING:
    from collections.abc import Callable


def extract_pdf(
    data: bytes,
    filename: str,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> ExtractedDocument:
    import fitz  # PyMuPDF
    import pdfplumber

    doc = fitz.open(stream=data, filetype="pdf")
    stats = ExtractionStats(pages=len(doc))
    if on_progress:
        on_progress(f"Detected PDF ({len(doc)} pages)")

    text_parts: list[str] = []
    images_to_describe: list[tuple[bytes, str, str]] = []

    for i, page in enumerate(doc):
        page_text = page.get_text("text") or ""
        text_parts.append(page_text)

        if len(images_to_describe) < MAX_IMAGES_PER_FILE:
            for img_info in page.get_images(full=True):
                if len(images_to_describe) >= MAX_IMAGES_PER_FILE:
                    stats.images_skipped += 1
                    continue
                xref = img_info[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.width < 80 or pix.height < 80:
                        continue
                    if pix.alpha:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    images_to_describe.append(
                        (pix.tobytes("png"), f"page_{i + 1}_img_{xref}", "image/png")
                    )
                except Exception:
                    pass

    doc.close()

    full_text = "\n".join(text_parts)
    if on_progress:
        on_progress(f"Extracted text from {stats.pages} pages")

    tables: list[TableBlock] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for pi, page in enumerate(pdf.pages):
                for ti, tbl in enumerate(page.extract_tables()):
                    if not tbl:
                        continue
                    header = tbl[0] if tbl else []
                    rows = tbl[1:] if len(tbl) > 1 else []
                    md_header = "| " + " | ".join(str(c or "") for c in header) + " |"
                    md_sep = "| " + " | ".join("---" for _ in header) + " |"
                    md_rows = "\n".join(
                        "| " + " | ".join(str(c or "") for c in row) + " |" for row in rows
                    )
                    md = f"{md_header}\n{md_sep}\n{md_rows}"
                    tables.append(TableBlock(label=f"Page {pi + 1}, Table {ti + 1}", content=md))
    except Exception:
        pass

    if tables and on_progress:
        on_progress(f"Found {len(tables)} table(s)")
    stats.tables_found = len(tables)

    image_notes: list[ImageNote] = []
    if images_to_describe and on_progress:
        on_progress(f"Describing {len(images_to_describe)} image(s) via vision…")
    for img_bytes, label, mime in images_to_describe:
        try:
            desc = describe_image(img_bytes, mime=mime, context=f"From {filename}, {label}")
            image_notes.append(ImageNote(label=label, description=desc))
            stats.images_processed += 1
        except Exception:
            stats.images_skipped += 1

    return ExtractedDocument(
        source_name=filename,
        format="pdf",
        text=full_text,
        tables=tables,
        image_notes=image_notes,
        stats=stats,
    )
