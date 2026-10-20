from __future__ import annotations

from typing import IO

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException
from src.components.builtin import ParseOutput, ParsePage

from temporal.components.parsers.exceptions import PermanentParsingError
from temporal.components.parsers.normalization import normalize_text

KEY = "pdfplumber"


class PdfPlumberParser:
    """Text extraction from PDF via `pdfplumber`.

    Lives in the worker and not in the API because it is the only process that runs it: the
    API serves `pdfplumber.PARAMS_SCHEMA` without needing the library. Satisfies the `Parser`
    protocol declared in `src.components.builtin.contracts`.
    """

    def parse(self, stream: IO[bytes], filename: str) -> ParseOutput:
        """Extract the normalised text of every page of a PDF.

        The page is kept as the unit of extraction, not a single joined string, because it
        is the anchor the chunker propagates onto chunks and the UI uses to show where a
        chunk came from (RT-U04): losing it here means it cannot be recovered downstream.

        Raises:
            PermanentParsingError: If the file is corrupt or encrypted (`corrupt_pdf` /
                `encrypted_pdf`), or if no page yields extractable text
                (`no_extractable_text`). These never succeed on retry, so the caller marks
                them non-retryable and the document ends `failed` while the others proceed.
        """
        with self._open(stream) as pdf:
            pages: list[ParsePage] = []
            has_text = False
            try:
                for index, page in enumerate(pdf.pages, start=1):
                    text = normalize_text(page.extract_text() or "")
                    if text:
                        has_text = True
                    pages.append(ParsePage(page=index, text=text))
            except PdfminerException as error:
                raise PermanentParsingError("corrupt_pdf", str(error)) from error

            if not has_text:
                raise PermanentParsingError(
                    "no_extractable_text",
                    "no extractable text (likely a scanned PDF); OCR is out of scope",
                )

            return ParseOutput(
                pages=pages, metadata=self._metadata(pdf, page_count=len(pages))
            )

    @staticmethod
    def _open(stream: IO[bytes]) -> pdfplumber.PDF:
        try:
            return pdfplumber.open(stream)
        except PdfminerException as error:
            # `pdfplumber.open` already tries an empty password (many PDFs are flagged
            # encrypted only to disable printing). The original pdfminer error is in
            # `args[0]` because the wrapper is raised without `from`.
            original = error.args[0] if error.args else error
            if isinstance(original, PDFPasswordIncorrect):
                raise PermanentParsingError(
                    "encrypted_pdf", "PDF is password protected"
                ) from error
            raise PermanentParsingError("corrupt_pdf", str(error)) from error

    @staticmethod
    def _metadata(pdf: pdfplumber.PDF, *, page_count: int) -> dict[str, object]:
        producer: str | None = None
        info = pdf.metadata
        if info:
            producer = info.get("Producer") or info.get("producer")
        return {"page_count": page_count, "producer": producer}
