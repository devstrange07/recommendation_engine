"""Shared types for file ETL extraction."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TableBlock:
    label: str
    content: str  # markdown or CSV-formatted table


@dataclass
class ImageNote:
    label: str
    description: str  # vision-generated caption


@dataclass
class ExtractionStats:
    pages: int = 0
    sheets: int = 0
    tables_found: int = 0
    images_processed: int = 0
    images_skipped: int = 0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class ExtractedDocument:
    source_name: str
    format: str
    text: str = ""
    tables: list[TableBlock] = field(default_factory=list)
    image_notes: list[ImageNote] = field(default_factory=list)
    stats: ExtractionStats = field(default_factory=ExtractionStats)

    def to_prompt_text(self) -> str:
        """Concatenate all extracted content into a single prompt-ready string."""
        parts = []
        if self.text.strip():
            parts.append(self.text.strip())
        for tbl in self.tables:
            parts.append(f"\n--- Table: {tbl.label} ---\n{tbl.content}")
        for img in self.image_notes:
            parts.append(f"\n--- Image: {img.label} ---\n{img.description}")
        return "\n\n".join(parts)
