"""Loads the recruiters from the CSV file into the database.

Safe to run many times: it updates existing recruiters and never deletes any.
Run it with: python -m app.seed [path-to-recruiters.csv]
It logs in as the database owner, because the API login can only read recruiters.
"""

import csv
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import read_env, settings
from app.models import Recruiter
from app.regions import ALL_REGIONS, VALID_REGIONS

DEFAULT_CSV = "/data/recruiters.csv"
REQUIRED_COLUMNS = {"recruiter_id", "full_name", "email", "role", "assigned_regions"}


def parse_regions(text: str) -> list[str]:
    """Split 'US-MW|US-NE' into a list. A lone '*' means all regions (an admin)."""
    regions = [part.strip() for part in text.split("|") if part.strip()]
    for region in regions:
        if region != ALL_REGIONS and region not in VALID_REGIONS:
            raise ValueError(f"Unknown region '{region}' in recruiter file")
    return regions


def read_recruiters(path: Path) -> list[dict]:
    """Read the recruiter CSV and return one clean dict per recruiter."""
    with open(path, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Recruiter file is missing columns: {sorted(missing)}")
        rows = [
            {
                "recruiter_id": row["recruiter_id"].strip(),
                "full_name": row["full_name"].strip(),
                "email": row["email"].strip().lower(),
                "role": row["role"].strip().lower(),
                "assigned_regions": parse_regions(row["assigned_regions"]),
            }
            for row in reader
        ]
    if not rows:
        raise ValueError("Recruiter file has no recruiters")
    return rows


def save_recruiters(session: Session, rows: list[dict]) -> None:
    """Insert the recruiters in one statement, updating the ones that already exist."""
    statement = insert(Recruiter).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[Recruiter.recruiter_id],
        set_={
            "full_name": statement.excluded.full_name,
            "email": statement.excluded.email,
            "role": statement.excluded.role,
            "assigned_regions": statement.excluded.assigned_regions,
        },
    )
    session.execute(statement)


def main() -> None:
    """Load the recruiter file named on the command line (or the default one)."""
    path = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV)
    if not path.exists():
        sys.exit(f"Recruiter file not found: {path}. Put recruiters.csv in the data folder.")

    rows = read_recruiters(path)
    owner_url = settings.build_url(read_env("DB_OWNER_USER"), read_env("DB_OWNER_PASSWORD"))
    engine = create_engine(owner_url)
    with Session(engine) as session, session.begin():
        save_recruiters(session, rows)
    engine.dispose()
    print(f"Seeded {len(rows)} recruiters from {path}")


if __name__ == "__main__":
    main()