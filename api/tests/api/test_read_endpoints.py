"""Access tests for the read endpoints, using the real candidates_import.csv once.

The real file is imported one time for the whole module, as the admin R-101. After that
the tests only read. Expected numbers are not typed in: they come from plain SQL run as
the owner (who sees every row), so the API answer is checked against an independent path.

Callers: R-101 is the admin; R-102 is a recruiter limited to US-MW and US-NE.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.database import get_session

ADMIN_ID = "R-101"
RESTRICTED_ID = "R-102"
ALL_CANDIDATES = 41

# How many candidates contain a text (name, email or role), counted with plain SQL.
COUNT_CONTAINING = """
SELECT count(*) FROM candidates WHERE
    strpos(lower(concat_ws(' ', first_name, last_name)), lower(:term)) > 0
    OR strpos(lower(email), lower(:term)) > 0
    OR strpos(lower(coalesce(desired_role, '')), lower(:term)) > 0
"""


@pytest.fixture(scope="module")
def db(api_owner_engine: Engine) -> Engine:
    """The owner engine, which sees every row. Used for expected values."""
    return api_owner_engine


@pytest.fixture(scope="module")
def loaded(
    api_app_engine: Engine, api_owner_engine: Engine, real_recruiters: None, real_csv: bytes
) -> Iterator[Any]:
    """A test client for an API database where the real CSV has been imported once."""
    from fastapi.testclient import TestClient

    from app.main import app

    with api_owner_engine.begin() as connection:
        connection.execute(text("TRUNCATE candidates, import_runs RESTART IDENTITY"))

    def test_session() -> Iterator[Session]:
        """Give each request a session that logs in as the limited API user."""
        with Session(api_app_engine) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    api = TestClient(app)
    response = api.post(
        "/api/v1/candidates/import",
        content=real_csv,
        headers={"X-Recruiter-Id": ADMIN_ID},
        params={"filename": "candidates_import.csv"},
    )
    assert response.status_code == 200
    assert (response.json()["imported"], response.json()["merged"]) == (ALL_CANDIDATES, 3)
    yield api
    app.dependency_overrides.clear()


def run_sql(engine: Engine, query: str, **params: Any) -> list[Any]:
    """Run a query as the owner and return all rows."""
    with engine.connect() as connection:
        return connection.execute(text(query), params).all()


def count_where(engine: Engine, condition: str, **params: Any) -> int:
    """Count the candidates that match a SQL condition."""
    return run_sql(engine, f"SELECT count(*) FROM candidates WHERE {condition}", **params)[0][0]


def fetch(client: Any, path: str, recruiter: str = ADMIN_ID, **params: Any) -> Any:
    """GET a path as the given recruiter, with optional query parameters."""
    return client.get(path, headers={"X-Recruiter-Id": recruiter}, params=params)


def list_all(client: Any, recruiter: str) -> list[dict[str, Any]]:
    """Every candidate the recruiter can list (one page of 100 holds all 41)."""
    body = fetch(client, "/api/v1/candidates", recruiter, page_size=100).json()
    assert body["total"] == len(body["items"])
    return body["items"]


def regions_of(db: Engine, recruiter_id: str) -> list[str]:
    """The regions assigned to a recruiter, read from the database."""
    rows = run_sql(db, "SELECT assigned_regions FROM recruiters WHERE recruiter_id = :id", id=recruiter_id)
    return list(rows[0][0])


def candidate_outside(db: Engine, regions: list[str]) -> Any:
    """A candidate (id and email) whose region is not in the given regions."""
    rows = run_sql(
        db,
        "SELECT candidate_id, email, region_code FROM candidates "
        "WHERE NOT (region_code = ANY(:regions)) ORDER BY candidate_id",
        regions=regions,
    )
    assert rows, "the real data should have candidates outside this recruiter's regions"
    return rows[0]


def candidate_inside(db: Engine, regions: list[str]) -> Any:
    """A candidate (id and region) whose region is in the given regions."""
    rows = run_sql(
        db,
        "SELECT candidate_id, region_code FROM candidates "
        "WHERE region_code = ANY(:regions) ORDER BY candidate_id",
        regions=regions,
    )
    assert rows, "the real data should have candidates inside this recruiter's regions"
    return rows[0]


# ---- the recruiter list ----


def test_recruiters_list_is_open_and_minimal(loaded: Any, db: Engine) -> None:
    """The dropdown list needs no header and shows only id, name and role."""
    response = loaded.get("/api/v1/recruiters")
    assert response.status_code == 200
    body = response.json()
    expected = run_sql(db, "SELECT recruiter_id, full_name, role FROM recruiters ORDER BY recruiter_id")
    assert [(r["recruiter_id"], r["full_name"], r["role"]) for r in body] == [tuple(r) for r in expected]
    assert len(body) == 5
    assert all(set(r) == {"recruiter_id", "full_name", "role"} for r in body)


# ---- who sees what ----


def test_totals_per_recruiter(loaded: Any, db: Engine) -> None:
    """Each recruiter's total is the number of candidates in their regions; the admin sees all."""
    recruiters = run_sql(db, "SELECT recruiter_id, role, assigned_regions FROM recruiters ORDER BY recruiter_id")
    restricted_totals = []
    for recruiter in recruiters:
        response = fetch(loaded, "/api/v1/candidates", recruiter.recruiter_id, page_size=100)
        assert response.status_code == 200
        body = response.json()
        if recruiter.role == "admin":
            assert body["total"] == ALL_CANDIDATES
            continue
        regions = list(recruiter.assigned_regions)
        assert body["total"] == count_where(db, "region_code = ANY(:regions)", regions=regions)
        assert {item["region_code"] for item in body["items"]} <= set(regions)
        restricted_totals.append(body["total"])
    assert restricted_totals
    assert any(0 < total < ALL_CANDIDATES for total in restricted_totals)


