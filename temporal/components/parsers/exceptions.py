from __future__ import annotations


class PermanentParsingError(Exception):
    """A parse that will never succeed on retry, whatever the number of attempts.

    A scanned PDF has no text to extract, a corrupt or encrypted file cannot be opened:
    retrying spends time and history for the same failure. The activity marks these
    non-retryable so Temporal stops immediately, and records `reason` so the document's
    failure is explainable without reading logs.
    """

    def __init__(self, reason: str, message: str | None = None) -> None:
        super().__init__(message or reason)
        self.reason = reason
