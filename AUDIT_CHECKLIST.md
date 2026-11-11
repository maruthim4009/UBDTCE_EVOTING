# UBDTCE Secure E-Voting Audit Checklist

## Current source audit — 2026-11-10

The table below distinguishes source inspection from a live deployment test.
No real student, real ballot, SMTP recipient, or migration was used during this
audit. `WORKING` means a code path was also exercised by the listed automated
checks; it is not a claim of production-scale validation.

| Area | Status | Evidence / limitation |
| --- | --- | --- |
| Flask import, request guards, role boundaries, CSRF header | WORKING | Backend compilation and contract tests passed. |
| Principal/HOD/student login code and session expiry | PARTIALLY WORKING | Source reviewed and guard tests pass; no real account login was performed. |
| Individual registration and bulk CSV/XLSX preview/import | PARTIALLY WORKING | Transactional validation/outbox logic reviewed; no new database records created. |
| Activation, reset tokens, email templates, durable outbox | PARTIALLY WORKING | Secure token handling and worker logic reviewed; provider acceptance not tested. |
| Temporary SMTP retry and permanent failure visibility | PARTIALLY WORKING | Implemented in source; needs `integrity_symbols_outbox_migration.sql` and an isolated SMTP test mailbox. |
| HOD activation/deactivation actions | PARTIALLY WORKING | UI no longer presents student Edit or post-activation resend; live HOD workflow untested. |
| Candidate symbols and election-specific uniqueness | PARTIALLY WORKING | Implemented in API/UI/schema and static tests; migration is pending approval/application. |
| Branch CR/FR eligibility and direct student access checks | PARTIALLY WORKING | Authoritative snapshot and vote-time checks reviewed; negative database journeys untested. |
| Principal multi-branch President election | PARTIALLY WORKING | Selected branches, optional cohort snapshot, and completed-CR-winner validation implemented; no live election created. |
| Anonymous voting / duplicate prevention | PARTIALLY WORKING | Transaction design and ballot-separation schema contract verified; no concurrent database test run. |
| Result totals, turnout, ties | PARTIALLY WORKING | Source reviewed; no controlled closed-election fixture executed. |
| SHA-256 audit chain and tamper detection | PARTIALLY WORKING | Versioned hash implementation and deterministic/tamper tests pass; audit verifier needs migration and a migrated database. |
| Blockchain network integration | BLOCKED BY EXTERNAL SERVICE | No configured permissioned network; the system does not claim one. |
| PostgreSQL connectivity | WORKING | A read-only connection test succeeded; schema migration has not been run. |
| Redis shared rate-limit store | BLOCKED BY EXTERNAL SERVICE | Production requires a configured shared store; no Redis target was supplied. |
| Frontend lint and production build | WORKING | Both commands passed after implementation. |
| Load and scale evidence for 10 million accounts | NOT IMPLEMENTED | Capacity model exists in `OPERATIONS.md`; no safe load infrastructure/results were supplied. |
| Production deployment, backups, disaster recovery | NOT IMPLEMENTED | Documented only; no deployment was authorized. |

Status reflects evidence gathered on 2026-11-07. “Verified” means code review
plus an executed check; it does not mean a live user journey was performed with
real accounts or votes.

| Area | Status | Evidence / remaining verification |
| --- | --- | --- |
| Python syntax and importability | COMPLETED | `py_compile` passed for backend modules. |
| Frontend lint and production build | COMPLETED | `npm run lint` and `npm run build` passed. |
| PostgreSQL connection and health endpoint | COMPLETED | Direct connection and `/api/health` returned success. |
| Additive reliability/email/HOD schema objects | COMPLETED | All expected tables and columns were present; no migration was run. |
| Principal, HOD, and Student backend role boundaries | COMPLETED | Regression tests verify each cross-role route rejection. |
| Positive login/logout journeys | PARTIALLY COMPLETED | Login code reviewed; logout and request-verification checks executed. Real credential tests were not run to protect existing accounts. |
| Student registration and CSV/XLSX preview/import | PARTIALLY COMPLETED | Validation, duplicate checks, pagination, and transactional registration were reviewed. No live records were created. |
| Activation token security and outbox worker design | COMPLETED | Secure random token, SHA-256-only persistence, expiry, single use, lease recovery, `SKIP LOCKED`, failed-job retry controls, and redacted logs were reviewed. |
| Activation email delivery | BLOCKED | No queued jobs existed and no controlled mail recipient/test backend was authorized for a delivery test. |
| Principal college-wide election workflow | COMPLETED | Added authenticated election list, candidate registration/review, explicit start/close, and closed-only results APIs/UI; read-only SQL smoke checks passed. |
| HOD student, class, election, candidate, and results workflow | PARTIALLY COMPLETED | Existing scoped APIs and frontend contracts were reviewed; no authenticated end-to-end data mutations were authorized. |
| Student dashboard and voting history secrecy | PARTIALLY COMPLETED | Existing scoped APIs/UI were reviewed; history returns participation only. No student test account was used. |
| Vote transaction and duplicate prevention | PARTIALLY COMPLETED | Code review confirmed election locking, eligibility checks, approved-candidate validation, participation primary key, and one transaction. No live vote was cast. |
| Ballot identity separation | COMPLETED | Live schema check confirmed no ballot `student_id`; regression test confirms schema contract. |
| Results counting and tie handling | PARTIALLY COMPLETED | Code review confirmed completed-only publication, candidate totals, turnout, ties, and no voter identities. Live election data was not queried or changed. |
| Audit hash chain | COMPLETED | Existing chain validated read-only. |
| Redis/rate limiting production readiness | PARTIALLY COMPLETED | Current non-production runtime uses local in-memory storage; production startup rejects this configuration. A shared Redis service remains external configuration. |
| Secret and release hygiene | COMPLETED | `.env`, cookies, build/dependency directories, and local backups are ignored; `.env` was not opened or modified. |
| Production deployment | NOT COMPLETED | Instructions are in `DEPLOYMENT.md`; no production deployment was attempted. |
