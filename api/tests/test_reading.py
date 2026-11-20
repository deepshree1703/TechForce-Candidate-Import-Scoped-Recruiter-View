"""Tests for reading the uploaded CSV bytes into raw rows."""

import pytest

from app.importing.reading import BadFileError, read_rows
from app.importing.row import CSV_COLUMNS

HEADER = ",".join(CSV_COLUMNS)
GOOD_ROW = "C-1,Ann,Lee,ann@example.com,,US-W,,,,Active,,"


def to_bytes(*lines: str) -> bytes:
    """Join lines with newlines and encode them as UTF-8."""
    return "\n".join(lines).encode("utf-8")


def test_rows_are_read_with_header_names() -> None:
    """Each data row becomes a dict keyed by the header names; empty cells are empty text."""
    rows = read_rows(to_bytes(HEADER, GOOD_ROW))
    assert len(rows) == 1
    assert rows[0]["candidate_id"] == "C-1"
    assert rows[0]["phone"] == ""


def test_quoted_multiline_cell_is_one_row() -> None:
    """A quoted cell with a line break stays inside one row (like C-1050's notes)."""
    multiline = 'C-2,Bob,Ray,bob@example.com,,US-W,,,,Active,,"line one\nline two"'
    rows = read_rows(to_bytes(HEADER, multiline, GOOD_ROW))
    assert len(rows) == 2
    assert rows[0]["notes"] == "line one\nline two"


def test_bom_is_ignored() -> None:
    """A byte order mark at the start of the file does not spoil the first column name."""
    rows = read_rows(("\ufeff" + HEADER + "\n" + GOOD_ROW).encode("utf-8"))
    assert rows[0]["candidate_id"] == "C-1"


def test_header_names_are_trimmed_and_lowercased() -> None:
    """Spaces and capitals in the header do not matter."""
    header = ",".join(f" {name.upper()} " for name in CSV_COLUMNS)
    rows = read_rows(to_bytes(header, GOOD_ROW))
    assert rows[0]["email"] == "ann@example.com"


def test_missing_column_is_a_bad_file() -> None:
    """A file without the email column cannot be imported."""
    header = ",".join(column for column in CSV_COLUMNS if column != "email")
    with pytest.raises(BadFileError, match="email"):
        read_rows(to_bytes(header, GOOD_ROW))


def test_empty_file_is_a_bad_file() -> None:
    """A file with no content is rejected."""
    with pytest.raises(BadFileError, match="empty"):
        read_rows(b"")


def test_invalid_utf8_is_a_bad_file() -> None:
    """A file that is not UTF-8 (for example Latin-1) is rejected instead of being mangled."""
    with pytest.raises(BadFileError, match="UTF-8"):
        read_rows(b"candidate_id\n\xe9\n")


def test_header_only_gives_no_rows() -> None:
    """A file with just the header is valid and has no rows."""
    assert read_rows(to_bytes(HEADER)) == []


def test_blank_lines_are_skipped() -> None:
    """Empty lines (such as the one at the end of the real file) are not rows."""
    assert len(read_rows(to_bytes(HEADER, "", GOOD_ROW, "", ""))) == 1


def test_short_row_has_none_for_missing_cells() -> None:
    """A row that stops early gets None for the cells it does not have."""
    rows = read_rows(to_bytes(HEADER, "C-1,Ann,Lee"))
    assert rows[0]["email"] is None


def test_extra_cells_are_kept_under_none() -> None:
    """Cells beyond the header are kept under the key None so the row can be rejected."""
    rows = read_rows(to_bytes(HEADER, GOOD_ROW + ",extra,more"))
    assert rows[0][None] == ["extra", "more"]

def test_nul_characters_are_removed() -> None:
    """NUL characters (which PostgreSQL cannot store) are dropped before parsing."""
    rows = read_rows(to_bytes(HEADER, "C-1,Ann\x00,Lee,ann@example.com,,US-W,,,,Active,,"))
    assert rows[0]["first_name"] == "Ann"