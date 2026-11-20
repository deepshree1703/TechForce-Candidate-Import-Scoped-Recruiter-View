"""The database write layer for imports: read what exists, upsert in chunks, save the run."""

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.importing.dedup import MERGE_FIELDS, ImportPlan
from app.importing.row import CSV_COLUMNS, CandidateRow
from app.models import Candidate, ImportRun

# 1000 rows x 12 columns = 12,000 values per statement, far under PostgreSQL's limit of 65,535.
CHUNK_SIZE = 1000


def fetch_existing(session: Session, ids: list[str], emails: list[str]) -> dict[str, CandidateRow]:
    """Load, with one query, every candidate whose id or email appears in the file.

    The ids and emails travel as two array parameters, so a large file cannot hit the
    limit on the number of query parameters.
    """
    if not ids and not emails:
        return {}
    columns = [getattr(Candidate, name) for name in CSV_COLUMNS]
    match = text("candidate_id = ANY(:ids) OR email = ANY(:emails)").bindparams(ids=ids, emails=emails)
    rows = session.execute(select(*columns).where(match)).all()
    return {row.candidate_id: CandidateRow.model_construct(**dict(row._mapping)) for row in rows}


def write_records(session: Session, records: list[CandidateRow]) -> None:
    """Upsert the records in chunks, one multi-row statement per chunk (never one per row)."""
    for start in range(0, len(records), CHUNK_SIZE):
        chunk = [record.model_dump() for record in records[start : start + CHUNK_SIZE]]
        statement = insert(Candidate).values(chunk)
        changes = {field: getattr(statement.excluded, field) for field in MERGE_FIELDS}
        changes["updated_at"] = func.now()
        session.execute(statement.on_conflict_do_update(index_elements=[Candidate.candidate_id], set_=changes))


def save_run(session: Session, filename: str, imported_by: str, plan: ImportPlan) -> int:
    """Save this run with its full report, including the raw cells of every rejected row."""
    report = {
        "rows_read": plan.rows_read,
        "imported": plan.imported,
        "merged": plan.merged,
        "written": len(plan.to_write),
        "rejected": [
            {
                "row_number": row.row_number,
                "candidate_id": row.candidate_id,
                "reason": row.reason,
                "raw": row.raw,
            }
            for row in plan.rejected
        ],
    }
    run = ImportRun(
        filename=filename,
        imported_by=imported_by,
        imported_count=plan.imported,
        merged_count=plan.merged,
        rejected_count=len(plan.rejected),
        report=report,
    )
    session.add(run)
    session.flush()
    return run.id