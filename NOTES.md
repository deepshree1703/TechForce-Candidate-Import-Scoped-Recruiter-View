# Notes

## 1. Normalization and validation

Each row is checked alone. A bad row is rejected with a reason (`field: problem`), never dropped quietly.

- **Email:** trimmed, lowercased, must look like `name@domain.tld`. `marcus.reed[at]gmail.com` is rejected.
- **Region:** case, spaces and a missing hyphen are ignored (`us-mw`, `USW`). It must end up as one of the 6 canonical codes, otherwise it is rejected.
- **Status:** lowercased, must be `active`, `screening`, `interviewing` or `withdrawn`. I do not guess typos (`actve` is rejected).
- **Applied date:** only `YYYY-MM-DD`, `MM/DD/YYYY` or `DD-Mon-YYYY`. Impossible dates (`2026-02-30`) are rejected. An empty date stays empty.
- **Salary:** `$95,000` and `85k` become numbers. Anything else (`negotiable`) becomes null and the row is still accepted.
- **Names and other text:** trimmed only. Unicode is kept as it is.
- **SQL injection:** every query uses bound parameters, so text like `O'Connor'); DROP TABLE candidates;--` is stored as plain text. The database also repeats the key rules as constraints.

## 2. Dedup and merge rules

- **Same email = same person.** The rows are merged and keep the id seen first (a record already in the database counts as first).
- **Same candidate_id, different email = collision.** These are two people. The first is kept and the later row is rejected.
- **Merge:** the row with the strictly newer applied date wins. On a tie or a missing date the earlier record wins.
- **Empty never overwrites a value,** and an initial (`A.`) never replaces a full name (`Amara`).
- The same rules apply against records already in the database. Importing the same file twice changes nothing.
- **Writes:** upserts in chunks of 1,000 rows (no row-at-a-time inserts), all in one transaction.
- **Result on the real file:** 53 rows read = 41 imported + 3 merged + 9 rejected.

## 3. Access control

- `X-Recruiter-Id` gives 401 if missing and 403 if the recruiter is unknown, never an empty 200.
- The scoping is PostgreSQL Row-Level Security. Each request sets its regions with a transaction-local setting, and the policy on `candidates` does the filtering. The Python code never filters by region.
- The API connects as a limited login (not a superuser, not the table owner, no `BYPASSRLS`). RLS is forced on.
- An out-of-region candidate returns 404, the same as a missing one.
- **Import decision:** the brief does not restrict who may import, so any known recruiter can call `POST /api/v1/candidates/import`. A bulk import must see all regions to merge correctly, so it runs with all regions. Reading stays scoped.
- **Known limit:** the header is trusted, not a real login.

## 4. AI usage log

- **Tools:** Claude Code (CLI) and ChatGPT.
- **Delegated:** first drafts of the cleaning code, dedup, the endpoints, the React table and the tests. Also explaining errors such as the Docker Compose database connection failure.
- **Not delegated:** the merge rules, the choice of Row-Level Security for authorization, and checking every rule against the brief.
- **How I checked:** I read the diffs, compared behaviour with the brief, and ran the suite (252 tests) against a real PostgreSQL with the real CSV files.
- **A mistake the AI made, caught and corrected:** the AI invented a rule that only admins can upload CSVs. The brief never says that. It looked sensible, so it was implemented without anyone asking for it. I found it by checking the endpoint against the brief, removed the admin check, and changed the import to run with all regions so it still works for any recruiter. I fixed the test that expected a 403.
- **A second mismatch with the brief, also fixed:** the AI had put the endpoints at `/imports` and `/candidates` with a `q` parameter. The brief says `/api/v1/candidates/import`, `/api/v1/candidates` and `search`.

## 5. What I would do next

1. A real login (sessions or signed tokens) instead of the trusted header.
2. An import history page and a dry-run mode, with a background job for large files.
3. Frontend tests (Vitest, one Playwright path) and CI that runs everything on each push.
4. Alembic migrations, trigram search and keyset pagination at larger scale.
5. A production setup (built frontend, HTTPS, secrets store) and an audit trail.
