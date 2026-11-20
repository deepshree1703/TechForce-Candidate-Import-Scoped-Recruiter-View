"""SQLAlchemy models that mirror db/schema.sql.

The schema file is the source of truth. These classes only describe the tables so
the code can query them. Never create tables from them (no create_all).
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""


class Recruiter(Base):
    """A recruiter or admin. An admin has assigned_regions of ['*']."""

    __tablename__ = "recruiters"

    recruiter_id: Mapped[str] = mapped_column(Text, primary_key=True)
    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)
    role: Mapped[str] = mapped_column(Text)
    assigned_regions: Mapped[list[str]] = mapped_column(ARRAY(Text))


class Candidate(Base):
    """A job candidate. The email identifies the person."""

    __tablename__ = "candidates"

    candidate_id: Mapped[str] = mapped_column(Text, primary_key=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)
    phone: Mapped[str | None] = mapped_column(Text)
    region_code: Mapped[str] = mapped_column(Text)
    desired_role: Mapped[str | None] = mapped_column(Text)
    salary_expectation: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    applied_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportRun(Base):
    """One CSV import run, saved with its full report (admin only)."""

    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    filename: Mapped[str] = mapped_column(Text)
    imported_by: Mapped[str] = mapped_column(Text, ForeignKey("recruiters.recruiter_id"))
    imported_count: Mapped[int] = mapped_column(Integer)
    merged_count: Mapped[int] = mapped_column(Integer)
    rejected_count: Mapped[int] = mapped_column(Integer)
    report: Mapped[dict] = mapped_column(JSONB)