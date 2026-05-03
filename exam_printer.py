#!/usr/bin/env python3
"""exam_printer.py – Build personalised exam PDFs from a master PDF and a CSV of scores.

CSV format
----------
The first row must be a header row. The first column is ignored (it is treated as
the student-name label). Every subsequent column header is the name of a learning
target (LT), and those names must correspond, **in order**, to the exam pages that
follow the cover page.

Example::

    Name,LT1,LT2,LT3
    Alice,4,3,2
    Bob,2,4,3

Scoring key
-----------
* ≤ 2  – below mastery
*   3  – at mastery (but not yet at expertise)
*   4  – at expertise

PDF layout assumptions
----------------------
* Page 1 (index 0): cover page – the student's name is stamped on it.
* Pages 2 … N+1 (indices 1 … N): one page per learning target, in the same order as
  the CSV columns.

Output
------
A single PDF whose pages are the concatenation of all per-student PDFs in the order
they appear in the CSV, ready to print-and-staple.
"""

import argparse
import csv
import io
import sys
from pathlib import Path

import pypdf
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas

# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def read_csv(csv_path: Path):
    """Return (learning_targets, students).

    learning_targets – list of LT names (from the header row, columns 1+)
    students         – list of dicts with keys 'name' and 'scores'
                       where scores maps LT name → int score
    """
    students = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        if len(header) < 2:
            sys.exit(
                f"ERROR: CSV header must have at least 2 columns "
                f"(student name + at least one learning target).  Got: {header}"
            )
        learning_targets = [col.strip() for col in header[1:]]
        for row_num, row in enumerate(reader, start=2):
            if not row or not row[0].strip():
                continue  # skip blank lines
            name = row[0].strip()
            scores: dict[str, int] = {}
            for i, lt in enumerate(learning_targets):
                raw = row[i + 1].strip() if i + 1 < len(row) else ""
                try:
                    scores[lt] = int(raw)
                except ValueError:
                    print(
                        f"WARNING: row {row_num}, column {i + 2}: "
                        f"cannot parse score {raw!r} for {name!r} / {lt!r}; treating as 0."
                    )
                    scores[lt] = 0
            students.append({"name": name, "scores": scores})
    return learning_targets, students


# ---------------------------------------------------------------------------
# ReportLab overlay helpers
# ---------------------------------------------------------------------------

def _page_size(pdf_page) -> tuple[float, float]:
    """Return (width, height) in points for a pypdf page."""
    box = pdf_page.mediabox
    return float(box.width), float(box.height)


def _name_overlay_pdf(width: float, height: float, student_name: str) -> pypdf.PdfReader:
    """Return a single-page PDF reader whose page contains only the student name."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(colors.black)
    # Place name in the upper-left area of the cover
    c.drawString(50, height - 60, student_name)
    c.save()
    buf.seek(0)
    return pypdf.PdfReader(buf)


def _summary_page_pdf(
    width: float,
    height: float,
    student_name: str,
    learning_targets: list[str],
    scores: dict[str, int],
) -> pypdf.PdfReader:
    """Return a single-page PDF reader that lists the student's LT statuses."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))

    margin = 50
    y = height - margin

    # Title
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin, y, f"Learning Target Status — {student_name}")
    y -= 30

    # Categorise
    below_mastery = [lt for lt in learning_targets if scores.get(lt, 0) <= 2]
    at_mastery = [lt for lt in learning_targets if scores.get(lt, 0) == 3]

    def section(title: str, items: list[str]) -> None:
        nonlocal y
        if not items:
            return
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, y, title)
        y -= 18
        c.setFont("Helvetica", 11)
        for item in items:
            if y < margin + 20:
                c.showPage()
                y = height - margin
                c.setFont("Helvetica", 11)
            c.drawString(margin + 15, y, f"\u2022  {item}")
            y -= 16
        y -= 10  # extra gap between sections

    section("Not yet at mastery (score \u2264 2):", below_mastery)
    section("At mastery, not yet at expertise (score = 3):", at_mastery)

    if not below_mastery and not at_mastery:
        c.setFont("Helvetica", 11)
        c.drawString(margin, y, "All learning targets achieved at expertise level. Congratulations!")

    c.save()
    buf.seek(0)
    return pypdf.PdfReader(buf)