def test_recruiter_list_never_contains_other_regions(loaded: Any, db: Engine) -> None:
    """The restricted recruiter's list holds no candidate from outside their regions."""
    regions = regions_of(db, RESTRICTED_ID)
    outside = candidate_outside(db, regions)
    items = list_all(loaded, RESTRICTED_ID)
    assert outside.candidate_id not in {item["candidate_id"] for item in items}
    assert {item["region_code"] for item in items} <= set(regions)


def test_recruiter_cannot_get_a_candidate_from_another_region(loaded: Any, db: Engine) -> None:
    """The detail of an out-of-region candidate is 404 for the restricted recruiter."""
    outside = candidate_outside(db, regions_of(db, RESTRICTED_ID))
    response = fetch(loaded, f"/api/v1/candidates/{outside.candidate_id}", RESTRICTED_ID)
    assert response.status_code == 404
    assert response.json()["detail"] == "Candidate not found"


def test_recruiter_can_get_a_candidate_from_their_region(loaded: Any, db: Engine) -> None:
    """The detail of an in-region candidate is 200, with every field."""
    regions = regions_of(db, RESTRICTED_ID)
    inside = candidate_inside(db, regions)
    response = fetch(loaded, f"/api/v1/candidates/{inside.candidate_id}", RESTRICTED_ID)
    assert response.status_code == 200
    body = response.json()
    assert body["candidate_id"] == inside.candidate_id
    assert body["region_code"] in regions
    assert {"phone", "salary_expectation", "source", "notes"} <= set(body)


def test_admin_can_get_any_candidate(loaded: Any, db: Engine) -> None:
    """The admin gets the out-of-region candidate that the recruiter could not, with all fields."""
    outside = candidate_outside(db, regions_of(db, RESTRICTED_ID))
    assert fetch(loaded, f"/api/v1/candidates/{outside.candidate_id}", ADMIN_ID).status_code == 200

    amara = fetch(loaded, "/api/v1/candidates/C-1016", ADMIN_ID).json()
    assert (amara["first_name"], amara["last_name"]) == ("Amara", "Diallo")
    assert amara["phone"] == "917-555-9999"
    assert amara["salary_expectation"] == "110000.00"
    assert amara["applied_date"] == "2026-06-20"
    assert amara["source"] == "Indeed"


def test_search_cannot_reach_other_regions(loaded: Any, db: Engine) -> None:
    """Searching for an out-of-region candidate's email finds them for the admin, not the recruiter."""
    outside = candidate_outside(db, regions_of(db, RESTRICTED_ID))
    as_admin = fetch(loaded, "/api/v1/candidates", ADMIN_ID, search=outside.email).json()
    as_recruiter = fetch(loaded, "/api/v1/candidates", RESTRICTED_ID, search=outside.email).json()
    assert outside.candidate_id in {item["candidate_id"] for item in as_admin["items"]}
    assert as_recruiter["total"] == 0
    assert as_recruiter["items"] == []


def test_unknown_candidate_is_404(loaded: Any) -> None:
    """An id that does not exist is 404, the same answer as an out-of-region one."""
    response = fetch(loaded, "/api/v1/candidates/C-9999", ADMIN_ID)
    assert response.status_code == 404


# ---- who is calling ----


@pytest.mark.parametrize("path", ["/api/v1/candidates", "/api/v1/candidates/C-1001"])
def test_missing_header_is_401(loaded: Any, path: str) -> None:
    """No X-Recruiter-Id header means 401."""
    assert loaded.get(path).status_code == 401


