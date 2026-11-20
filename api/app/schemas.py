"""The Pydantic models the API sends back."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class RejectedItem(BaseModel):
    """One rejected CSV row in the import report."""

    row_number: int
    candidate_id: str | None
    reason: str


class ImportReport(BaseModel):
    """The result of one import run."""

    run_id: int
    rows_read: int
    imported: int
    merged: int
    rejected: list[RejectedItem]


class CandidateSummary(BaseModel):
    """One candidate as shown in the list (the columns of the table on the page)."""

    model_config = ConfigDict(from_attributes=True)

    candidate_id: str
    first_name: str
    last_name: str
    email: str
    region_code: str
    desired_role: str | None
    status: str
    applied_date: date | None


class CandidateDetail(CandidateSummary):
    """One candidate with every field, as shown by the detail endpoint."""

    phone: str | None
    salary_expectation: Decimal | None
    source: str | None
    notes: str | None


class CandidatePage(BaseModel):
    """One page of the candidate list, plus the total number of matches."""

    items: list[CandidateSummary]
    total: int
    page: int
    page_size: int


class RecruiterOut(BaseModel):
    """A recruiter as shown in the dropdown. No email and no regions."""

    recruiter_id: str
    full_name: str
    role: str