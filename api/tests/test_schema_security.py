"""Proves at database level that row-level security keeps each recruiter in their regions.

Every test logs in as the limited API user and talks to PostgreSQL directly, with no
API code in between, so these results come from the database rules alone.
The sample data has four candidates: T-1 US-MW, T-2 US-NE, T-3 PH-MNL, T-4 US-W.
"""

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.database import set_region_context

TOTAL_CANDIDATES = 4

INSERT_CANDIDATE = text(
    """
    INSERT INTO candidates (candidate_id, first_name, last_name, email, region_code, status)
    VALUES (:candidate_id, 'New', 'Person', :email, :region, 'active')
    """
)

INSERT_IMPORT_RUN = text(
    """
    INSERT INTO import_runs (filename, imported_by, imported_count, merged_count, rejected_count, report)
    VALUES ('candidates.csv', 'R-1', 0, 0, 0, '{}')
    """
)


def count_rows(session: Session, table: str) -> int:
    """Count the rows the current login can see in a table."""
    return session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def visible_regions(session: Session) -> set[str]:
    """Return the set of region codes among the candidates the login can see."""
    rows = session.execute(text("SELECT DISTINCT region_code FROM candidates"))
    return {row[0] for row in rows}


def insert_candidate(session: Session, candidate_id: str, region: str) -> None:
    """Try to insert a new candidate in the given region."""
    session.execute(
        INSERT_CANDIDATE,
        {"candidate_id": candidate_id, "email": f"{candidate_id.lower()}@example.com", "region": region},
    )


def test_no_context_returns_no_rows(app_session: Session) -> None:
    """With no region setting at all, the candidate table looks empty."""
    assert count_rows(app_session, "candidates") == 0


def test_empty_context_returns_no_rows(app_session: Session) -> None:
    """A recruiter with no regions sees nothing."""
    set_region_context(app_session, [])
    assert count_rows(app_session, "candidates") == 0


def test_region_setting_shows_only_that_region(app_session: Session) -> None:
    """One region in the setting means only that region's candidates are visible."""
    set_region_context(app_session, ["US-MW"])
    assert visible_regions(app_session) == {"US-MW"}


def test_several_regions_show_exactly_those_regions(app_session: Session) -> None:
    """Two regions in the setting show those two and nothing else."""
    set_region_context(app_session, ["US-MW", "PH-MNL"])
    assert visible_regions(app_session) == {"US-MW", "PH-MNL"}


def test_unknown_region_shows_nothing(app_session: Session) -> None:
    """A region code that matches no candidate gives no rows (and no error)."""
    set_region_context(app_session, ["ZZ-99"])
    assert count_rows(app_session, "candidates") == 0


def test_admin_setting_shows_everything(app_session: Session) -> None:
    """The '*' setting shows the candidates from every region."""
    set_region_context(app_session, ["*"])
    assert count_rows(app_session, "candidates") == TOTAL_CANDIDATES


def test_setting_ends_with_the_transaction(app_session: Session) -> None:
    """After the transaction ends the setting is gone, so access is gone with it."""
    set_region_context(app_session, ["*"])
    assert count_rows(app_session, "candidates") == TOTAL_CANDIDATES
    app_session.rollback()
    assert count_rows(app_session, "candidates") == 0


def test_write_outside_region_fails(app_session: Session) -> None:
    """Inserting a candidate in a region the recruiter does not have is refused by the rule."""
    set_region_context(app_session, ["US-MW"])
    with pytest.raises(ProgrammingError) as error:
        insert_candidate(app_session, "T-90", "PH-MNL")
    assert isinstance(error.value.orig, psycopg.errors.InsufficientPrivilege)
    assert "row-level security" in str(error.value.orig)


def test_write_inside_region_works(app_session: Session) -> None:
    """The same insert in an allowed region works, so the test above fails for the right reason."""
    set_region_context(app_session, ["US-MW"])
    insert_candidate(app_session, "T-91", "US-MW")
    assert count_rows(app_session, "candidates") == 2


def test_cannot_move_a_candidate_out_of_the_region(app_session: Session) -> None:
    """Changing a visible candidate's region to one the recruiter lacks is refused."""
    set_region_context(app_session, ["US-MW"])
    with pytest.raises(ProgrammingError) as error:
        app_session.execute(text("UPDATE candidates SET region_code = 'PH-MNL' WHERE candidate_id = 'T-1'"))
    assert "row-level security" in str(error.value.orig)


def test_cannot_change_a_candidate_in_another_region(app_session: Session) -> None:
    """A candidate outside the recruiter's regions is invisible, so an update touches no rows."""
    set_region_context(app_session, ["US-MW"])
    result = app_session.execute(text("UPDATE candidates SET notes = 'changed' WHERE candidate_id = 'T-3'"))
    assert result.rowcount == 0


def test_api_user_cannot_delete(app_session: Session) -> None:
    """Even an admin context cannot delete candidates, because the login has no delete right."""
    set_region_context(app_session, ["*"])
    with pytest.raises(ProgrammingError) as error:
        app_session.execute(text("DELETE FROM candidates"))
    assert "permission denied" in str(error.value.orig)


def test_api_user_cannot_change_recruiters(app_session: Session) -> None:
    """The login can read recruiters but cannot add or change them."""
    with pytest.raises(ProgrammingError) as error:
        app_session.execute(
            text(
                "INSERT INTO recruiters (recruiter_id, full_name, email, role, assigned_regions) "
                "VALUES ('R-99', 'Sneaky', 'sneaky@example.com', 'admin', ARRAY['*'])"
            )
        )
    assert "permission denied" in str(error.value.orig)


def test_recruiters_are_readable_without_context(app_session: Session) -> None:
    """Recruiters can be looked up before any region setting exists (needed to log a caller in)."""
    assert count_rows(app_session, "recruiters") == 2


def test_import_runs_are_hidden_from_recruiters(app_session: Session) -> None:
    """A recruiter can neither read nor write the import history."""
    set_region_context(app_session, ["US-MW", "US-NE"])
    assert count_rows(app_session, "import_runs") == 0
    with pytest.raises(ProgrammingError) as error:
        app_session.execute(INSERT_IMPORT_RUN)
    assert "row-level security" in str(error.value.orig)


def test_import_runs_work_for_admins(app_session: Session) -> None:
    """An admin context can save an import run and read it back."""
    set_region_context(app_session, ["*"])
    app_session.execute(INSERT_IMPORT_RUN)
    assert count_rows(app_session, "import_runs") == 1


def test_api_user_cannot_bypass_security(app_session: Session) -> None:
    """The login is not a superuser, cannot bypass the rules, and the rules are forced on."""
    role = app_session.execute(
        text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
    ).one()
    assert role.rolsuper is False
    assert role.rolbypassrls is False

    tables = app_session.execute(
        text(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname IN ('candidates', 'import_runs') AND relnamespace = 'public'::regnamespace"
        )
    ).all()
    assert {table.relname for table in tables} == {"candidates", "import_runs"}
    assert all(table.relrowsecurity and table.relforcerowsecurity for table in tables)