"""The candidate list and detail endpoints.

Both use get_access, the one shared dependency. It tells PostgreSQL which regions the
caller has, and row-level security does the filtering. Nothing here checks regions, so
a candidate outside the caller's regions simply does not exist for them.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, select

from app.access import Access, get_access
from app.models import Candidate
from app.schemas import CandidateDetail, CandidatePage, CandidateSummary
from app.search import search_condition

# The same four values as the status check in db/schema.sql.
CandidateStatus = Literal["active", "screening", "interviewing", "withdrawn"]

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_PAGE = 100_000
MAX_SEARCH_LENGTH = 100

router = APIRouter(prefix="/candidates")


@router.get("", response_model=CandidatePage)
def list_candidates(
    access: Annotated[Access, Depends(get_access)],
    search: Annotated[str | None, Query(max_length=MAX_SEARCH_LENGTH)] = None,
    status: Annotated[CandidateStatus | None, Query()] = None,
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> CandidatePage:
    """List the caller's candidates: newest applied date first, with search and paging."""
    conditions = []
    text_match = search_condition(search)
    if text_match is not None:
        conditions.append(text_match)
    if status is not None:
        conditions.append(Candidate.status == status)

    session = access.session
    total = session.execute(select(func.count()).select_from(Candidate).where(*conditions)).scalar_one()
    query = (
        select(Candidate)
        .where(*conditions)
        .order_by(Candidate.applied_date.desc().nulls_last(), Candidate.candidate_id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    rows = session.execute(query).scalars().all()
    items = [CandidateSummary.model_validate(row) for row in rows]
    return CandidatePage(items=items, total=total, page=page, page_size=page_size)


@router.get("/{candidate_id}", response_model=CandidateDetail)
def get_candidate(
    candidate_id: Annotated[str, Path(max_length=50)],
    access: Annotated[Access, Depends(get_access)],
) -> CandidateDetail:
    """Return one candidate. Missing and out-of-region both give 404."""
    query = select(Candidate).where(Candidate.candidate_id == candidate_id)
    candidate = access.session.execute(query).scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return CandidateDetail.model_validate(candidate)