@pytest.mark.parametrize("path", ["/api/v1/candidates", "/api/v1/candidates/C-1001"])
def test_unknown_recruiter_is_403(loaded: Any, path: str) -> None:
    """An id that is not a recruiter means 403, never an empty 200."""
    assert fetch(loaded, path, "R-999").status_code == 403


# ---- bad input ----


@pytest.mark.parametrize(
    "params",
    [
        pytest.param({"page_size": 0}, id="page-size-zero"),
        pytest.param({"page_size": 101}, id="page-size-over-cap"),
        pytest.param({"page_size": -5}, id="page-size-negative"),
        pytest.param({"page_size": "abc"}, id="page-size-text"),
        pytest.param({"page": 0}, id="page-zero"),
        pytest.param({"page": -1}, id="page-negative"),
        pytest.param({"page": "abc"}, id="page-text"),
        pytest.param({"page": 100_001}, id="page-over-cap"),
        pytest.param({"status": "bogus"}, id="status-unknown"),
        pytest.param({"status": "ACTIVE"}, id="status-wrong-case"),
        pytest.param({"status": "on hold"}, id="status-not-in-set"),
        pytest.param({"search": "x" * 101}, id="search-too-long"),
    ],
)
def test_bad_query_is_422(loaded: Any, params: dict[str, Any]) -> None:
    """A bad page, page size, status or search text is refused with 422."""
    assert fetch(loaded, "/api/v1/candidates", ADMIN_ID, **params).status_code == 422


# ---- ordering and pagination ----


def test_order_is_newest_first_then_candidate_id(loaded: Any) -> None:
    """Newest applied date first, equal dates by candidate id, and no date at the very end."""
    items = list_all(loaded, ADMIN_ID)
    by_id = sorted(items, key=lambda item: item["candidate_id"])
    dated = sorted((i for i in by_id if i["applied_date"]), key=lambda i: i["applied_date"], reverse=True)
    undated = [i for i in by_id if not i["applied_date"]]
    assert undated, "the real data has candidates without an applied date"
    assert [i["candidate_id"] for i in items] == [i["candidate_id"] for i in dated + undated]


def test_pages_follow_the_same_order(loaded: Any) -> None:
    """Five pages of 10 add up to the full list, with no gaps and no repeats."""
    full = [item["candidate_id"] for item in list_all(loaded, ADMIN_ID)]
    seen: list[str] = []
    for page in range(1, 6):
        body = fetch(loaded, "/api/v1/candidates", ADMIN_ID, page=page, page_size=10).json()
        assert (body["page"], body["page_size"], body["total"]) == (page, 10, ALL_CANDIDATES)
        assert len(body["items"]) == (10 if page < 5 else 1)
        seen += [item["candidate_id"] for item in body["items"]]
    assert seen == full
    beyond = fetch(loaded, "/api/v1/candidates", ADMIN_ID, page=6, page_size=10).json()
    assert beyond["items"] == []
    assert beyond["total"] == ALL_CANDIDATES


def test_default_page_size_is_20(loaded: Any) -> None:
    """Without paging parameters the first 20 are returned."""
    body = fetch(loaded, "/api/v1/candidates", ADMIN_ID).json()
    assert (body["page"], body["page_size"], body["total"]) == (1, 20, ALL_CANDIDATES)
    assert len(body["items"]) == 20


# ---- status filter ----


@pytest.mark.parametrize("status", ["active", "screening", "interviewing", "withdrawn"])
def test_status_filter(loaded: Any, db: Engine, status: str) -> None:
    """The status filter returns exactly the candidates with that status."""
    body = fetch(loaded, "/api/v1/candidates", ADMIN_ID, status=status, page_size=100).json()
    assert body["total"] == count_where(db, "status = :status", status=status)
    assert all(item["status"] == status for item in body["items"])


def test_status_and_search_combine(loaded: Any, db: Engine) -> None:
    """Status and search both apply: the right status finds the person, another does not."""
    row = run_sql(db, "SELECT status FROM candidates WHERE email = 'daniel.okafor@gmail.com'")[0]
    other = "withdrawn" if row.status != "withdrawn" else "active"
    same = fetch(loaded, "/api/v1/candidates", ADMIN_ID, search="okafor", status=row.status).json()
    different = fetch(loaded, "/api/v1/candidates", ADMIN_ID, search="okafor", status=other).json()
    assert same["total"] >= 1
    assert different["total"] == 0


# ---- search ----


