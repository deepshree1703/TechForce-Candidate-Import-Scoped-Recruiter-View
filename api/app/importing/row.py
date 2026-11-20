"""Validates one CSV row into a clean CandidateRow, or rejects it with a short reason."""

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator

from app.importing.cleaning import (
    clean_date,
    clean_email,
    clean_region,
    clean_salary,
    clean_status,
    clean_text,
    require_text,
)


class RowRejected(Exception):
    """Raised when a row cannot be imported. The reason is a short text for the report."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class CandidateRow(BaseModel):
    """One valid, cleaned candidate row. The fields are in the same order as the CSV columns."""

    candidate_id: str
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    region_code: str
    desired_role: str | None = None
    salary_expectation: Decimal | None = None
    applied_date: date | None = None
    status: str
    source: str | None = None
    notes: str | None = None

    @field_validator("candidate_id", "first_name", "last_name", mode="before")
    @classmethod
    def clean_required_text(cls, value: str | None) -> str:
        """Trim the text; it must not be empty."""
        return require_text(value)

    @field_validator("phone", "desired_role", "source", "notes", mode="before")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        """Trim the text; empty becomes None."""
        return clean_text(value)

    @field_validator("email", mode="before")
    @classmethod
    def clean_email_field(cls, value: str | None) -> str:
        """Trim and lowercase the email; it must look like an email."""
        return clean_email(value)

    @field_validator("region_code", mode="before")
    @classmethod
    def clean_region_field(cls, value: str | None) -> str:
        """Map the region to one of the six valid codes."""
        return clean_region(value)

    @field_validator("salary_expectation", mode="before")
    @classmethod
    def clean_salary_field(cls, value: str | None) -> Decimal | None:
        """Read the salary; anything unreadable becomes None."""
        return clean_salary(value)

    @field_validator("applied_date", mode="before")
    @classmethod
    def clean_date_field(cls, value: str | None) -> date | None:
        """Read the date in one of the three accepted formats; empty becomes None."""
        return clean_date(value)

    @field_validator("status", mode="before")
    @classmethod
    def clean_status_field(cls, value: str | None) -> str:
        """Lowercase the status; it must be one of the four known values."""
        return clean_status(value)


# The CSV column names, in file order (they are the model's field names).
CSV_COLUMNS = tuple(CandidateRow.model_fields)


def join_reasons(error: ValidationError) -> str:
    """Turn validation errors into 'field: reason' texts, joined with '; ' in CSV column order."""
    problems = sorted(error.errors(), key=lambda problem: CSV_COLUMNS.index(str(problem["loc"][0])))
    parts = []
    for problem in problems:
        reason = str(problem["ctx"]["error"]) if "ctx" in problem else problem["msg"]
        parts.append(f"{problem['loc'][0]}: {reason}")
    return "; ".join(parts)


def parse_row(raw: dict[str | None, Any]) -> CandidateRow:
    """Clean and validate one row from csv.DictReader; raise RowRejected if it is not acceptable."""
    # DictReader puts cells beyond the header under the key None (often an unquoted comma).
    if None in raw:
        raise RowRejected("too many columns")
    data = {column: raw.get(column) for column in CSV_COLUMNS}
    try:
        return CandidateRow.model_validate(data)
    except ValidationError as error:
        raise RowRejected(join_reasons(error)) from None