"""Tests for merging and dedup, on the real candidates_import.csv and on small examples."""

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.importing.dedup import ImportPlan, merge_records, plan_import, plan_rows
from app.importing.row import CandidateRow, parse_row

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))

# The rows we expect to be rejected from the real file: (row number, candidate id, reason).
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

# A clean row for the small examples. Tests change only what they care about.
BASE_ROW = {
    "candidate_id": "C-1",
    "first_name": "Amara",
    "last_name": "Diallo",
    "email": "amara@example.com",
    "phone": "111",
    "region_code": "US-NE",
    "desired_role": "Full-Stack Engineer",
    "salary_expectation": "100000",
    "applied_date": "2026-06-01",
    "status": "Active",
    "source": "Referral",
    "notes": "first note",
}


def make_raw(**changes: str) -> dict[Any, Any]:
    """A raw CSV row (all text), based on BASE_ROW."""
    return {**BASE_ROW, **changes}


def make_record(**changes: str) -> CandidateRow:
    """A clean, validated record, based on BASE_ROW."""
    return parse_row(make_raw(**changes))


def written(plan: ImportPlan) -> dict[str, CandidateRow]:
    """The records a plan would write, by candidate id."""
    return {record.candidate_id: record for record in plan.to_write}


def rejected_summary(plan: ImportPlan) -> list[tuple[int, str | None, str]]:
    """(row number, candidate id, reason) for each rejected row."""
    return [(row.row_number, row.candidate_id, row.reason) for row in plan.rejected]


@pytest.fixture(scope="module")
def real_csv() -> bytes:
    """The bytes of the real data/candidates_import.csv file."""
    path = DATA_DIR / "candidates_import.csv"
    if not path.exists():
        pytest.fail(f"{path} not found. Put candidates_import.csv in the data folder.")
    return path.read_bytes()


@pytest.fixture(scope="module")
def first_run(real_csv: bytes) -> ImportPlan:
    """The plan for importing the real file into an empty database."""
    return plan_import(real_csv, {})


# ---- the real file ----


def test_counts_on_the_real_file(first_run: ImportPlan) -> None:
    """53 rows: 41 new candidates, 3 merged into others, 9 rejected, 41 records to write."""
    assert first_run.rows_read == 53
    assert first_run.imported == 41
    assert first_run.merged == 3
    assert len(first_run.rejected) == 9
    assert first_run.imported + first_run.merged + len(first_run.rejected) == first_run.rows_read
    assert len(first_run.to_write) == 41
    assert len({record.candidate_id for record in first_run.to_write}) == 41
    assert len({record.email for record in first_run.to_write}) == 41


def test_rejected_rows_on_the_real_file(first_run: ImportPlan) -> None:
    """Each rejected row has the right data-row number, candidate id and reason."""
    assert rejected_summary(first_run) == EXPECTED_REJECTED


def test_rejected_row_keeps_its_raw_cells(first_run: ImportPlan) -> None:
    """The collision row is saved with its original cells for the report."""
    collision = next(row for row in first_run.rejected if row.reason == "candidate_id collision")
    assert collision.raw["first_name"] == "Becca"
    assert collision.raw["email"] == "becca.storm@gmail.com"


def test_exact_duplicate_is_merged_without_change(first_run: ImportPlan) -> None:
    """C-1004 appears twice, word for word. It becomes one record and is not rejected."""
    okafor = [record for record in first_run.to_write if record.email == "daniel.okafor@gmail.com"]
    assert len(okafor) == 1
    assert okafor[0].candidate_id == "C-1004"
    assert okafor[0].salary_expectation == Decimal("97500")
    assert okafor[0].applied_date == date(2026, 5, 19)
    assert 31 not in [row.row_number for row in first_run.rejected]


def test_same_email_with_different_details_is_merged(first_run: ImportPlan) -> None:
    """C-1032 (newer) is folded into C-1016: its details win and the earlier id is kept."""
    records = written(first_run)
    amara = records["C-1016"]
    assert "C-1032" not in records
    assert amara.phone == "917-555-9999"
    assert amara.salary_expectation == Decimal("110000")
    assert amara.applied_date == date(2026, 6, 20)
    assert amara.source == "Indeed"
    assert amara.notes == "Which record wins?"
    assert amara.region_code == "US-NE"