@pytest.mark.parametrize(
    ("term", "candidate_id"),
    [
        pytest.param("Nguyễn", "C-1008", id="first-name"),
        pytest.param("Thị Hoa", "C-1008", id="last-name-with-space"),
        pytest.param("Nguyễn Thị Hoa", "C-1008", id="full-name"),
        pytest.param("Tomás", "C-1006", id="accent-a"),
        pytest.param("Müller", "C-1015", id="umlaut"),
        pytest.param("Trần", "C-1044", id="vietnamese"),
    ],
)
def test_search_finds_unicode_names(loaded: Any, term: str, candidate_id: str) -> None:
    """Names with accents are found by searching for them with the accents."""
    body = fetch(loaded, "/api/v1/candidates", ADMIN_ID, search=term, page_size=100).json()
    assert candidate_id in {item["candidate_id"] for item in body["items"]}
    assert body["total"] < ALL_CANDIDATES


def test_unicode_names_come_back_exact(loaded: Any) -> None:
    """The JSON answer carries the Unicode name exactly as stored."""
    items = fetch(loaded, "/api/v1/candidates", ADMIN_ID, search="Nguyễn").json()["items"]
    match = next(item for item in items if item["candidate_id"] == "C-1008")
    assert (match["first_name"], match["last_name"]) == ("Nguyễn", "Thị Hoa")


@pytest.mark.parametrize("term", ["DANIEL.OKAFOR", "okafor@GMAIL.com"])
def test_search_ignores_case_and_matches_email(loaded: Any, term: str) -> None:
    """Search ignores case and looks in the email; the merged duplicate appears once."""
    body = fetch(loaded, "/api/v1/candidates", ADMIN_ID, search=term).json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "daniel.okafor@gmail.com"


def test_search_matches_role(loaded: Any, db: Engine) -> None:
    """A word from a desired role finds every candidate with that word in their role."""
    role = run_sql(
        db, "SELECT desired_role FROM candidates WHERE desired_role IS NOT NULL ORDER BY candidate_id LIMIT 1"
    )[0][0]
    word = role.split()[0]
    expected = run_sql(db, "SELECT candidate_id FROM candidates WHERE strpos(lower(desired_role), lower(:w)) > 0", w=word)
    found = fetch(loaded, "/api/v1/candidates", ADMIN_ID, search=word.upper(), page_size=100).json()["items"]
    assert {row.candidate_id for row in expected} <= {item["candidate_id"] for item in found}


def test_search_injection_text_is_just_text(loaded: Any, db: Engine) -> None:
    """SQL-looking search text is searched for as plain text, and nothing is dropped."""
    quote_drop = fetch(loaded, "/api/v1/candidates", ADMIN_ID, search="'; DROP TABLE candidates;--")
    assert quote_drop.status_code == 200
    assert quote_drop.json()["total"] == 0

    always_true = fetch(loaded, "/api/v1/candidates", ADMIN_ID, search="' OR '1'='1")
    assert always_true.status_code == 200
    assert always_true.json()["total"] == 0

    stored_name = fetch(loaded, "/api/v1/candidates", ADMIN_ID, search="O'Connor'); DROP TABLE candidates;--").json()
    assert [item["candidate_id"] for item in stored_name["items"]] == ["C-1036"]

    assert count_where(db, "true") == ALL_CANDIDATES
    assert fetch(loaded, "/api/v1/candidates", ADMIN_ID).json()["total"] == ALL_CANDIDATES


@pytest.mark.parametrize("term", ["%", "_", "%%", "Dan%", "d_niel", "\\", "/", "//"])
def test_search_wildcards_are_literal(loaded: Any, db: Engine, term: str) -> None:
    """%, _ and the escape characters match only themselves, never "anything"."""
    expected = run_sql(db, COUNT_CONTAINING, term=term)[0][0]
    assert expected < ALL_CANDIDATES, "this term should not match every row in the real data"
    body = fetch(loaded, "/api/v1/candidates", ADMIN_ID, search=term, page_size=100)
    assert body.status_code == 200
    assert body.json()["total"] == expected


# ---- the database itself ----


def test_raw_connection_without_a_setting_sees_nothing(loaded: Any, db: Engine, api_app_engine: Engine) -> None:
    """The limited login with no region setting gets no rows, even though 41 are stored.

    It uses the same connection pool the API requests used, so this also shows that no
    region setting leaks from one request to the next.
    """
    assert count_where(db, "true") == ALL_CANDIDATES
    with api_app_engine.connect() as connection:
        setting = connection.execute(text("SELECT current_setting('app.regions', true)")).scalar_one()
        assert setting in (None, "")
        assert connection.execute(text("SELECT count(*) FROM candidates")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM import_runs")).scalar_one() == 0

    with api_app_engine.begin() as connection:
        connection.execute(text("SELECT set_config('app.regions', '*', true)"))
        assert connection.execute(text("SELECT count(*) FROM candidates")).scalar_one() == ALL_CANDIDATES