# ---------------------------------------------------------------------------
# Per-student PDF builder
# ---------------------------------------------------------------------------

def build_student_pdf(
    pdf_reader: pypdf.PdfReader,
    learning_targets: list[str],
    student: dict,
) -> pypdf.PdfWriter:
    """Return a PdfWriter containing the personalised exam for *student*."""
    writer = pypdf.PdfWriter()
    name: str = student["name"]
    scores: dict[str, int] = student["scores"]

    # ---- Cover page (index 0) with student name stamped on it ---------------
    if len(pdf_reader.pages) == 0:
        sys.exit("ERROR: the input PDF contains no pages.")

    cover = pdf_reader.pages[0]
    w, h = _page_size(cover)

    overlay_reader = _name_overlay_pdf(w, h, name)
    cover_copy = pypdf.PageObject.create_blank_page(width=w, height=h)
    cover_copy.merge_page(cover)
    cover_copy.merge_page(overlay_reader.pages[0])
    writer.add_page(cover_copy)

    # ---- Summary page -------------------------------------------------------
    summary_reader = _summary_page_pdf(w, h, name, learning_targets, scores)
    for pg in summary_reader.pages:
        writer.add_page(pg)

    # ---- Learning-target pages (score < 4 → include) -----------------------
    for i, lt in enumerate(learning_targets):
        score = scores.get(lt, 0)
        if score < 4:
            page_idx = i + 1  # index 0 is the cover
            if page_idx < len(pdf_reader.pages):
                writer.add_page(pdf_reader.pages[page_idx])
            else:
                print(
                    f"WARNING: no page found for learning target {lt!r} "
                    f"(expected page index {page_idx}); skipping."
                )

    return writer


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create personalised exam PDFs from a master PDF and a CSV of scores, "
            "then combine them into a single print-ready file."
        )
    )
    parser.add_argument(
        "pdf",
        metavar="EXAM.pdf",
        help=(
            "Master exam PDF.  Page 1 is the cover page; pages 2‒N+1 correspond to "
            "the N learning-target columns in the CSV (in order)."
        ),
    )
    parser.add_argument(
        "csv",
        metavar="SCORES.csv",
        help=(
            "CSV file with a header row (student-name column + one column per LT) "
            "and one data row per student."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="OUTPUT.pdf",
        default=None,
        help="Path for the combined output PDF (default: output.pdf in the same directory as EXAM.pdf).",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)

    pdf_path = Path(args.pdf)
    csv_path = Path(args.csv)

    if not pdf_path.is_file():
        sys.exit(f"ERROR: PDF not found: {pdf_path}")
    if not csv_path.is_file():
        sys.exit(f"ERROR: CSV not found: {csv_path}")

    output_path = Path(args.output) if args.output else pdf_path.parent / "output.pdf"

    pdf_reader = pypdf.PdfReader(str(pdf_path))
    learning_targets, students = read_csv(csv_path)

    if not students:
        sys.exit("ERROR: no student rows found in CSV.")

    # Warn if the PDF doesn't have enough pages
    expected_pages = len(learning_targets) + 1  # cover + one per LT
    actual_pages = len(pdf_reader.pages)
    if actual_pages < expected_pages:
        print(
            f"WARNING: PDF has {actual_pages} page(s) but {len(learning_targets)} learning "
            f"target(s) were found in the CSV (expected {expected_pages} pages: 1 cover + "
            f"{len(learning_targets)} LT pages).  Some LT pages will be missing."
        )

    combined_writer = pypdf.PdfWriter()

    for student in students:
        student_writer = build_student_pdf(pdf_reader, learning_targets, student)
        for page in student_writer.pages:
            combined_writer.add_page(page)
        print(f"  Processed: {student['name']}")

    with open(output_path, "wb") as fh:
        combined_writer.write(fh)

    print(f"\nDone.  Output written to: {output_path}")
    print(f"Total pages: {len(combined_writer.pages)}")


if __name__ == "__main__":
    main()
