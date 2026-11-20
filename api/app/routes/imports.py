"""The endpoint that imports a candidates CSV. Any known recruiter may call it.

The CSV is sent as the raw request body (not as a multipart form), for example:
  curl -X POST "http://localhost:8000/api/v1/candidates/import?filename=candidates.csv" \
       -H "X-Recruiter-Id: R-101" -H "Content-Type: text/csv" --data-binary @candidates.csv
Because there is no form to parse, the caller is checked before a single byte of the file
is read, and the size limit is enforced while the body streams in.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError

from app.access import Access, get_access
from app.database import set_region_context
from app.importing.reading import BadFileError
from app.importing.service import run_import
from app.schemas import ImportReport

MAX_UPLOAD_BYTES = 5 * 1024 * 1024

router = APIRouter()


def too_large() -> HTTPException:
    """The error for a file over the size limit."""
    return HTTPException(
        status_code=413,
        detail=f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
    )


async def read_upload(
    request: Request,
    caller: Annotated[Access, Depends(get_access)],
) -> bytes:
    """Read the request body, refusing anything over the size limit.

    The caller parameter is not used here. It makes sure the caller is checked first
    (no header gives 401, an unknown recruiter gives 403).
    """
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise too_large()

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise too_large()
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/candidates/import", response_model=ImportReport)
def import_candidates(
    caller: Annotated[Access, Depends(get_access)],
    content: Annotated[bytes, Depends(read_upload)],
    filename: Annotated[str, Query(max_length=255)] = "candidates.csv",
) -> ImportReport:
    """Import a candidates CSV (any known recruiter). Everything is saved in one transaction.

    An import is a bulk load of the whole file, so it runs with all regions (not the
    caller's). Reading candidates stays limited to the caller's regions.
    """
    set_region_context(caller.session, ["*"])
    try:
        return run_import(caller.session, content, filename, caller.recruiter_id)
    except BadFileError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except IntegrityError as error:
        raise HTTPException(
            status_code=409, detail="The data changed during the import. Please try again."
        ) from error