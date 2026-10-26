from __future__ import annotations

import pytest
from src.qa_sets.utils import ExportFormat, ExportRow, parse_import, render_export

ROWS = [
    ExportRow(
        question='Penalty, "per day"?',
        answer="0.1%, capped at 10%",
        gold_files=["a.pdf", "sha256:" + "ab" * 32],
        tags=["penalty", "contract"],
        answerable=True,
    ),
    ExportRow(
        question="Out of scope?",
        answer=None,
        gold_files=[],
        tags=[],
        answerable=False,
    ),
]


@pytest.mark.parametrize("export_format", list(ExportFormat))
def test_an_export_reads_back_as_the_same_rows(export_format) -> None:
    content, _ = render_export(ROWS, export_format)

    parsed = parse_import(f"export.{export_format.value}", content.encode())

    assert [
        (row.question, row.answer, row.gold_files, row.tags, row.answerable, row.error)
        for row in parsed
    ] == [
        (
            'Penalty, "per day"?',
            "0.1%, capped at 10%",
            ["a.pdf", "sha256:" + "ab" * 32],
            ["penalty", "contract"],
            True,
            None,
        ),
        ("Out of scope?", None, [], [], False, None),
    ]


def test_the_csv_header_follows_the_import_columns() -> None:
    content, media_type = render_export([], ExportFormat.CSV)

    assert content == "question,answer,gold_files,tags,answerable\n"
    assert media_type == "text/csv"
