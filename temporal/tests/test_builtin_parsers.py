from __future__ import annotations

import io

import pytest

from temporal.components.parsers.exceptions import PermanentParsingError
from temporal.components.parsers.normalization import normalize_text
from temporal.components.parsers.pypdf import PyPdfParser
from temporal.tests.pdf_fixtures import make_blank_pdf, make_pdf


@pytest.fixture
def parser() -> PyPdfParser:
    return PyPdfParser()


def test_extracts_text_per_page(parser: PyPdfParser) -> None:
    """The page is the unit of extraction, because it is the anchor propagated to chunks."""
    data = make_pdf(["First page.", "Second page."])
    output = parser.parse(io.BytesIO(data), "doc.pdf")

    assert [page["page"] for page in output["pages"]] == [1, 2]
    assert output["pages"][0]["text"] == "First page."
    assert output["pages"][1]["text"] == "Second page."
    assert output["metadata"]["page_count"] == 2


def test_is_deterministic(parser: PyPdfParser) -> None:
    """Two parses of the same bytes yield identical output; chunk-level gold relies on it."""
    data = make_pdf(["Alpha.", "Beta.", "Gamma."])
    first = parser.parse(io.BytesIO(data), "doc.pdf")
    second = parser.parse(io.BytesIO(data), "doc.pdf")
    assert first == second


def test_scanned_pdf_is_permanent_no_extractable_text(parser: PyPdfParser) -> None:
    """A page with no text stream never yields text: a permanent, dedicated-reason failure."""
    data = make_blank_pdf(2)
    with pytest.raises(PermanentParsingError) as error:
        parser.parse(io.BytesIO(data), "scan.pdf")
    assert error.value.reason == "no_extractable_text"


def test_corrupt_pdf_is_permanent(parser: PyPdfParser) -> None:
    """Bytes that are not a PDF fail permanently rather than being retried forever."""
    with pytest.raises(PermanentParsingError) as error:
        parser.parse(io.BytesIO(b"not a pdf at all"), "broken.pdf")
    assert error.value.reason == "corrupt_pdf"


def test_normalisation_dehyphenates_and_collapses_spaces() -> None:
    assert normalize_text("de-\nsillabazione") == "desillabazione"
    assert normalize_text("a   b\t c") == "a b c"


def test_normalisation_canonicalises_quotes_and_ligatures() -> None:
    assert normalize_text("\u201cquoted\u201d") == '"quoted"'
    assert normalize_text("o\uFB00ice") == "office"
    assert normalize_text("\uFB01ne") == "fine"
