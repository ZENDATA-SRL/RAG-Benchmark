from __future__ import annotations

import csv
import dataclasses
import enum
import io
import json
import re
from typing import Any

from src.qa_sets.exceptions import InvalidImportFileError, UnsupportedImportFormatError

# Separator of the multi-valued CSV cells (`gold_files`, `tags`). A comma would collide with
# file names, and a semicolon with the delimiter some spreadsheets export.
LIST_SEPARATOR = "|"

_HASH_PATTERN = re.compile(r"^(?:sha256:)?([0-9a-fA-F]{64})$")
_TRUE_VALUES = {"true", "1", "yes", "y", "si", "sì"}
_FALSE_VALUES = {"false", "0", "no", "n"}


@dataclasses.dataclass(frozen=True)
class ImportRow:
    """One row of an import file, as read and before any file is resolved.

    `error` is set when the row itself is malformed; such a row is reported, never
    dropped.
    """

    row: int
    question: str
    gold_files: list[str]
    tags: list[str]
    answerable: bool
    answer: str | None = None
    error: str | None = None


class ExportFormat(str, enum.Enum):
    """File formats of an export: the same two the import reads."""

    CSV = "csv"
    JSONL = "jsonl"


# Columns of an exported CSV, in the order the import documents them.
EXPORT_COLUMNS = ("question", "answer", "gold_files", "tags", "answerable")


@dataclasses.dataclass(frozen=True)
class ExportRow:
    """One question as written to an export file."""

    question: str
    answer: str | None
    gold_files: list[str]
    tags: list[str]
    answerable: bool


def render_export(
    rows: list[ExportRow], export_format: ExportFormat
) -> tuple[str, str]:
    """Write rows in the format the import reads back, and return it with its media type.

    Lists are joined with the same separator the CSV import splits on; JSONL keeps them as
    arrays. A missing answer is an empty cell in a CSV and `null` in JSONL.
    """
    if export_format is ExportFormat.JSONL:
        lines = [
            json.dumps(
                {
                    "question": row.question,
                    "answer": row.answer,
                    "gold_files": row.gold_files,
                    "tags": row.tags,
                    "answerable": row.answerable,
                },
                ensure_ascii=False,
            )
            for row in rows
        ]
        return "".join(f"{line}\n" for line in lines), "application/x-ndjson"

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.question,
                row.answer or "",
                LIST_SEPARATOR.join(row.gold_files),
                LIST_SEPARATOR.join(row.tags),
                "true" if row.answerable else "false",
            ]
        )
    return buffer.getvalue(), "text/csv"


def content_hash_of(reference: str) -> str | None:
    """Return the sha-256 a gold file reference names, or `None` if it names a file.

    A reference that is 64 hex characters (optionally prefixed `sha256:`) is a content
    hash: file names are ambiguous across a corpus, hashes are not.
    """
    match = _HASH_PATTERN.match(reference.strip())
    return match.group(1).lower() if match else None


def parse_import(filename: str, data: bytes) -> list[ImportRow]:
    """Parse a CSV or JSONL import file into rows.

    Args:
        filename: Used only to pick the format from its extension.
        data: Raw file content, UTF-8.

    Returns:
        One row per record, in file order, numbered from 1 (the header of a CSV is not a
        record).

    Raises:
        UnsupportedImportFormatError: If the extension is neither `.csv` nor `.jsonl`.
        InvalidImportFileError: If the file is not UTF-8 or a CSV lacks the question column.
    """
    lowered = filename.lower()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InvalidImportFileError("the file is not UTF-8") from error
    if lowered.endswith(".csv"):
        return _parse_csv(text)
    if lowered.endswith((".jsonl", ".ndjson")):
        return _parse_jsonl(text)
    raise UnsupportedImportFormatError(filename)


def _parse_csv(text: str) -> list[ImportRow]:
    reader = csv.DictReader(io.StringIO(text))
    fields = {(name or "").strip().lower(): name for name in reader.fieldnames or []}
    if "question" not in fields:
        raise InvalidImportFileError("the CSV needs a `question` column")
    gold_column = fields.get("gold_files") or fields.get("gold_file")

    def cell(record: dict[str, Any], key: str | None) -> str:
        return (record.get(key) or "").strip() if key else ""

    rows = []
    for number, record in enumerate(reader, start=1):
        rows.append(
            _build_row(
                number,
                cell(record, fields["question"]),
                _split(cell(record, gold_column)),
                _split(cell(record, fields.get("tags"))),
                cell(record, fields.get("answerable")),
                cell(record, fields.get("answer")),
            )
        )
    return rows


def _parse_jsonl(text: str) -> list[ImportRow]:
    rows = []
    number = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        number += 1
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            rows.append(
                ImportRow(number, "", [], [], True, error=f"invalid JSON: {error.msg}")
            )
            continue
        if not isinstance(record, dict):
            rows.append(
                ImportRow(number, "", [], [], True, error="the line is not an object")
            )
            continue
        rows.append(
            _build_row(
                number,
                str(record.get("question") or "").strip(),
                _as_list(record.get("gold_files", record.get("gold_file"))),
                _as_list(record.get("tags")),
                record.get("answerable"),
                str(record.get("answer") or "").strip(),
            )
        )
    return rows


def _build_row(
    number: int,
    question: str,
    gold_files: list[str],
    tags: list[str],
    answerable: Any,
    answer: str,
) -> ImportRow:
    flag = _as_bool(answerable)
    row = ImportRow(
        number, question, gold_files, tags, bool(flag), answer=answer or None
    )
    if not question:
        return dataclasses.replace(row, answerable=True, error="empty question")
    if flag is None:
        return dataclasses.replace(
            row, answerable=True, error=f"invalid answerable: {answerable!r}"
        )
    if flag and not gold_files:
        return dataclasses.replace(row, error="an answerable question needs gold_files")
    return row


def _split(cell: str) -> list[str]:
    return [part.strip() for part in cell.split(LIST_SEPARATOR) if part.strip()]


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _split(value)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _as_bool(value: Any) -> bool | None:
    """Read the `answerable` flag; an empty value means answerable, an unknown one is an error."""
    if value is None or value == "":
        return True
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    return None
