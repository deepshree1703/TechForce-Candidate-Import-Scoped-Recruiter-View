"""Search for the candidate list: turns the user's text into a safe "contains" filter.

The text is never put into the SQL itself. It travels as a bound parameter, and the
characters that mean something in a LIKE pattern are escaped first, so "%" and "_" are
searched for as ordinary characters.
"""

from sqlalchemy import ColumnElement, String, func, or_

from app.models import Candidate

# The character that marks "take the next character literally" in the LIKE pattern.
ESCAPE_CHAR = "/"


def escape_like(term: str) -> str:
    """Escape %, _ and the escape character itself, so they match literally."""
    escaped = term.replace(ESCAPE_CHAR, ESCAPE_CHAR * 2)
    escaped = escaped.replace("%", ESCAPE_CHAR + "%")
    return escaped.replace("_", ESCAPE_CHAR + "_")


def search_condition(term: str | None) -> ColumnElement[bool] | None:
    """Build the filter "name, email or role contains the text", ignoring case.

    The name is searched as "first last", so a full name also matches. A blank
    search gives None, which means no filter.
    """
    cleaned = (term or "").strip()
    if not cleaned:
        return None
    pattern = f"%{escape_like(cleaned)}%"
    full_name = func.concat_ws(" ", Candidate.first_name, Candidate.last_name, type_=String)
    columns = [full_name, Candidate.email, Candidate.desired_role]
    return or_(*(column.ilike(pattern, escape=ESCAPE_CHAR) for column in columns))