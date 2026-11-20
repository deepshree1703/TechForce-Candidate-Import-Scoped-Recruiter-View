"""API tests for POST /api/v1/candidates/import, using the real candidates_import.csv and recruiters.csv.

Callers: R-101 is Dana Whitmore (admin), R-102 is Caleb Nguyen (a recruiter, US-MW and US-NE).
What the import stored is checked directly in the database, as the owner (who sees every row).
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.importing.row import CSV_COLUMNS

ADMIN = {"X-Recruiter-Id": "R-101"}
RECRUITER = {"X-Recruiter-Id": "R-102"}

# The rows rejected from the real file: (row number, candidate id, reason).
EXPECTED_REJECTED = [
    (34, "C-1033", "email: invalid"),
    (35, "C-1034", "email: invalid"),
    (36, "C-1035", "email: missing"),
    (41, "C-1040", "applied_date: impossible date"),
    (46, "C-1045", "region_code: invalid"),
    (48, "C-1047", "status: invalid"),
    (49, "C-1048", "status: invalid"),
    (52, "C-1010", "candidate_id collision"),
    (53, "C-1051", "region_code: missing"),
]

HEADER_WITHOUT_EMAIL = ",".join(column for column in CSV_COLUMNS if column != "email")


@pytest.fixture
def db(api_owner_engine: Engine) -> Engine:
    """The owner engine, used to look at what the import stored."""
    return api_owner_engine


def import_csv(
    client: Any,
    content: bytes,
    headers: dict[str, str] = ADMIN,
    filename: str = "candidates_import.csv",
) -> Any:
    """Send a CSV to the import endpoint as the given caller."""
    return client.post("/api/v1/candidates/import", content=content, headers=headers, params={"filename": filename})


def run_sql(engine: Engine, query: str, **params: Any) -> list[Any]:
    """Run a query as the owner and return all rows."""
    with engine.connect() as connection:
        return connection.execute(text(query), params).all()


def count_rows(engine: Engine, table: str) -> int:
    """Count the rows in a table."""
    return run_sql(engine, f"SELECT count(*) FROM {table}")[0][0]


def get_candidate(engine: Engine, candidate_id: str) -> Any | None:
    """The stored candidate as a mapping of column name to value, or None if not stored."""
    rows = run_sql(engine, "SELECT * FROM candidates WHERE candidate_id = :id", id=candidate_id)
    return rows[0]._mapping if rows else None


def summary(items: list[dict[str, Any]]) -> list[tuple[int, str, str]]:
    """(row number, candidate id, reason) for each rejected item in a response."""
    return [(item["row_number"], item["candidate_id"], item["reason"]) for item in items]


# ---- the import itself ----


def test_report_numbers(client: Any, real_csv: bytes) -> None:
    """53 rows read: 41 imported, 3 merged, 9 rejected, with row numbers, ids and reasons."""
    response = import_csv(client, real_csv)
    assert response.status_code == 200
    body = response.json()
    assert (body["rows_read"], body["imported"], body["merged"]) == (53, 41, 3)
    assert summary(body["rejected"]) == EXPECTED_REJECTED
    assert all(set(item) == {"row_number", "candidate_id", "reason"} for item in body["rejected"])
    assert isinstance(body["run_id"], int)


def test_dedup_result_is_stored(client: Any, real_csv: bytes, db: Engine) -> None:
    """Duplicates are merged, the collision keeps the first person, and a tie goes to the earlier row."""
    import_csv(client, real_csv)
    assert count_rows(db, "candidates") == 41

    amara = get_candidate(db, "C-1016")
    assert (amara["first_name"], amara["last_name"]) == ("Amara", "Diallo")
    assert amara["phone"] == "917-555-9999"
    assert amara["salary_expectation"] == Decimal("110000.00")
    assert amara["applied_date"] == date(2026, 6, 20)
    assert amara["source"] == "Indeed"
    assert get_candidate(db, "C-1032") is None

    okafor = run_sql(db, "SELECT count(*) FROM candidates WHERE email = :e", e="daniel.okafor@gmail.com")
    assert okafor[0][0] == 1

    alicia = get_candidate(db, "C-1001")
    assert alicia["source"] == "LinkedIn"
    assert get_candidate(db, "C-1031") is None

    sofia = get_candidate(db, "C-1010")
    assert (sofia["first_name"], sofia["last_name"]) == ("Sofía", "Cárdenas")
    assert run_sql(db, "SELECT count(*) FROM candidates WHERE email = 'becca.storm@gmail.com'")[0][0] == 0


def test_invalid_email_rows_are_rejected_and_not_stored(client: Any, real_csv: bytes, db: Engine) -> None:
    """Rows with [at] instead of @, no @, or no email at all are reported and never saved."""
    reasons = {item["candidate_id"]: item["reason"] for item in import_csv(client, real_csv).json()["rejected"]}
    assert reasons["C-1033"] == "email: invalid"
    assert reasons["C-1034"] == "email: invalid"
    assert reasons["C-1035"] == "email: missing"
    stored = run_sql(db, "SELECT count(*) FROM candidates WHERE candidate_id IN ('C-1033', 'C-1034', 'C-1035')")
    assert stored[0][0] == 0


def test_injection_rows_are_stored_as_plain_text(client: Any, real_csv: bytes, db: Engine) -> None:
    """The SQL-looking rows are imported as plain text, and the tables are still there."""
    assert import_csv(client, real_csv).status_code == 200
    assert get_candidate(db, "C-1036")["last_name"] == "O'Connor'); DROP TABLE candidates;--"
    assert get_candidate(db, "C-1037")["notes"] == "' OR '1'='1"
    assert run_sql(db, "SELECT to_regclass('public.candidates') IS NOT NULL")[0][0] is True
    assert run_sql(db, "SELECT to_regclass('public.import_runs') IS NOT NULL")[0][0] is True
    assert count_rows(db, "candidates") == 41


def test_odd_dates_and_regions(client: Any, real_csv: bytes, db: Engine) -> None:
    """Other date formats and region spellings are cleaned; impossible or unknown ones are rejected."""
    body = import_csv(client, real_csv).json()
    reasons = {item["candidate_id"]: item["reason"] for item in body["rejected"]}

    assert get_candidate(db, "C-1038")["applied_date"] == date(2026, 6, 30)  # 06/30/2026
    assert get_candidate(db, "C-1039")["applied_date"] == date(2026, 5, 14)  # 14-May-2026
    assert get_candidate(db, "C-1041")["applied_date"] is None  # empty date
    assert get_candidate(db, "C-1042")["region_code"] == "US-MW"  # us-mw
    assert get_candidate(db, "C-1043")["region_code"] == "CO-BOG"  # " CO-BOG "
    assert get_candidate(db, "C-1044")["region_code"] == "US-W"  # USW
    assert get_candidate(db, "C-1046")["status"] == "active"  # ACTIVE
    assert get_candidate(db, "C-1046")["salary_expectation"] == Decimal("85000.00")  # 85k

    rejected = {
        "C-1040": "applied_date: impossible date",
        "C-1045": "region_code: invalid",
        "C-1051": "region_code: missing",
    }
    for candidate_id, reason in rejected.items():
        assert reasons[candidate_id] == reason
        assert get_candidate(db, candidate_id) is None


def test_unicode_and_multiline_text_are_stored_exactly(client: Any, real_csv: bytes, db: Engine) -> None:
    """Accented names and a note with line breaks come back exactly as they were in the file."""
    import_csv(client, real_csv)
    nguyen = get_candidate(db, "C-1008")
    assert (nguyen["first_name"], nguyen["last_name"]) == ("Nguyễn", "Thị Hoa")
    assert get_candidate(db, "C-1006")["first_name"] == "Tomás"
    assert get_candidate(db, "C-1015")["last_name"] == "Müller"
    assert get_candidate(db, "C-1044")["last_name"] == "Trần"
    notes = get_candidate(db, "C-1050")["notes"]
    assert notes.startswith("Interview notes:")
    assert "\n" in notes
    assert "Round 2 pending scheduling." in notes


def test_reimport_changes_nothing(client: Any, real_csv: bytes, db: Engine) -> None:
    """Importing the same file again writes nothing, but is still saved as a run."""
    first = import_csv(client, real_csv)
    before = [tuple(row) for row in run_sql(db, "SELECT * FROM candidates ORDER BY candidate_id")]

    second = import_csv(client, real_csv)
    assert second.status_code == 200
    body = second.json()
    assert (body["rows_read"], body["imported"], body["merged"]) == (53, 0, 44)
    assert body["rejected"] == first.json()["rejected"]

    after = [tuple(row) for row in run_sql(db, "SELECT * FROM candidates ORDER BY candidate_id")]
    assert after == before  # every column, including created_at and updated_at
    runs = run_sql(db, "SELECT imported_count, merged_count, rejected_count FROM import_runs ORDER BY id")
    assert [tuple(run) for run in runs] == [(41, 3, 9), (0, 44, 9)]


def test_run_is_saved_with_raw_rejected_rows(client: Any, real_csv: bytes, db: Engine) -> None:
    """The saved run has who ran it, the file name, the counts and the raw cells of rejected rows."""
    response = import_csv(client, real_csv, filename="clients.csv")
    run = run_sql(db, "SELECT id, filename, imported_by, imported_count, merged_count, rejected_count, report FROM import_runs")[0]
    assert run.id == response.json()["run_id"]
    assert (run.filename, run.imported_by) == ("clients.csv", "R-101")
    assert (run.imported_count, run.merged_count, run.rejected_count) == (41, 3, 9)

    rejected = run.report["rejected"]
    assert len(rejected) == 9
    collision = next(item for item in rejected if item["reason"] == "candidate_id collision")
    assert collision["raw"]["first_name"] == "Becca"
    assert collision["raw"]["email"] == "becca.storm@gmail.com"
    bad_email = next(item for item in rejected if item["candidate_id"] == "C-1033")
    assert bad_email["raw"]["email"] == "marcus.reed[at]gmail.com"


# ---- errors ----


def test_missing_header_is_401(client: Any, real_csv: bytes, db: Engine) -> None:
    """No X-Recruiter-Id header means 401, and nothing is saved."""
    response = import_csv(client, real_csv, headers={})
    assert response.status_code == 401
    assert count_rows(db, "candidates") == 0
    assert count_rows(db, "import_runs") == 0


def test_unknown_recruiter_is_403(client: Any, real_csv: bytes, db: Engine) -> None:
    """An id that is not a recruiter means 403 (never an empty 200), and nothing is saved."""
    response = import_csv(client, real_csv, headers={"X-Recruiter-Id": "R-999"})
    assert response.status_code == 403
    assert count_rows(db, "candidates") == 0


def test_non_admin_recruiter_can_import_everything(client: Any, real_csv: bytes, db: Engine) -> None:
    """The brief has no admin-only rule: any known recruiter can import, and all rows are saved."""
    response = import_csv(client, real_csv, headers=RECRUITER)
    assert response.status_code == 200
    assert response.json()["imported"] == 41
    assert count_rows(db, "candidates") == 41


@pytest.mark.parametrize(
    ("content", "detail_part"),
    [
        pytest.param(b"", "empty", id="empty-file"),
        pytest.param((HEADER_WITHOUT_EMAIL + "\n").encode("utf-8"), "email", id="missing-column"),
        pytest.param(b"candidate_id\n\xe9\n", "UTF-8", id="not-utf-8"),
    ],
)
def test_bad_file_is_400(client: Any, db: Engine, content: bytes, detail_part: str) -> None:
    """An empty file, a file without a required column, or a non-UTF-8 file gives 400 and saves nothing."""
    response = import_csv(client, content)
    assert response.status_code == 400
    assert detail_part in response.json()["detail"]
    assert count_rows(db, "import_runs") == 0


def test_too_large_is_413(client: Any, db: Engine, oversized_body: bytes) -> None:
    """A file over the limit is refused with 413 and nothing is saved."""
    response = import_csv(client, oversized_body)
    assert response.status_code == 413
    assert count_rows(db, "import_runs") == 0


def test_too_large_without_content_length_is_413(client: Any, db: Engine) -> None:
    """The limit also holds when the size is not announced up front (a chunked upload)."""
    chunks = (b"x" * 1_000_000 for _ in range(6))
    response = client.post("/api/v1/candidates/import", content=chunks, headers=ADMIN)
    assert response.status_code == 413
    assert count_rows(db, "import_runs") == 0


def test_auth_is_checked_before_the_file_is_read(client: Any, oversized_body: bytes) -> None:
    """A caller with no header gets 401 even when the file is too large, so the file is never read."""
    response = import_csv(client, oversized_body, headers={})
    assert response.status_code == 401


def test_failure_after_writing_rolls_everything_back(
    client: Any, real_csv: bytes, db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If saving the run fails after the candidates were written, no candidate is kept."""

    def fail(*args: Any, **kwargs: Any) -> int:
        """Stand in for save_run and fail."""
        raise RuntimeError("boom")

    monkeypatch.setattr("app.importing.service.save_run", fail)
    with pytest.raises(RuntimeError, match="boom"):
        import_csv(client, real_csv)
    assert count_rows(db, "candidates") == 0
    assert count_rows(db, "import_runs") == 0