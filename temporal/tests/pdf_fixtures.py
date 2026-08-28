from __future__ import annotations

import io


def make_pdf(pages_text: list[str]) -> bytes:
    """Build a minimal, valid PDF with one text line per page.

    Deliberately hand-rolled and dependency-free: the tests need small PDFs with known,
    extractable text, and pulling in a PDF-generation library only to produce them would be
    heavier than the ~40 lines it takes to emit the object table directly.
    """
    n_pages = len(pages_text)
    font_id = 3
    page_ids: list[int] = []
    content_ids: list[int] = []
    next_id = 4
    for _ in range(n_pages):
        page_ids.append(next_id)
        next_id += 1
        content_ids.append(next_id)
        next_id += 1

    parts: dict[int, bytes] = {}
    parts[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    parts[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode()
    parts[font_id] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    for index in range(n_pages):
        page_id = page_ids[index]
        content_id = content_ids[index]
        parts[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode()
        text = pages_text[index].replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 700 Td ({text}) Tj ET".encode()
        parts[content_id] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)

    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    max_id = max(parts)
    for object_id in range(1, max_id + 1):
        offsets[object_id] = buffer.tell()
        buffer.write(f"{object_id} 0 obj\n".encode())
        buffer.write(parts[object_id])
        buffer.write(b"\nendobj\n")
    xref_position = buffer.tell()
    buffer.write(f"xref\n0 {max_id + 1}\n".encode())
    buffer.write(b"0000000000 65535 f \n")
    for object_id in range(1, max_id + 1):
        buffer.write(f"{offsets[object_id]:010d} 00000 n \n".encode())
    buffer.write(
        f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF".encode()
    )
    return buffer.getvalue()


def make_blank_pdf(n_pages: int = 1) -> bytes:
    """A PDF whose pages carry no text stream: stands in for a scanned document."""
    font_id = 3
    page_ids: list[int] = []
    next_id = 4
    for _ in range(n_pages):
        page_ids.append(next_id)
        next_id += 1

    parts: dict[int, bytes] = {}
    parts[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    parts[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode()
    parts[font_id] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    for page_id in page_ids:
        parts[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        ).encode()

    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    max_id = max(parts)
    for object_id in range(1, max_id + 1):
        offsets[object_id] = buffer.tell()
        buffer.write(f"{object_id} 0 obj\n".encode())
        buffer.write(parts[object_id])
        buffer.write(b"\nendobj\n")
    xref_position = buffer.tell()
    buffer.write(f"xref\n0 {max_id + 1}\n".encode())
    buffer.write(b"0000000000 65535 f \n")
    for object_id in range(1, max_id + 1):
        buffer.write(f"{offsets[object_id]:010d} 00000 n \n".encode())
    buffer.write(
        f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF".encode()
    )
    return buffer.getvalue()
