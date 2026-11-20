"""Runs one whole import: read the file, plan the changes, write them and save the run.

Everything happens in the caller's transaction and is committed once at the end, so a
failure anywhere leaves the database exactly as it was.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.importing.cleaning import clean_email, clean_text
from app.importing.dedup import plan_rows
from app.importing.reading import read_rows
from app.importing.save import fetch_existing, save_run, write_records
from app.schemas import ImportReport, RejectedItem


def collect_keys(raw_rows: list[dict[str | None, Any]]) -> tuple[list[str], list[str]]:
    """Collect the candidate ids and emails in the file, so existing records can be loaded.

    This may collect a few more than the valid rows need, which is harmless.
    """
    ids: set[str] = set()
    emails: set[str] = set()
    for raw in raw_rows:
        candidate_id = clean_text(raw.get("candidate_id"))
        if candidate_id:
            ids.add(candidate_id)
        try:
            emails.add(clean_email(raw.get("email")))
        except ValueError:
            pass
    return sorted(ids), sorted(emails)


def run_import(session: Session, content: bytes, filename: str, imported_by: str) -> ImportReport:
    """Import the CSV bytes. Raises BadFileError for an unusable file (nothing is saved)."""
    raw_rows = read_rows(content)
    ids, emails = collect_keys(raw_rows)
    existing = fetch_existing(session, ids, emails)
    plan = plan_rows(raw_rows, existing)

    write_records(session, plan.to_write)
    # Read the run id before the commit: after it, the region setting is gone.
    run_id = save_run(session, filename, imported_by, plan)
    session.commit()

    return ImportReport(
        run_id=run_id,
        rows_read=plan.rows_read,
        imported=plan.imported,
        merged=plan.merged,
        rejected=[
            RejectedItem(row_number=row.row_number, candidate_id=row.candidate_id, reason=row.reason)
            for row in plan.rejected
        ],
    )