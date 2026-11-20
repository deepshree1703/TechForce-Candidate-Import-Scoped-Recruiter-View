# Recruiting Platform

Import a messy candidate CSV into PostgreSQL, then let each recruiter see only the
candidates from their assigned regions. The database enforces that, with Row-Level
Security. The stack is a FastAPI API and a React page, and everything runs through
Docker Compose, including the tests.

The decisions behind it (cleaning rules, merge rules, how access works, what comes
next) are in [NOTES.md](NOTES.md).

## Requirements

Docker with Docker Compose. Nothing else needs to be installed.

## Start

1. Copy the example settings and set both passwords:

   ```bash
   cp .env.example .env
   ```

2. Put the two CSV files in the `data/` folder:
   `data/candidates_import.csv` and `data/recruiters.csv`.
   Git ignores them because they are client data. The API loads `recruiters.csv` every
   time it starts and will not start without it.

3. Start everything:

   ```bash
   docker compose up --build
   ```

| What | Address |
| --- | --- |
| The page | http://localhost:5173 |
| The API | http://localhost:8000 (docs at `/docs`) |

The database schema is applied the first time the database starts. If you change
`db/schema.sql` later, reset the database: `docker compose down -v`, then
`docker compose up --build` (this deletes the stored data).

Check that it is running:

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok","database":"ok"}`. The start-up log shows
`Seeded 5 recruiters from /data/recruiters.csv`.

## Import the candidates

Send the CSV as the request body, as any recruiter (R-101 is used here):

```bash
curl -s -X POST "http://localhost:8000/api/v1/candidates/import?filename=candidates_import.csv" \
  -H "X-Recruiter-Id: R-101" \
  -H "Content-Type: text/csv" \
  --data-binary @data/candidates_import.csv | python3 -m json.tool

```

The answer has `rows_read`, `imported`, `merged` and a `rejected` list. Each rejected row
shows its `row_number` (counting data rows from 1), its `candidate_id` and a short
`reason`. Importing the same file again changes nothing.

## Use the page

Open http://localhost:5173. The dropdown at the top right chooses who you are viewing
as. The header, the table and the totals change with it. A recruiter only gets rows from
their own regions, and the admin gets everything. Search covers name, email and role.
Status filter and pages work together with it.

## API

Every call except `/health` and `/api/v1/recruiters` needs an `X-Recruiter-Id` header.

| Endpoint | Who | Notes |
| --- | --- | --- |
| `GET /health` | anyone | 503 if the database does not answer |
| `GET /api/v1/recruiters` | anyone | id, name and role, for the dropdown |
| `POST /api/v1/candidates/import` | any recruiter | CSV as the request body, up to 5 MB |
| `GET /api/v1/candidates` | any recruiter | `search`, `status`, `page`, `page_size` (1 to 100, default 20) |
| `GET /api/v1/candidates/{id}` | any recruiter | 404 if outside the caller's regions |

Error answers:

| Status | Meaning |
| --- | --- |
| 400 | The CSV is unusable (empty, not UTF-8, missing a required column) |
| 401 | No `X-Recruiter-Id` header |
| 403 | Unknown recruiter |
| 404 | No such candidate, or one outside the caller's regions |
| 409 | Two imports collided; try again |
| 413 | The file is over 5 MB |
| 422 | A bad `page`, `page_size`, `status` or search text |

Example reads:

```bash
curl -H "X-Recruiter-Id: R-102" "http://localhost:8000/api/v1/candidates?page_size=5"
curl -G -H "X-Recruiter-Id: R-101" --data-urlencode "search=Nguyễn" http://localhost:8000/api/v1/candidates
curl -i -H "X-Recruiter-Id: R-102" http://localhost:8000/api/v1/candidates/C-1001
```

## Run the tests

```bash
docker compose build
docker compose run --rm tests                      # everything
docker compose run --rm tests pytest tests/api -q  # only the API tests
docker compose run --rm frontend npm run build     # page: type check + build
```

The tests run on a real PostgreSQL and use the real CSV files from `data/`. They build
two throwaway databases (`recruiting_test` and `recruiting_api_test`) from
`db/schema.sql` on the same server and drop them afterwards. Your own data is not touched.

## Everyday commands

- Stop: `docker compose down`
- Database shell: `docker compose exec db psql -U recruiting_owner -d recruiting`
  (use the values from your `.env` if you changed them)
- Start the database from scratch: `docker compose down -v`, then `docker compose up --build`

## Project layout

```
.env.example, docker-compose.yml, NOTES.md
db/
  schema.sql          the single source of truth: tables, constraints, indexes, roles, security
  app_login.sh        sets the password of the limited API login from .env
data/                 the two CSV files (not committed)
api/
  app/
    main.py           the app and the health check
    config.py, database.py, models.py, regions.py, seed.py, schemas.py
    access.py         who is calling, and which regions the database lets them see
    search.py         the safe "contains" search
    routes/           imports.py, candidates.py, recruiters.py
    importing/        reading, cleaning, row, dedup, save, service
  tests/              unit tests; tests/api/ holds the endpoint tests
frontend/
  src/                App, api.ts (the only code that calls the API), types, hooks, components/
```

Stack: Python 3.13, FastAPI, Pydantic v2, SQLAlchemy (sync), PostgreSQL 17, pytest;
React 19 with TypeScript (Vite). The versions are in `api/requirements*.txt` and
`frontend/package.json`.

## Good to know

- `X-Recruiter-Id` identifies the caller but does not authenticate them. It stands in for a
  real login (see NOTES.md).
- The tables are never created from the Python models. The schema file is the only place
  that defines the database.