from __future__ import annotations

from typing import IO

from src.components.builtin import ParseOutput
from src.components.builtin.parsers import pypdf

KEY = pypdf.KEY


class PyPdfParser:
    """Text extraction from PDF via `pypdf`.

    Lives in the worker and not in the API because it is the only process that runs it: the
    API serves `pypdf.PARAMS_SCHEMA` without needing the library. Satisfies the `Parser`
    protocol declared in `src.components.builtin.contracts`.
    """

    def parse(self, stream: IO[bytes], filename: str) -> ParseOutput:
        """Extract the text of every page of a PDF.

        Raises:
            NotImplementedError: Until the parsing activity of Sprint 3 lands.
        """
        raise NotImplementedError("PyPdfParser.parse lands with the Sprint 3 parsing activity")
