"""Functions that clean single CSV values: email, region, status, date, salary and text.

Each function takes the raw text from the file (or None). When the value is not
acceptable it raises ValueError with a short message: "missing", "invalid",
"bad format" or "impossible date". The row model in row.py adds the field name.
"""

import re
from datetime import date
from decimal import Decimal

from app.regions import VALID_REGIONS

# Keep in sync with the status check in db/schema.sql.
VALID_STATUSES = ("active", "screening", "interviewing", "withdrawn")

# The same shape rule as candidates_email_format in db/schema.sql.
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

# Lets a region be written without its hyphen: "USMW" -> "US-MW".
REGIONS_WITHOUT_HYPHEN = {region.replace("-", ""): region for region in VALID_REGIONS}

# The three accepted date shapes (two-digit day and month, ASCII digits only).
ISO_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")  # YYYY-MM-DD
US_DATE = re.compile(r"([0-9]{2})/([0-9]{2})/([0-9]{4})")  # MM/DD/YYYY
TEXT_DATE = re.compile(r"([0-9]{2})-([A-Za-z]{3})-([0-9]{4})")  # DD-Mon-YYYY
MONTHS = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}

# $ and thousands commas are allowed, and a trailing k means thousands.
SALARY_PATTERN = re.compile(
    r"\$?\s*(?P<number>[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*(?P<k>[kK])?"
)

# The largest value the numeric(12, 2) salary column can hold.
MAX_SALARY = Decimal("9999999999.99")


def clean_text(value: str | None) -> str | None:
    """Trim the text and return None if nothing is left. Everything else is kept as written."""
    if value is None:
        return None
    # PostgreSQL text cannot hold NUL characters, so they are dropped.
    text = value.replace("\x00", "").strip()
    return text or None


def require_text(value: str | None) -> str:
    """Clean the text like clean_text, but reject it when it is empty."""
    text = clean_text(value)
    if text is None:
        raise ValueError("missing")
    return text


def clean_email(value: str | None) -> str:
    """Trim and lowercase the email; reject it when it is empty or not shaped like an email."""
    email = (value or "").strip().lower()
    if not email:
        raise ValueError("missing")
    if not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("invalid")
    return email


def clean_region(value: str | None) -> str:
    """Map a region to its standard code, ignoring case, spaces and a missing hyphen."""
    compact = "".join((value or "").split()).upper()
    if not compact:
        raise ValueError("missing")
    if compact in VALID_REGIONS:
        return compact
    if compact in REGIONS_WITHOUT_HYPHEN:
        return REGIONS_WITHOUT_HYPHEN[compact]
    raise ValueError("invalid")


def clean_status(value: str | None) -> str:
    """Lowercase the status and check it is one of the four known values (no typo guessing)."""
    status = (value or "").strip().lower()
    if not status:
        raise ValueError("missing")
    if status not in VALID_STATUSES:
        raise ValueError("invalid")
    return status


def clean_date(value: str | None) -> date | None:
    """Read YYYY-MM-DD, MM/DD/YYYY or DD-Mon-YYYY. Empty gives None; anything else is rejected."""
    text = (value or "").strip()
    if not text:
        return None

    if match := ISO_DATE.fullmatch(text):
        year, month, day = (int(part) for part in match.groups())
    elif match := US_DATE.fullmatch(text):
        month, day, year = (int(part) for part in match.groups())
    elif match := TEXT_DATE.fullmatch(text):
        day, year = int(match[1]), int(match[3])
        month = MONTHS.get(match[2].lower())
        if month is None:
            raise ValueError("bad format")
    else:
        raise ValueError("bad format")

    try:
        return date(year, month, day)
    except ValueError:
        raise ValueError("impossible date") from None


def clean_salary(value: str | None) -> Decimal | None:
    """Read amounts like $95,000, 97,500, 88000 or 85k. Anything else becomes None (not a rejection)."""
    match = SALARY_PATTERN.fullmatch((value or "").strip())
    if match is None:
        return None
    amount = Decimal(match["number"].replace(",", ""))
    if match["k"]:
        amount *= 1000
    if amount > MAX_SALARY:
        return None
    return amount.quantize(Decimal("0.01"))