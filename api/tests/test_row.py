"""Unit tests for CandidateRow and parse_row, using real rows from candidates_import.csv."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.importing.row import CSV_COLUMNS, RowRejected, parse_row


def make_row(**changes: str | None) -> dict[Any, Any]:
    """Start from a clean real row (C-1001, Alicia Trent) and change only some fields."""
    row = {
        "candidate_id": "C-1001",
        "first_name": "Alicia",
        "last_name": "Trent",
        "email": "alicia.trent@gmail.com",
        "phone": "+1 (734) 555-0142",
        "region_code": "US-MW",
        "desired_role": "Full-Stack Engineer",
        "salary_expectation": "$95,000",
        "applied_date": "2026-05-14",
        "status": "Active",
        "source": "LinkedIn",
        "notes": "Strong React portfolio",
    }
    row.update(changes)
    return row


def test_columns_match_the_csv_header() -> None:
    """The model fields are in the same order as the columns in candidates_import.csv."""
    assert CSV_COLUMNS == (
        "candidate_id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "region_code",
        "desired_role",
        "salary_expectation",
        "applied_date",
        "status",
        "source",
        "notes",
    )


def test_clean_row_is_converted() -> None:
    """A good row comes back with real types: a Decimal salary, a date and a lowercase status."""
    row = parse_row(make_row())
    assert row.candidate_id == "C-1001"
    assert row.email == "alicia.trent@gmail.com"
    assert row.region_code == "US-MW"
    assert row.salary_expectation == Decimal("95000")
    assert row.applied_date == date(2026, 5, 14)
    assert row.status == "active"


def test_email_with_spaces_and_capitals_is_cleaned() -> None:
    """C-1031 is accepted, with its email trimmed and lowercased."""
    row = parse_row(make_row(candidate_id="C-1031", email="  Alicia.Trent@Gmail.com ", source="Indeed"))
    assert row.email == "alicia.trent@gmail.com"


def test_sql_looking_text_passes_through_unchanged() -> None:
    """C-1036's last name and C-1037's notes are kept exactly as written."""
    last_name = "O'Connor'); DROP TABLE candidates;--"
    notes = "' OR '1'='1"
    row = parse_row(make_row(candidate_id="C-1036", first_name="Robert", last_name=last_name, notes=notes))
    assert row.last_name == last_name
    assert row.notes == notes


def test_unicode_names_are_not_changed() -> None:
    """C-1008's accented name is kept exactly."""
    row = parse_row(make_row(candidate_id="C-1008", first_name="Nguyễn", last_name="Thị Hoa"))
    assert (row.first_name, row.last_name) == ("Nguyễn", "Thị Hoa")


def test_multiline_notes_are_kept() -> None:
    """C-1050's notes keep their line breaks."""
    notes = "Interview notes:\nRound 1 passed.\nRound 2 pending scheduling."
    assert parse_row(make_row(notes=notes)).notes == notes


@pytest.mark.parametrize(
    ("changes", "field", "expected"),
    [
        ({"applied_date": "06/30/2026"}, "applied_date", date(2026, 6, 30)),  # C-1038
        ({"applied_date": "14-May-2026"}, "applied_date", date(2026, 5, 14)),  # C-1039
        ({"applied_date": ""}, "applied_date", None),  # C-1041
        ({"region_code": "us-mw"}, "region_code", "US-MW"),  # C-1042
        ({"region_code": " CO-BOG "}, "region_code", "CO-BOG"),  # C-1043
        ({"region_code": "USW"}, "region_code", "US-W"),  # C-1044
        ({"status": "ACTIVE"}, "status", "active"),  # C-1046
        ({"salary_expectation": "85k"}, "salary_expectation", Decimal("85000")),  # C-1046
        ({"salary_expectation": "negotiable"}, "salary_expectation", None),  # C-1047
        ({"salary_expectation": ""}, "salary_expectation", None),  # C-1048
        ({"phone": ""}, "phone", None),  # C-1051
    ],
)
def test_rows_that_are_accepted(changes: dict[str, str], field: str, expected: object) -> None:
    """Rows with a different format, or with an optional value missing, are accepted and cleaned."""
    assert getattr(parse_row(make_row(**changes)), field) == expected


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"email": "marcus.reed[at]gmail.com"}, "email: invalid"),  # C-1033
        ({"email": "tina.holloway.gmail.com"}, "email: invalid"),  # C-1034
        ({"email": ""}, "email: missing"),  # C-1035
        ({"applied_date": "2026-02-30"}, "applied_date: impossible date"),  # C-1040
        ({"region_code": "ZZ-99"}, "region_code: invalid"),  # C-1045
        ({"status": "actve", "salary_expectation": "negotiable"}, "status: invalid"),  # C-1047
        ({"status": "on hold", "salary_expectation": ""}, "status: invalid"),  # C-1048
        ({"region_code": "", "phone": ""}, "region_code: missing"),  # C-1051
        ({"first_name": " "}, "first_name: missing"),
    ],
)
def test_rows_that_are_rejected(changes: dict[str, str], reason: str) -> None:
    """Bad rows are rejected with a short 'field: problem' reason (a bad salary never adds one)."""
    with pytest.raises(RowRejected) as error:
        parse_row(make_row(**changes))
    assert error.value.reason == reason


def test_several_problems_are_joined_in_column_order() -> None:
    """Reasons follow the CSV column order, whatever order the row's keys arrive in."""
    row = make_row(
        email="marcus.reed[at]gmail.com",
        region_code="ZZ-99",
        applied_date="2026-02-30",
        status="actve",
        salary_expectation="negotiable",
    )
    backwards = dict(reversed(list(row.items())))
    with pytest.raises(RowRejected) as error:
        parse_row(backwards)
    assert error.value.reason == (
        "email: invalid; region_code: invalid; applied_date: impossible date; status: invalid"
    )


def test_row_with_extra_columns_is_rejected() -> None:
    """A row with more cells than the header (for example an unquoted comma) is rejected."""
    row = make_row()
    row[None] = ["left over cell"]
    with pytest.raises(RowRejected) as error:
        parse_row(row)
    assert error.value.reason == "too many columns"