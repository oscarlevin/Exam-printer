"""Tests for exam_printer.py"""

import io
import csv
import sys
import tempfile
from pathlib import Path

import pytest
import pypdf
from reportlab.pdfgen import canvas as rl_canvas

# Ensure the repo root is on the path when running pytest directly
sys.path.insert(0, str(Path(__file__).parent))
from exam_printer import (
    read_csv,
    build_student_pdf,
    _cover_overlay_pdf,
    _page_size,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf(num_pages: int, page_width: float = 612, page_height: float = 792) -> bytes:
    """Return a minimal PDF with *num_pages* pages, each containing a page number."""
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(page_width, page_height))
    for i in range(num_pages):
        c.setFont("Helvetica", 12)
        c.drawString(50, page_height - 50, f"Page {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def _write_csv(tmp_path: Path, rows: list[list[str]]) -> Path:
    """Write *rows* to a CSV file and return its path."""
    p = tmp_path / "scores.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for row in rows:
            writer.writerow(row)
    return p


# ---------------------------------------------------------------------------
# read_csv
# ---------------------------------------------------------------------------

class TestReadCsv:
    def test_basic(self, tmp_path):
        csv_path = _write_csv(tmp_path, [
            ["Name", "LT1", "LT2"],
            ["Alice", "4", "3"],
            ["Bob", "2", "4"],
        ])
        lts, students = read_csv(csv_path)
        assert lts == ["LT1", "LT2"]
        assert len(students) == 2
        assert students[0]["name"] == "Alice"
        assert students[0]["scores"] == {"LT1": 4, "LT2": 3}
        assert students[1]["name"] == "Bob"
        assert students[1]["scores"] == {"LT1": 2, "LT2": 4}

    def test_skips_blank_lines(self, tmp_path):
        csv_path = _write_csv(tmp_path, [
            ["Name", "LT1"],
            ["Alice", "3"],
            ["", ""],      # blank name → should be skipped
            ["Bob", "4"],
        ])
        _, students = read_csv(csv_path)
        assert len(students) == 2

    def test_missing_score_defaults_to_zero(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, [
            ["Name", "LT1", "LT2"],
            ["Alice", "4"],  # LT2 missing
        ])
        _, students = read_csv(csv_path)
        assert students[0]["scores"]["LT2"] == 0

    def test_non_numeric_score_defaults_to_zero(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, [
            ["Name", "LT1"],
            ["Alice", "N/A"],
        ])
        _, students = read_csv(csv_path)
        assert students[0]["scores"]["LT1"] == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_header_only_raises(self, tmp_path):
        csv_path = _write_csv(tmp_path, [["Name"]])
        with pytest.raises(SystemExit):
            read_csv(csv_path)


# ---------------------------------------------------------------------------
# Overlay helpers
# ---------------------------------------------------------------------------

class TestOverlayHelpers:
    def test_cover_overlay_is_one_page(self):
        reader = _cover_overlay_pdf(
            612, 792, "Test Student",
            ["LT1", "LT2", "LT3"],
            {"LT1": 4, "LT2": 3, "LT3": 2},
        )
        assert len(reader.pages) == 1

    def test_cover_overlay_all_expertise(self):
        reader = _cover_overlay_pdf(
            612, 792, "Test Student",
            ["LT1", "LT2"],
            {"LT1": 4, "LT2": 4},
        )
        assert len(reader.pages) == 1

    def test_page_size(self):
        pdf_bytes = _make_pdf(1, 612, 792)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        w, h = _page_size(reader.pages[0])
        assert abs(w - 612) < 1
        assert abs(h - 792) < 1


# ---------------------------------------------------------------------------
# build_student_pdf
# ---------------------------------------------------------------------------

class TestBuildStudentPdf:
    def _setup(self, tmp_path, num_lt_pages=3):
        """Create a reader with a cover + *num_lt_pages* LT pages."""
        pdf_bytes = _make_pdf(1 + num_lt_pages)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        lts = [f"LT{i+1}" for i in range(num_lt_pages)]
        return reader, lts

    def test_expertise_on_all_has_cover_only(self, tmp_path):
        reader, lts = self._setup(tmp_path, 3)
        student = {"name": "Alice", "scores": {"LT1": 4, "LT2": 4, "LT3": 4}}
        writer = build_student_pdf(reader, lts, student)
        # cover + forced blank after cover = 2
        assert len(writer.pages) == 2

    def test_below_mastery_includes_lt_page(self, tmp_path):
        reader, lts = self._setup(tmp_path, 3)
        student = {"name": "Bob", "scores": {"LT1": 2, "LT2": 4, "LT3": 4}}
        writer = build_student_pdf(reader, lts, student)
        # cover + forced blank + LT1 + trailing blank (odd LT count) = 4
        assert len(writer.pages) == 4

    def test_at_mastery_includes_lt_page(self, tmp_path):
        reader, lts = self._setup(tmp_path, 3)
        student = {"name": "Carol", "scores": {"LT1": 3, "LT2": 4, "LT3": 4}}
        writer = build_student_pdf(reader, lts, student)
        # cover + forced blank + LT1 + trailing blank (odd LT count) = 4
        assert len(writer.pages) == 4

    def test_all_below_mastery_includes_all_lt_pages(self, tmp_path):
        reader, lts = self._setup(tmp_path, 3)
        student = {"name": "Dave", "scores": {"LT1": 1, "LT2": 2, "LT3": 0}}
        writer = build_student_pdf(reader, lts, student)
        # cover + forced blank + 3 LT pages + trailing blank (odd LT count) = 6
        assert len(writer.pages) == 6

    def test_mixed_scores(self, tmp_path):
        reader, lts = self._setup(tmp_path, 4)
        # LT1=4 (skip), LT2=3 (include), LT3=2 (include), LT4=4 (skip)
        student = {"name": "Eve", "scores": {"LT1": 4, "LT2": 3, "LT3": 2, "LT4": 4}}
        writer = build_student_pdf(reader, lts, student)
        # cover + forced blank + 2 LT pages = 4
        assert len(writer.pages) == 4


# ---------------------------------------------------------------------------
# main() integration test
# ---------------------------------------------------------------------------

class TestMain:
    def test_end_to_end(self, tmp_path):
        # Build a 5-page PDF: cover + 4 LT pages
        pdf_bytes = _make_pdf(5)
        pdf_path = tmp_path / "exam.pdf"
        pdf_path.write_bytes(pdf_bytes)

        csv_path = _write_csv(tmp_path, [
            ["Name", "LT1", "LT2", "LT3", "LT4"],
            ["Alice", "4", "3", "2", "4"],  # include LT2, LT3 → 2 LT pages
            ["Bob",   "2", "4", "4", "3"],  # include LT1, LT4 → 2 LT pages
        ])
        output_path = tmp_path / "output.pdf"

        main([str(pdf_path), str(csv_path), "-o", str(output_path)])

        assert output_path.exists()
        reader = pypdf.PdfReader(str(output_path))
        # Alice: cover + forced blank + 2 LT pages = 4
        # Bob:   cover + forced blank + 2 LT pages = 4
        # total = 8
        assert len(reader.pages) == 8

    def test_missing_pdf_exits(self, tmp_path):
        csv_path = _write_csv(tmp_path, [["Name", "LT1"], ["Alice", "4"]])
        with pytest.raises(SystemExit):
            main([str(tmp_path / "nonexistent.pdf"), str(csv_path)])

    def test_missing_csv_exits(self, tmp_path):
        pdf_bytes = _make_pdf(2)
        pdf_path = tmp_path / "exam.pdf"
        pdf_path.write_bytes(pdf_bytes)
        with pytest.raises(SystemExit):
            main([str(pdf_path), str(tmp_path / "nonexistent.csv")])
