# Exam-printer

A Python utility that takes a master exam PDF and a CSV file of student scores on
learning targets, and produces a single print-ready PDF with a personalised exam
for every student.

## What it does

For each student the script:

1. **Stamps the student's name** on the cover page of the exam.
2. **Inserts a summary page** listing which learning targets they haven't yet
   reached mastery on (score ≤ 2) and which they're at mastery but not yet
   expertise on (score = 3).
3. **Includes only the exam pages** for learning targets they don't yet have
   *expertise* on (i.e. score < 4).  Learning targets scored 4 are omitted.
4. Concatenates all per-student PDFs into **one output file** that can be
   printed and stapled in one pass.

### Scoring key

| Score | Meaning                      |
|-------|------------------------------|
| ≤ 2   | Below mastery                |
| 3     | At mastery (not expertise)   |
| 4     | At expertise — page excluded |

---

## PDF layout assumption

The master exam PDF must follow this layout:

| Page   | Content                          |
|--------|----------------------------------|
| 1      | Cover page                       |
| 2      | Learning target 1 (LT1)          |
| 3      | Learning target 2 (LT2)          |
| …      | …                                |
| N + 1  | Learning target N (LTN)          |

The learning targets are matched **in order** to the columns in the CSV file.

---

## CSV format

The CSV must have a **header row**.  The first column is the student name; every
subsequent column is a learning target name.  One data row per student.

```csv
Name,LT1 - Limits,LT2 - Derivatives,LT3 - Integrals,LT4 - Applications
Alice Smith,4,3,2,4
Bob Jones,2,4,3,1
```

A sample file is provided as `sample_scores.csv`.

---

## Requirements

- Python 3.9+
- [pypdf](https://pypdf.readthedocs.io/) ≥ 5.0
- [reportlab](https://www.reportlab.com/dev/install/open-source/) ≥ 4.0

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Usage

```
python exam_printer.py EXAM.pdf SCORES.csv [-o OUTPUT.pdf]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `EXAM.pdf` | Master exam PDF (cover page + one page per learning target) |
| `SCORES.csv` | CSV file with student names and learning-target scores |
| `-o OUTPUT.pdf` | Output path (default: `output.pdf` next to `EXAM.pdf`) |

### Example

```bash
python exam_printer.py final_exam.pdf class_scores.csv -o print_ready.pdf
```

---

## Running the tests

```bash
pip install pytest
pytest test_exam_printer.py -v
```
