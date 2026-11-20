"""Reads the API settings from environment variables."""

import os
from dataclasses import dataclass

from sqlalchemy.engine import URL


@dataclass(frozen=True)
class Settings:
    """The settings the API needs, read once when the app starts."""

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    def build_url(self, user: str, password: str, database: str | None = None) -> URL:
        """Build a SQLAlchemy connection URL (safe for special characters in the password)."""
        return URL.create(
            drivername="postgresql+psycopg",
            username=user,
            password=password,
            host=self.db_host,
            port=self.db_port,
            database=database or self.db_name,
        )

    def database_url(self) -> URL:
        """The URL the API itself uses: the limited login that row-level security applies to."""
        return self.build_url(self.db_user, self.db_password)


def read_env(name: str) -> str:
    """Return an environment variable, or stop with a clear message if it is missing."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    """Read every setting the API needs from the environment."""
    return Settings(
        db_host=read_env("DB_HOST"),
        db_port=int(read_env("DB_PORT")),
        db_name=read_env("DB_NAME"),
        db_user=read_env("DB_USER"),
        db_password=read_env("DB_PASSWORD"),
    )


settings = load_settings()