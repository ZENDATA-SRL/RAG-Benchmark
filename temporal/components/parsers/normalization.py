from __future__ import annotations

import re
import unicodedata

# Ligatures pypdf may hand back as single codepoints; NFKC normalises most of these, but
# a few (notably the f-ligatures) are kept explicit so the canonical form does not depend
# on the unicode database version the worker happens to ship.
_LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}

# Curly quotes, primes and dashes to their ascii equivalents, so the same word typed with
# a smart-quote apostrophe and a plain one match during lexical retrieval (Milestone 6).
_PUNCTUATION = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u2032": "'",
    "\u2033": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2212": "-",
    "\u00a0": " ",
}

_TRANSLATION = {
    ord(source): target for source, target in {**_LIGATURES, **_PUNCTUATION}.items()
}

# A word split across a line by a hyphen: "de-\nsillabazione" -> "desillabazione". Only
# joined when a letter precedes the hyphen and a letter follows the break, so genuine
# hyphenated compounds at a line end are left alone as much as a heuristic can.
_HYPHEN_BREAK = re.compile(r"(?<=[A-Za-zÀ-ÿ])-\n(?=[A-Za-zÀ-ÿ])")
_SOFT_HYPHEN = "\u00ad"
_SPACES = re.compile(r"[^\S\n]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Normalise extracted page text to the one canonical form used downstream (RT-M01).

    De-hyphenates words broken across a line, collapses runs of spaces and tabs, drops the
    soft hyphen, maps typographic punctuation and ligatures to their canonical ascii form,
    and applies NFKC. Newlines are preserved because the chunker splits on them, but a run
    of blank lines is capped so the page structure stays comparable across parses.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_TRANSLATION)
    text = text.replace(_SOFT_HYPHEN, "")
    text = _HYPHEN_BREAK.sub("", text)
    text = _SPACES.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()
