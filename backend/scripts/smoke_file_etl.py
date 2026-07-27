"""Smoke test for file_etl package — validates imports, detection, and text-format extraction."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.file_etl.detect import detect_format, is_text_format
from app.pipeline.file_etl.types import ExtractedDocument, ExtractionStats, TableBlock, ImageNote
from app.pipeline.file_etl.extract import extract_file


def test_detect():
    cases = {
        "report.pdf": "pdf",
        "data.xlsx": "xlsx",
        "catalog.docx": "docx",
        "slides.pptx": "pptx",
        "photo.png": "image",
        "photo.JPG": "image",
        "page.html": "html",
        "data.csv": "csv",
        "notes.txt": "text",
        "data.json": "json",
        "readme.md": "text",
        "unknown.xyz": None,
    }
    for name, expected in cases.items():
        result = detect_format(name)
        assert result == expected, f"detect({name}) = {result}, expected {expected}"
    print("  detect_format: OK")


def test_text_format():
    assert is_text_format("csv")
    assert is_text_format("json")
    assert is_text_format("text")
    assert not is_text_format("pdf")
    assert not is_text_format("image")
    print("  is_text_format: OK")


def test_text_extract():
    csv_content = b"name,price,description\nWidget,100,A good widget\n"
    progress: list[str] = []
    doc = extract_file(csv_content, "products.csv", on_progress=progress.append)
    assert doc.format == "csv"
    assert "Widget" in doc.text
    assert len(progress) >= 1
    print(f"  text extract: OK (format={doc.format}, progress_msgs={len(progress)})")


def test_html_extract():
    html = b"""<html><body>
    <h1>Products</h1>
    <table><tr><th>Name</th><th>Price</th></tr>
    <tr><td>Widget</td><td>99</td></tr></table>
    </body></html>"""
    progress: list[str] = []
    doc = extract_file(html, "catalog.html", on_progress=progress.append)
    assert doc.format == "html"
    assert len(doc.tables) == 1
    assert "Widget" in doc.tables[0].content
    print(f"  html extract: OK (tables={len(doc.tables)}, progress_msgs={len(progress)})")


def test_prompt_text():
    doc = ExtractedDocument(
        source_name="test",
        format="test",
        text="Main body",
        tables=[TableBlock(label="T1", content="| a | b |")],
        image_notes=[ImageNote(label="img1", description="A product photo")],
    )
    prompt = doc.to_prompt_text()
    assert "Main body" in prompt
    assert "Table: T1" in prompt
    assert "Image: img1" in prompt
    print("  to_prompt_text: OK")


def test_unsupported():
    try:
        extract_file(b"data", "file.xyz")
        assert False, "Should have raised"
    except ValueError as e:
        assert "Unsupported" in str(e)
    print("  unsupported format error: OK")


if __name__ == "__main__":
    print("Running file_etl smoke tests…")
    test_detect()
    test_text_format()
    test_text_extract()
    test_html_extract()
    test_prompt_text()
    test_unsupported()
    print("\nAll smoke tests passed!")