def test_initial_does_not_replace_a_full_name(first_run: ImportPlan) -> None:
    """C-1032 is 'A. Diallo' and newer, but the merged record keeps 'Amara'."""
    amara = written(first_run)["C-1016"]
    assert (amara.first_name, amara.last_name) == ("Amara", "Diallo")


def test_id_collision_keeps_the_first_person(first_run: ImportPlan) -> None:
    """C-1010 stays Sofía Cárdenas. Becca Storm (same id, different email) is not imported."""
    records = written(first_run)
    assert (records["C-1010"].first_name, records["C-1010"].last_name) == ("Sofía", "Cárdenas")
    assert all(record.email != "becca.storm@gmail.com" for record in first_run.to_write)


def test_tie_goes_to_the_earlier_record(first_run: ImportPlan) -> None:
    """C-1031 has the same applied date as C-1001, so C-1001's source and notes stay."""
    records = written(first_run)
    alicia = records["C-1001"]
    assert "C-1031" not in records
    assert alicia.email == "alicia.trent@gmail.com"
    assert alicia.source == "LinkedIn"
    assert alicia.notes == "Strong React portfolio"


def test_empty_values_never_overwrite_real_ones(real_csv: bytes) -> None:
    """A newer row for Amara with empty cells adds its date and source but wipes nothing."""
    extra_row = b"C-9001,Amara,Diallo,amara.diallo@gmail.com,,US-NE,,,2026-07-01,Active,Careers page,\n"
    plan = plan_import(real_csv.rstrip(b"\r\n") + b"\n" + extra_row, {})
    records = written(plan)
    amara = records["C-1016"]
    assert "C-9001" not in records
    assert plan.merged == 4
    assert amara.applied_date == date(2026, 7, 1)
    assert amara.source == "Careers page"
    assert amara.phone == "917-555-9999"
    assert amara.salary_expectation == Decimal("110000")
    assert amara.desired_role == "Full-Stack Engineer"
    assert amara.notes == "Which record wins?"


def test_special_text_survives_the_whole_pipeline(first_run: ImportPlan) -> None:
    """SQL-looking text, accents and line breaks come out of the plan exactly as written."""
    records = written(first_run)
    assert records["C-1036"].last_name == "O'Connor'); DROP TABLE candidates;--"
    assert records["C-1037"].notes == "' OR '1'='1"
    assert (records["C-1008"].first_name, records["C-1008"].last_name) == ("Nguyễn", "Thị Hoa")
    assert "Round 2 pending scheduling." in records["C-1050"].notes


def test_second_run_on_its_own_output_changes_nothing(real_csv: bytes, first_run: ImportPlan) -> None:
    """Feeding the first run's records back in: nothing to write, nothing new, same rejects."""
    existing = {record.candidate_id: record for record in first_run.to_write}
    second = plan_import(real_csv, existing)
    assert second.to_write == []
    assert second.imported == 0
    assert second.merged == first_run.imported + first_run.merged
    assert second.rejected == first_run.rejected


def test_newer_existing_record_is_not_overwritten(real_csv: bytes) -> None:
    """A complete database record with a newer date beats the file's older row, so no write."""
    existing = {
        "C-1002": make_record(
            candidate_id="C-1002",
            first_name="Marcus",
            last_name="Bellamy",
            email="m.bellamy@outlook.com",
            phone="000",
            region_code="US-MW",
            desired_role="Backend Engineer",
            salary_expectation="90000",
            applied_date="2026-12-01",
            status="Screening",
            source="Referral",
            notes="kept",
        )
    }
    plan = plan_import(real_csv, existing)
    assert "C-1002" not in written(plan)
    assert plan.imported == 40
    assert plan.merged == 4


