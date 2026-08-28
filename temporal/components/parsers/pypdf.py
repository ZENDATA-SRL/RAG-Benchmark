from __future__ import annotations

from typing import IO

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from src.components.builtin import ParseOutput, ParsePage

from temporal.components.parsers.exceptions import PermanentParsingError
from temporal.components.parsers.normalization import normalize_text

KEY = "pypdf"


class PyPdfParser:
    """Text extraction from PDF via `pypdf`.

    Lives in the worker and not in the API because it is the only process that runs it: the
    API serves `pypdf.PARAMS_SCHEMA` without needing the library. Satisfies the `Parser`
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
        try:
            reader = PdfReader(stream)
        except PdfReadError as error:
            raise PermanentParsingError("corrupt_pdf", str(error)) from error

        if reader.is_encrypted:
            # An empty-password decrypt is attempted first: many PDFs are flagged encrypted
            # only to disable printing and open with no password at all.
            try:
                if reader.decrypt("") == 0:
                    raise PermanentParsingError("encrypted_pdf", "PDF is password protected")
            except (PdfReadError, NotImplementedError) as error:
                raise PermanentParsingError("encrypted_pdf", str(error)) from error

        pages: list[ParsePage] = []
        has_text = False
        try:
            for index, page in enumerate(reader.pages, start=1):
                text = normalize_text(page.extract_text() or "")
                if text:
                    has_text = True
                pages.append(ParsePage(page=index, text=text))
        except PdfReadError as error:
            raise PermanentParsingError("corrupt_pdf", str(error)) from error

        if not has_text:
            raise PermanentParsingError(
                "no_extractable_text",
                "no extractable text (likely a scanned PDF); OCR is out of scope",
            )

        metadata = self._metadata(reader, page_count=len(pages))
        return ParseOutput(pages=pages, metadata=metadata)

    @staticmethod
    def _metadata(reader: PdfReader, *, page_count: int) -> dict[str, object]:
        producer: str | None = None
        info = reader.metadata
        if info is not None:
            producer = info.producer
        return {"page_count": page_count, "producer": producer}
