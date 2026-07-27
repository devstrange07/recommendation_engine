"""HTML extraction — reuse existing BeautifulSoup cleaning."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .types import ExtractionStats, ExtractedDocument, TableBlock

if TYPE_CHECKING:
    from collections.abc import Callable


def extract_html(
    data: bytes,
    filename: str,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> ExtractedDocument:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    if on_progress:
        on_progress(f"Extracted text from HTML ({len(text)} chars)")

    tables: list[TableBlock] = []
    for ti, tbl in enumerate(soup.find_all("table")):
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if not rows:
            continue
        header = rows[0]
        md_header = "| " + " | ".join(header) + " |"
        md_sep = "| " + " | ".join("---" for _ in header) + " |"
        md_rows = "\n".join("| " + " | ".join(r) + " |" for r in rows[1:])
        tables.append(TableBlock(label=f"Table {ti + 1}", content=f"{md_header}\n{md_sep}\n{md_rows}"))

    if tables and on_progress:
        on_progress(f"Found {len(tables)} table(s) in HTML")

    return ExtractedDocument(
        source_name=filename,
        format="html",
        text=text,
        tables=tables,
        stats=ExtractionStats(tables_found=len(tables)),
    )