def test_older_existing_record_is_updated(real_csv: bytes) -> None:
    """The file's newer row updates an older database record, and empty cells wipe nothing."""
    existing = {
        "C-1003": make_record(
            candidate_id="C-1003",
            first_name="Priya",
            last_name="Raman",
            email="priya.raman@yahoo.com",
            phone="",
            region_code="US-MW",
            desired_role="Data Engineer",
            salary_expectation="",
            applied_date="2026-01-01",
            status="Active",
            source="",
            notes="old note",
        )
    }
    updated = written(plan_import(real_csv, existing))["C-1003"]
    assert updated.phone == "(312) 555-0165"
    assert updated.salary_expectation == Decimal("102000")
    assert updated.status == "interviewing"
    assert updated.source == "Indeed"
    assert updated.applied_date == date(2026, 5, 18)
    assert updated.notes == "old note"


def test_collision_with_an_existing_record(real_csv: bytes) -> None:
    """The file's C-1005 is rejected when the database already has C-1005 for someone else."""
    existing = {"C-1005": make_record(candidate_id="C-1005", email="someone.else@example.com")}
    plan = plan_import(real_csv, existing)
    assert (5, "C-1005", "candidate_id collision") in rejected_summary(plan)


def test_same_email_under_another_id_in_the_database(real_csv: bytes) -> None:
    """The file's C-1002 is merged into the database record that has the same email."""
    existing = {
        "C-0500": make_record(candidate_id="C-0500", email="m.bellamy@outlook.com", applied_date="2026-01-01")
    }
    records = written(plan_import(real_csv, existing))
    assert "C-1002" not in records
    assert records["C-0500"].first_name == "Marcus"
    assert records["C-0500"].applied_date == date(2026, 5, 16)


# ---- the merge rules, on small examples ----


@pytest.mark.parametrize(
    ("earlier", "later", "field", "expected"),
    [
        pytest.param(
            {"phone": "111", "applied_date": "2026-05-01"},
            {"phone": "222", "applied_date": "2026-06-01"},
            "phone",
            "222",
            id="newer-later-row-wins",
        ),
        pytest.param(
            {"phone": "111", "applied_date": "2026-06-01"},
            {"phone": "222", "applied_date": "2026-05-01"},
            "phone",
            "111",
            id="older-later-row-loses",
        ),
        pytest.param({"phone": "111"}, {"phone": "222"}, "phone", "111", id="tie-goes-to-earlier"),
        pytest.param(
            {"phone": "111", "applied_date": ""},
            {"phone": "222", "applied_date": ""},
            "phone",
            "111",
            id="both-dates-empty-goes-to-earlier",
        ),
        pytest.param(
            {"phone": "111", "applied_date": ""},
            {"phone": "222"},
            "phone",
            "222",
            id="only-later-has-a-date",
        ),
        pytest.param(
            {"phone": "111"},
            {"phone": "222", "applied_date": ""},
            "phone",
            "111",
            id="only-earlier-has-a-date",
        ),
        pytest.param(
            {"phone": "111", "applied_date": "2026-05-01"},
            {"phone": "", "applied_date": "2026-06-01"},
            "phone",
            "111",
            id="empty-never-overwrites",
        ),
        pytest.param(
            {"phone": "", "applied_date": "2026-06-01"},
            {"phone": "222", "applied_date": "2026-05-01"},
            "phone",
            "222",
            id="empty-is-filled-from-the-other",
        ),
        pytest.param(
            {"first_name": "Amara", "applied_date": "2026-05-01"},
            {"first_name": "A.", "applied_date": "2026-06-01"},
            "first_name",
            "Amara",
            id="newer-initial-does-not-replace-full-name",
        ),
        pytest.param(
            {"first_name": "A.", "applied_date": "2026-06-01"},
            {"first_name": "Amara", "applied_date": "2026-05-01"},
            "first_name",
            "Amara",
            id="newer-initial-in-earlier-record-gives-way-to-full-name",
        ),
        pytest.param(
            {"last_name": "Diallo", "applied_date": "2026-05-01"},
            {"last_name": "Diallo-Sow", "applied_date": "2026-06-01"},
            "last_name",
            "Diallo-Sow",
            id="newer-full-name-replaces-full-name",
        ),
        pytest.param(
            {"first_name": "A.", "applied_date": "2026-05-01"},
            {"first_name": "B.", "applied_date": "2026-06-01"},
            "first_name",
            "B.",
            id="two-initials-newer-wins",
        ),
        pytest.param(
            {"last_name": "Diallo", "applied_date": "2026-05-01"},
            {"last_name": "D", "applied_date": "2026-06-01"},
            "last_name",
            "Diallo",
            id="last-name-initial-without-period",
        ),
    ],
)
def test_merge_rules(
    earlier: dict[str, str], later: dict[str, str], field: str, expected: str
) -> None:
    """Newer date wins per field; ties and missing dates go to the earlier record; empties and initials lose."""
    merged = merge_records(make_record(**earlier), make_record(candidate_id="C-2", **later))
    assert getattr(merged, field) == expected


