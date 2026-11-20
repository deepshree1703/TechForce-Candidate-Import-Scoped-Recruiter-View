"""Unit tests for the cleaning functions, using real values from candidates_import.csv."""

from datetime import date
from decimal import Decimal

import pytest

from app.importing.cleaning import (
    clean_date,
    clean_email,
    clean_region,
    clean_salary,
    clean_status,
    clean_text,
    require_text,
)


# ---- email ----


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Alicia.Trent@Gmail.com ", "alicia.trent@gmail.com"),  # C-1031: spaces and capitals
        ("alicia.trent@gmail.com", "alicia.trent@gmail.com"),  # C-1001: already clean
    ],
)
def test_email_is_trimmed_and_lowercased(raw: str, expected: str) -> None:
    """Spaces around the email are removed and capitals become lowercase."""
    assert clean_email(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "marcus.reed[at]gmail.com",  # C-1033
        "tina.holloway.gmail.com",  # C-1034
        "two words@gmail.com",
        "a@b",
    ],
)
def test_bad_email_is_invalid(raw: str) -> None:
    """[at] instead of @, no @ at all, spaces inside, or no dot in the domain are invalid."""
    with pytest.raises(ValueError, match="^invalid$"):
        clean_email(raw)


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_empty_email_is_missing(raw: str | None) -> None:
    """An empty email (C-1035) is reported as missing, not invalid."""
    with pytest.raises(ValueError, match="^missing$"):
        clean_email(raw)


# ---- region ----


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("US-MW", "US-MW"),  # C-1001
        ("us-mw", "US-MW"),  # C-1042: lowercase
        (" CO-BOG ", "CO-BOG"),  # C-1043: spaces around
        ("USW", "US-W"),  # C-1044: missing hyphen
        ("us mw", "US-MW"),  # spaces inside
    ],
)
def test_region_is_mapped_to_its_code(raw: str, expected: str) -> None:
    """Case, spaces and a missing hyphen are ignored."""
    assert clean_region(raw) == expected


@pytest.mark.parametrize("raw", ["ZZ-99", "U-SMW", "US--MW"])
def test_unknown_region_is_invalid(raw: str) -> None:
    """ZZ-99 (C-1045) and misplaced or doubled hyphens cannot be mapped with confidence."""
    with pytest.raises(ValueError, match="^invalid$"):
        clean_region(raw)


@pytest.mark.parametrize("raw", ["", None])
def test_empty_region_is_missing(raw: str | None) -> None:
    """An empty region (C-1051) is reported as missing."""
    with pytest.raises(ValueError, match="^missing$"):
        clean_region(raw)


# ---- status ----


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Active", "active"),
        ("ACTIVE", "active"),  # C-1046
        ("Interviewing", "interviewing"),
        ("Screening", "screening"),
        ("Withdrawn", "withdrawn"),
    ],
)
def test_status_is_lowercased(raw: str, expected: str) -> None:
    """Known statuses are accepted in any capitalisation."""
    assert clean_status(raw) == expected


@pytest.mark.parametrize("raw", ["actve", "on hold", "pending"])
def test_unknown_status_is_invalid(raw: str) -> None:
    """A typo (C-1047) or a status outside the set (C-1048) is rejected, never guessed."""
    with pytest.raises(ValueError, match="^invalid$"):
        clean_status(raw)


@pytest.mark.parametrize("raw", ["", "   "])
def test_empty_status_is_missing(raw: str) -> None:
    """An empty status is reported as missing."""
    with pytest.raises(ValueError, match="^missing$"):
        clean_status(raw)


# ---- date ----


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-05-14", date(2026, 5, 14)),  # C-1001
        ("06/30/2026", date(2026, 6, 30)),  # C-1038
        ("14-May-2026", date(2026, 5, 14)),  # C-1039
        ("14-may-2026", date(2026, 5, 14)),  # month name in lowercase
        ("", None),  # C-1041: an empty date is fine
        ("   ", None),
        (None, None),
    ],
)
def test_date_formats(raw: str | None, expected: date | None) -> None:
    """The three accepted formats are read; an empty date gives None."""
    assert clean_date(raw) == expected


@pytest.mark.parametrize("raw", ["2026-02-30", "02/30/2026", "31-Apr-2026", "2026-13-01"])
def test_impossible_date_is_rejected(raw: str) -> None:
    """A date in the right format that does not exist (C-1040) is rejected."""
    with pytest.raises(ValueError, match="^impossible date$"):
        clean_date(raw)


@pytest.mark.parametrize(
    "raw",
    ["May 14, 2026", "2026/05/14", "14-Foo-2026", "30-06-2026", "6/30/2026", "yesterday"],
)
def test_other_date_formats_are_rejected(raw: str) -> None:
    """Only the three listed formats (with two-digit day and month) are accepted."""
    with pytest.raises(ValueError, match="^bad format$"):
        clean_date(raw)


# ---- salary ----


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$95,000", Decimal("95000")),  # C-1001
        ("97,500", Decimal("97500")),  # C-1004
        ("88000", Decimal("88000")),  # C-1002
        ("85k", Decimal("85000")),  # C-1046
        ("85K", Decimal("85000")),
        ("$1.5k", Decimal("1500")),
    ],
)
def test_salary_formats(raw: str, expected: Decimal) -> None:
    """Dollar signs, thousands commas and a trailing k are understood."""
    assert clean_salary(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["negotiable", "", "   ", None, "12,34", "-5", "99999999999999", "abc123"],
)
def test_unreadable_salary_becomes_none(raw: str | None) -> None:
    """Text (C-1047), empty (C-1048), odd commas, negatives and too-large numbers give None."""
    assert clean_salary(raw) is None


# ---- text ----


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Strong React portfolio  ", "Strong React portfolio"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_text_is_trimmed(raw: str | None, expected: str | None) -> None:
    """Spaces around text are removed and empty text becomes None."""
    assert clean_text(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "O'Connor'); DROP TABLE candidates;--",  # C-1036 last name
        "' OR '1'='1",  # C-1037 notes
        "Nguyễn",  # C-1008
        "Thị Hoa",  # C-1008
        "Prefers remote, but open to hybrid in Denver, CO",  # C-1049
        "Interview notes:\nRound 1 passed.\nRound 2 pending scheduling.",  # C-1050
    ],
)
def test_text_content_is_kept_exactly(raw: str) -> None:
    """SQL-looking text, accents, commas and line breaks pass through unchanged."""
    assert clean_text(raw) == raw


def test_nul_characters_are_removed() -> None:
    """NUL characters cannot be stored by PostgreSQL, so they are dropped."""
    assert clean_text("a\x00b") == "ab"


@pytest.mark.parametrize("raw", ["", "  ", None])
def test_required_text_rejects_empty(raw: str | None) -> None:
    """Required text (such as a first name) must not be empty."""
    with pytest.raises(ValueError, match="^missing$"):
        require_text(raw)


def test_required_text_is_trimmed() -> None:
    """Required text is trimmed like any other text."""
    assert require_text("  Alicia ") == "Alicia"