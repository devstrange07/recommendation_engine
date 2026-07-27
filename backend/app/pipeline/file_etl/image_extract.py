"""Standalone image extraction via vision."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from .types import ExtractionStats, ExtractedDocument, ImageNote
from .vision import describe_image

if TYPE_CHECKING:
    from collections.abc import Callable

MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


def extract_image(
    data: bytes,
    filename: str,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> ExtractedDocument:
    ext = PurePosixPath(filename).suffix.lower()
    mime = MIME_MAP.get(ext, "image/png")
    stats = ExtractionStats(images_processed=1)

    if on_progress:
        on_progress(f"Describing image via vision…")

    desc = describe_image(data, mime=mime, context=f"Product catalog image: {filename}")
    note = ImageNote(label=filename, description=desc)

    return ExtractedDocument(
        source_name=filename,
        format="image",
        text="",
        image_notes=[note],
        stats=stats,
    )