def test_merge_keeps_the_earlier_id_and_email() -> None:
    """Whatever wins, the merged record keeps the earlier record's id and email."""
    merged = merge_records(make_record(), make_record(candidate_id="C-2"))
    assert merged.candidate_id == "C-1"
    assert merged.email == "amara@example.com"


# ---- the plan, on small examples ----


def test_rows_are_numbered_from_one() -> None:
    """Row numbers count data rows from 1, and the counts add up."""
    rows = [
        make_raw(candidate_id="C-1", email="a@example.com"),
        make_raw(candidate_id="C-2", email="not-an-email"),
        make_raw(candidate_id="C-3", email="c@example.com"),
    ]
    plan = plan_rows(rows, {})
    assert rejected_summary(plan) == [(2, "C-2", "email: invalid")]
    assert (plan.rows_read, plan.imported, plan.merged) == (3, 2, 0)


def test_first_row_wins_an_id_collision() -> None:
    """Two different emails on one id: the first is kept, the second is rejected."""
    rows = [
        make_raw(candidate_id="C-1", email="a@example.com"),
        make_raw(candidate_id="C-1", email="b@example.com"),
    ]
    plan = plan_rows(rows, {})
    assert rejected_summary(plan) == [(2, "C-1", "candidate_id collision")]
    assert [record.email for record in plan.to_write] == ["a@example.com"]


def test_known_email_with_a_new_id_is_merged() -> None:
    """The same email under a second id is the same person, so the second id is dropped."""
    plan = plan_rows([make_raw(candidate_id="C-1"), make_raw(candidate_id="C-2")], {})
    assert (plan.imported, plan.merged) == (1, 1)
    assert [record.candidate_id for record in plan.to_write] == ["C-1"]


def test_id_held_by_another_email_is_a_collision() -> None:
    """Even when the email is known, using someone else's id is a collision."""
    rows = [
        make_raw(candidate_id="C-1", email="a@example.com"),
        make_raw(candidate_id="C-2", email="b@example.com"),
        make_raw(candidate_id="C-1", email="b@example.com"),
    ]
    plan = plan_rows(rows, {})
    assert rejected_summary(plan) == [(3, "C-1", "candidate_id collision")]


def test_unchanged_merge_is_not_written() -> None:
    """A row that matches a database record exactly is counted as merged but not written."""
    plan = plan_rows([make_raw()], {"C-1": make_record()})
    assert plan.to_write == []
    assert (plan.imported, plan.merged) == (0, 1)


def test_changed_merge_is_written() -> None:
    """A row that fills an empty value in a database record produces a write."""
    plan = plan_rows([make_raw()], {"C-1": make_record(phone="")})
    assert [record.phone for record in plan.to_write] == ["111"]


def test_records_are_written_in_file_order() -> None:
    """The records to write follow the order the people first appear in the file."""
    rows = [make_raw(candidate_id=f"C-{n}", email=f"p{n}@example.com") for n in (3, 1, 2)]
    plan = plan_rows(rows, {})
    assert [record.candidate_id for record in plan.to_write] == ["C-3", "C-1", "C-2"]


def test_rejected_raw_row_is_safe_for_json() -> None:
    """A row with extra cells is rejected and its raw cells can be saved as JSON."""
    raw = make_raw()
    raw[None] = ["left over"]
    plan = plan_rows([raw], {})
    assert rejected_summary(plan) == [(1, "C-1", "too many columns")]
    assert json.loads(json.dumps(plan.rejected[0].raw))["_extra"] == ["left over"]