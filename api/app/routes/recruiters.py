"""The recruiter list for the dropdown on the page.

It needs no X-Recruiter-Id header, because the page needs it to choose one. It returns
only the id, name and role. The recruiters table is not protected by row-level security.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Recruiter
from app.schemas import RecruiterOut

router = APIRouter()


@router.get("/recruiters", response_model=list[RecruiterOut])
def list_recruiters(session: Annotated[Session, Depends(get_session)]) -> list[RecruiterOut]:
    """List every recruiter (id, name and role only), ordered by id."""
    query = select(Recruiter.recruiter_id, Recruiter.full_name, Recruiter.role).order_by(Recruiter.recruiter_id)
    return [
        RecruiterOut(recruiter_id=row.recruiter_id, full_name=row.full_name, role=row.role)
        for row in session.execute(query).all()
    ]