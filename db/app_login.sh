#!/bin/sh
# Turns on login for the limited API role and sets its password.
# The password comes from the environment, so it is never written in schema.sql.
# Postgres runs this once, right after schema.sql, when the data volume is created.

psql -v ON_ERROR_STOP=1 -v app_password="$APP_DB_PASSWORD" \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'EOF' || exit 1
ALTER ROLE recruiting_app LOGIN PASSWORD :'app_password';
EOF