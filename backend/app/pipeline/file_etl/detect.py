"""Detect file format from extension."""

from __future__ import annotations

from pathlib import PurePosixPath

FORMAT_MAP: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".xls": "xlsx",
    ".csv": "csv",
    ".tsv": "csv",
    ".json": "json",
    ".jsonl": "json",
    ".txt": "text",
    ".md": "text",
    ".html": "html",
    ".htm": "html",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".bmp": "image",
}

TEXT_FORMATS = {"csv", "json", "text"}


def detect_format(filename: str) -> str | None:
    ext = PurePosixPath(filename).suffix.lower()
    return FORMAT_MAP.get(ext)


def is_text_format(fmt: str) -> bool:
    return fmt in TEXT_FORMATS
