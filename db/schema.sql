-- The single source of truth for the database.
--
-- Plain SQL only (no psql-only commands), so the same file runs when Postgres
-- first starts and when the tests build a fresh test database.
-- Order: roles, tables, indexes, row-level security, grants.
-- The API login password is NOT in this file: db/app_login.sh sets it from the
-- environment. To apply a changed schema from scratch: docker compose down -v

-- ---------------------------------------------------------------------------
-- Roles
-- ---------------------------------------------------------------------------

-- recruiting_app is the only login the API uses. It owns nothing, is not a
-- superuser and cannot bypass row-level security. It is created without login;
-- db/app_login.sh turns login on and sets the password.
-- (Roles belong to the whole server, so create it only if it is missing.)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'recruiting_app') THEN
        CREATE ROLE recruiting_app NOLOGIN;
    END IF;
END
$$;

ALTER ROLE recruiting_app
    NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

-- Recruiters and admins. assigned_regions holds region codes, or just '*' for an
-- admin (all regions).
CREATE TABLE recruiters (
    recruiter_id     text PRIMARY KEY,
    full_name        text NOT NULL,
    email            text NOT NULL UNIQUE,
    role             text NOT NULL,
    assigned_regions text[] NOT NULL,

    CONSTRAINT recruiters_id_not_blank CHECK (btrim(recruiter_id) <> ''),
    CONSTRAINT recruiters_name_not_blank CHECK (btrim(full_name) <> ''),
    CONSTRAINT recruiters_email_clean CHECK (email = lower(btrim(email))),
    CONSTRAINT recruiters_role_valid CHECK (role IN ('admin', 'recruiter')),
    CONSTRAINT recruiters_regions_not_empty CHECK (cardinality(assigned_regions) > 0),
    CONSTRAINT recruiters_regions_valid CHECK (
        assigned_regions <@ ARRAY['US-MW', 'US-NE', 'US-SE', 'US-W', 'PH-MNL', 'CO-BOG', '*']::text[]
    ),
    -- An admin has exactly '*'. A recruiter never has '*'.
    CONSTRAINT recruiters_admin_has_star CHECK (
        role <> 'admin' OR assigned_regions = ARRAY['*']::text[]
    ),
    CONSTRAINT recruiters_recruiter_has_no_star CHECK (
        role <> 'recruiter' OR NOT ('*' = ANY (assigned_regions))
    )
);

-- Candidates. The email identifies a person (unique, always trimmed and lowercase).
-- The import cleans values before saving; these constraints are the safety net.
CREATE TABLE candidates (
    candidate_id       text PRIMARY KEY,
    first_name         text NOT NULL,
    last_name          text NOT NULL,
    email              text NOT NULL UNIQUE,
    phone              text,
    region_code        text NOT NULL,
    desired_role       text,
    salary_expectation numeric(12, 2),
    applied_date       date,
    status             text NOT NULL,
    source             text,
    notes              text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT candidates_id_not_blank CHECK (btrim(candidate_id) <> ''),
    CONSTRAINT candidates_first_name_not_blank CHECK (btrim(first_name) <> ''),
    CONSTRAINT candidates_last_name_not_blank CHECK (btrim(last_name) <> ''),
    CONSTRAINT candidates_email_clean CHECK (email = lower(btrim(email))),
    CONSTRAINT candidates_email_format CHECK (
        email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
    ),
    CONSTRAINT candidates_region_valid CHECK (
        region_code IN ('US-MW', 'US-NE', 'US-SE', 'US-W', 'PH-MNL', 'CO-BOG')
    ),
    CONSTRAINT candidates_status_valid CHECK (
        status IN ('active', 'screening', 'interviewing', 'withdrawn')
    ),
    CONSTRAINT candidates_salary_not_negative CHECK (
        salary_expectation IS NULL OR salary_expectation >= 0
    )
);

-- One row per import run. report holds the full result, including every rejected
-- row with its raw values. Only admins can see it (it contains all regions' data).
CREATE TABLE import_runs (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at     timestamptz NOT NULL DEFAULT now(),
    filename       text NOT NULL,
    imported_by    text NOT NULL REFERENCES recruiters (recruiter_id),
    imported_count integer NOT NULL CHECK (imported_count >= 0),
    merged_count   integer NOT NULL CHECK (merged_count >= 0),
    rejected_count integer NOT NULL CHECK (rejected_count >= 0),
    report         jsonb NOT NULL
);

-- ---------------------------------------------------------------------------
-- Indexes (the primary keys and unique emails already have their own)
-- ---------------------------------------------------------------------------

-- List order: newest applied date first, a stable tie-break for paging.
CREATE INDEX candidates_applied_date_idx ON candidates (applied_date DESC NULLS LAST, candidate_id);
CREATE INDEX candidates_region_idx ON candidates (region_code);
CREATE INDEX candidates_status_idx ON candidates (status);

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------
-- Each API transaction sets app.regions to the recruiter's regions, for example
-- 'US-MW,US-NE', or '*' for an admin. If nothing is set, no rows match.
-- FORCE makes the rules apply to the table owner too (superusers still bypass,
-- which is why the API never logs in as one).

ALTER TABLE candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidates FORCE ROW LEVEL SECURITY;

-- With only USING given, PostgreSQL also applies it to new and changed rows, so
-- a write outside the allowed regions fails.
CREATE POLICY candidates_by_region ON candidates
    FOR ALL
    TO recruiting_app
    USING (
        current_setting('app.regions', true) = '*'
        OR region_code = ANY (string_to_array(current_setting('app.regions', true), ','))
    );

ALTER TABLE import_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE import_runs FORCE ROW LEVEL SECURITY;

CREATE POLICY import_runs_admin_only ON import_runs
    FOR ALL
    TO recruiting_app
    USING (current_setting('app.regions', true) = '*');

-- ---------------------------------------------------------------------------
-- Grants (the API user gets only what it needs; nothing can be deleted)
-- ---------------------------------------------------------------------------

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO recruiting_app;

GRANT SELECT ON recruiters TO recruiting_app;
GRANT SELECT, INSERT, UPDATE ON candidates TO recruiting_app;
GRANT SELECT, INSERT ON import_runs TO recruiting_app;