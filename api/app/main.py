"""Creates the FastAPI app, defines the health check and mounts the routes."""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_session
from app.routes import candidates, imports, recruiters

app = FastAPI(title="Recruiting Platform API")
API_PREFIX = "/api/v1"
app.include_router(imports.router, prefix=API_PREFIX)
app.include_router(candidates.router, prefix=API_PREFIX)
app.include_router(recruiters.router, prefix=API_PREFIX)


@app.get("/health")
def health(session: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
    """Return ok when the API is running and the database answers."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error
    return {"status": "ok", "database": "ok"}