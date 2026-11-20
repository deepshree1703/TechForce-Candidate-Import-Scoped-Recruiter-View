"""Dedup and merge: works out what an import should write, with no database involved.

Input: the CSV bytes and the records that already exist (candidate_id -> CandidateRow).
Output: an ImportPlan with the records to write, the counts and the rejected rows.

Rules:
- The email identifies a person. A row whose email is already known (in the database or
  in an earlier row) is merged into that record, which keeps its id.
- A row whose candidate_id is already used by a record with a different email is rejected
  as "candidate_id collision" (the first one wins).
- In a merge the newer applied_date wins field by field. A tie, or a missing date, goes to
  the earlier record. An empty value never replaces a real one, and a name that is only an
  initial ("A.") never replaces a full name.
- A record that a merge leaves unchanged is not written, so importing the same file twice
  writes nothing the second time.

"Earlier" means seen first: a record already in the database, otherwise the earlier row.
"""

import re
from dataclasses import dataclass
from typing import Any

from app.importing.reading import read_rows
from app.importing.row import CSV_COLUMNS, CandidateRow, RowRejected, parse_row

COLLISION_REASON = "candidate_id collision"

NAME_FIELDS = ("first_name", "last_name")

# Every field a merge can change: all of them except the id and the email.
MERGE_FIELDS = tuple(column for column in CSV_COLUMNS if column not in ("candidate_id", "email"))

# An initial is a single letter with an optional period: "A." or "A".
INITIAL_PATTERN = re.compile(r"[^\W\d_]\.?")


@dataclass(frozen=True)
class RejectedRow:
    """A row that was not imported: its number (data rows from 1), id, reason and raw cells."""

    row_number: int
    candidate_id: str | None
    reason: str
    raw: dict[str, Any]


@dataclass
class ImportPlan:
    """What an import would do.

    Every row that was read is either imported (a new candidate), merged (into a candidate
    that is already known) or rejected. to_write holds only the records that are new or
    changed, in file order.
    """

    rows_read: int
    to_write: list[CandidateRow]
    imported: int
    merged: int
    rejected: list[RejectedRow]


def is_initial(name: str) -> bool:
    """True when the name is just an initial, like 'A.' or 'D'."""
    return INITIAL_PATTERN.fullmatch(name) is not None


def pick(winner_value: Any, other_value: Any, is_name: bool) -> Any:
    """Choose a field value: the winner's, unless it is empty or (for names) only an initial."""
    if winner_value is None:
        return other_value
    if other_value is None:
        return winner_value
    if is_name and is_initial(winner_value) and not is_initial(other_value):
        return other_value
    return winner_value


def merge_records(earlier: CandidateRow, later: CandidateRow) -> CandidateRow:
    """Merge a new row (later) into the record seen first (earlier); the earlier id is kept."""
    later_is_newer = later.applied_date is not None and (
        earlier.applied_date is None or later.applied_date > earlier.applied_date
    )
    winner, other = (later, earlier) if later_is_newer else (earlier, later)
    values = {
        field: pick(getattr(winner, field), getattr(other, field), field in NAME_FIELDS)
        for field in MERGE_FIELDS
    }
    return earlier.model_copy(update=values)


def make_rejected(number: int, raw: dict[str | None, Any], reason: str) -> RejectedRow:
    """Build the report entry for a rejected row. Cells beyond the header go under '_extra'."""
    candidate_id = (raw.get("candidate_id") or "").strip() or None
    safe_raw = {("_extra" if key is None else key): value for key, value in raw.items()}
    return RejectedRow(row_number=number, candidate_id=candidate_id, reason=reason, raw=safe_raw)


def plan_rows(
    raw_rows: list[dict[str | None, Any]], existing: dict[str, CandidateRow]
) -> ImportPlan:
    """Validate and merge the raw rows against the existing records.

    existing maps candidate_id to a record. It must contain every database record whose
    candidate_id or email appears in the file, because that is all this function can see.
    """
    records = dict(existing)
    id_by_email = {record.email: record_id for record_id, record in existing.items()}
    touched: dict[str, None] = {}  # ids of records created or merged into, in order
    rejected: list[RejectedRow] = []
    imported = 0
    merged = 0

    for number, raw in enumerate(raw_rows, start=1):
        try:
            row = parse_row(raw)
        except RowRejected as error:
            rejected.append(make_rejected(number, raw, error.reason))
            continue

        # The id is taken by someone with a different email: the first one wins.
        holder = records.get(row.candidate_id)
        if holder is not None and holder.email != row.email:
            rejected.append(make_rejected(number, raw, COLLISION_REASON))
            continue

        known_id = id_by_email.get(row.email)
        if known_id is None:
            records[row.candidate_id] = row
            id_by_email[row.email] = row.candidate_id
            touched[row.candidate_id] = None
            imported += 1
        else:
            records[known_id] = merge_records(records[known_id], row)
            touched[known_id] = None
            merged += 1

    # Only records that are new, or end up different from what the database already has.
    to_write = [
        records[record_id] for record_id in touched if records[record_id] != existing.get(record_id)
    ]
    return ImportPlan(
        rows_read=len(raw_rows),
        to_write=to_write,
        imported=imported,
        merged=merged,
        rejected=rejected,
    )


def plan_import(content: bytes, existing: dict[str, CandidateRow]) -> ImportPlan:
    """Read the CSV bytes and plan the import. Raises BadFileError if the file is unusable."""
    return plan_rows(read_rows(content), existing)