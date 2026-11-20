#!/bin/sh
# Starts the API: first loads the recruiters into the database, then runs the server.
# Extra arguments (such as --reload) are passed on to uvicorn.
set -e

python -m app.seed

# The server must not keep the owner login that the seed just used.
unset DB_OWNER_USER DB_OWNER_PASSWORD

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"