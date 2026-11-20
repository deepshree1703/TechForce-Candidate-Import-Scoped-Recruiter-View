"""Reads the uploaded CSV bytes into raw rows (one dict per data row)."""

import csv
import io
from typing import Any

from app.importing.row import CSV_COLUMNS


class BadFileError(Exception):
    """Raised when the file cannot be read as a candidates CSV (the API will answer 400)."""


def read_rows(content: bytes) -> list[dict[str | None, Any]]:
    """Decode the file and return one dict per data row, keyed by the lowercase header names.

    A quoted cell with line breaks is still one row. Blank lines are skipped. Cells beyond
    the header are kept under the key None, and missing trailing cells are None.
    """
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise BadFileError("file is not valid UTF-8 text") from error

    # PostgreSQL cannot store NUL characters, so they are removed before anything is parsed.
    text = text.replace("\x00", "")

    reader = csv.DictReader(io.StringIO(text, newline=""))
    try:
        header = [name.strip().lower() for name in reader.fieldnames or []]
        if not header:
            raise BadFileError("file is empty")
        missing = [column for column in CSV_COLUMNS if column not in header]
        if missing:
            raise BadFileError("missing columns: " + ", ".join(missing))
        reader.fieldnames = header
        return list(reader)
    except csv.Error as error:
        raise BadFileError(f"cannot read the CSV: {error}") from error