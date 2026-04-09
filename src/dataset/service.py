from io import BytesIO
from typing import List
from uuid import UUID

import httpx
from fastapi import UploadFile
from openpyxl import load_workbook

from src.dataset.models import (
    DocumentORM,
    QuestionORM,
)
from src.dataset.repository import (
    find_document_by_name_and_url,
    get_dataset,
    get_documents_by_dataset,
    get_questions_by_dataset,
    insert_document,
    insert_question,
)
from src.infrastructure.blob_storage.blob import insert_blob


_XLSX_COLUMNS = ("query", "answer", "filename", "file_url")
_DOCUMENTS_XLSX_COLUMNS = ("file_name", "file_url")


class DocumentNotFoundError(LookupError):
    def __init__(self, row_index: int, name: str, url: str) -> None:
        super().__init__(
            f"Row {row_index}: no document matches filename={name!r} and file_url={url!r}"
        )
        self.row_index = row_index
        self.name = name
        self.url = url


def _normalize_header(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _cell_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_xlsx_rows(data: bytes) -> list[tuple[str, str, str, str]]:
    wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    try:
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        header_row = next(rows, None)
        if not header_row:
            return []

        headers = [_normalize_header(c) for c in header_row]
        col_index = {h: i for i, h in enumerate(headers) if h}
        for name in _XLSX_COLUMNS:
            if name not in col_index:
                raise ValueError(
                    f"XLSX must contain columns {list(_XLSX_COLUMNS)}; missing {name!r}"
                )

        def cols(r: tuple) -> tuple[str, str, str, str]:
            def at(name: str) -> str:
                i = col_index[name]
                return _cell_str(r[i] if i < len(r) else None)

            return at("query"), at("answer"), at("filename"), at("file_url")

        out: list[tuple[str, str, str, str]] = []
        for row in rows:
            if row is None:
                continue
            q, a, fn, u = cols(row)
            if not (q or a or fn or u):
                continue
            out.append((q, a, fn, u))
        return out
    finally:
        wb.close()


def _normalize_header_key(value: object) -> str:
    """
    Header normalization that tolerates 'file name' / 'file-name' / 'File_Name' etc.
    """
    return _normalize_header(value).replace(" ", "_").replace("-", "_")


def _parse_documents_xlsx_rows(data: bytes) -> list[tuple[str, str]]:
    wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    try:
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        header_row = next(rows, None)
        if not header_row:
            return []

        headers = [_normalize_header_key(c) for c in header_row]
        col_index = {h: i for i, h in enumerate(headers) if h}

        # Back-compat: accept `filename` as alias for `file_name`
        if "file_name" not in col_index and "filename" in col_index:
            col_index["file_name"] = col_index["filename"]

        for name in _DOCUMENTS_XLSX_COLUMNS:
            if name not in col_index:
                raise ValueError(
                    f"XLSX must contain columns {list(_DOCUMENTS_XLSX_COLUMNS)}; missing {name!r}"
                )

        out: list[tuple[str, str]] = []
        for row in rows:
            if row is None:
                continue
            file_name = _cell_str(
                row[col_index["file_name"]]
                if col_index["file_name"] < len(row)
                else None
            )
            file_url = _cell_str(
                row[col_index["file_url"]] if col_index["file_url"] < len(row) else None
            )
            if not (file_name or file_url):
                continue
            out.append((file_name, file_url))
        return out
    finally:
        wb.close()


def _upload_file_from_bytes(*, filename: str, content: bytes) -> UploadFile:
    # UploadFile wraps a sync file object; BytesIO is fine here.
    return UploadFile(filename=filename, file=BytesIO(content))


async def ingest_documents_from_xlsx(
    file: UploadFile, dataset_id: UUID
) -> list[DocumentORM]:
    dataset = await get_dataset(dataset_id)
    if dataset is None:
        raise ValueError(f"Dataset {dataset_id} not found")

    raw = await file.read()
    rows = _parse_documents_xlsx_rows(raw)

    docs: list[DocumentORM] = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        for i, (file_name, file_url) in enumerate(rows, start=2):
            if not file_name:
                raise ValueError(f"Row {i}: file_name is required")
            if not file_url:
                raise ValueError(f"Row {i}: file_url is required")

            try:
                resp = await client.get(file_url)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                raise ValueError(
                    f"Row {i}: failed to download {file_url!r}: {e}"
                ) from e

            upload = _upload_file_from_bytes(filename=file_name, content=resp.content)
            doc = await ingest_document(
                file=upload, file_url=file_url, dataset_id=dataset_id
            )
            docs.append(doc)

    return docs


async def get_documents(dataset_id: UUID) -> list[DocumentORM]:
    dataset = await get_dataset(dataset_id)
    if dataset is None:
        raise ValueError(f"Dataset {dataset_id} not found")
    return await get_documents_by_dataset(dataset_id)


async def get_questions(dataset_id: UUID) -> list[QuestionORM]:
    dataset = await get_dataset(dataset_id)
    if dataset is None:
        raise ValueError(f"Dataset {dataset_id} not found")
    return await get_questions_by_dataset(dataset_id)


async def ingest_document(
    file: UploadFile, file_url: str, dataset_id: UUID
) -> DocumentORM:
    dataset = await get_dataset(dataset_id)
    if dataset is None:
        raise ValueError(f"Dataset {dataset_id} not found")

    raw = await file.read()
    blob_url = insert_blob(
        container_name=f"{dataset.name}_{dataset.created_at.strftime('%Y%m%d')}",
        blob_name=file.filename,
        blob_content=raw,
    )
    document = DocumentORM(
        name=file.filename,
        url=file_url,
        dataset_id=dataset_id,
        blob_url=blob_url,
    )
    await insert_document(document)
    return document


async def ingest_dataset_questions(
    file: UploadFile, dataset_id: UUID
) -> List[QuestionORM]:
    dataset = await get_dataset(dataset_id)
    if dataset is None:
        raise ValueError(f"Dataset {dataset_id} not found")
    raw = await file.read()
    rows = _parse_xlsx_rows(raw)
    questions: list[QuestionORM] = []
    for i, (query, answer, filename, file_url) in enumerate(rows, start=2):
        doc = await find_document_by_name_and_url(filename, file_url, dataset_id)
        if doc is None:
            raise DocumentNotFoundError(i, filename, file_url)
        q = QuestionORM(
            query=query,
            answer=answer,
            document_id=doc.id,
            dataset_id=dataset_id,
        )
        await insert_question(q)
        questions.append(q)

    return questions
