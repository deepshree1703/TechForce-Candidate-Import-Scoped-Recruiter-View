"""Access control: who is calling, and which regions the database lets them see.

get_access is the one shared dependency for every route that touches candidates.
It never filters rows itself. It only tells PostgreSQL the caller's regions, and the
row-level security rules in db/schema.sql do the rest.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_session, set_region_context
from app.models import Recruiter


@dataclass
class Access:
    """The caller, plus a database session that is already limited to the caller's regions."""

    session: Session
    recruiter_id: str
    role: str
    regions: list[str]


def get_access(
    session: Annotated[Session, Depends(get_session)],
    x_recruiter_id: Annotated[str | None, Header()] = None,
) -> Access:
    """Identify the caller from X-Recruiter-Id and set their regions for this transaction.

    No header gives 401. An id that is not a recruiter gives 403, never an empty 200.
    """
    recruiter_id = (x_recruiter_id or "").strip()
    if not recruiter_id:
        raise HTTPException(status_code=401, detail="X-Recruiter-Id header is required")

    recruiter = session.get(Recruiter, recruiter_id)
    if recruiter is None:
        raise HTTPException(status_code=403, detail="Unknown recruiter")

    regions = list(recruiter.assigned_regions)
    set_region_context(session, regions)
    return Access(session=session, recruiter_id=recruiter.recruiter_id, role=recruiter.role, regions=regions)
