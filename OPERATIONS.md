# UBDTCE Secure E-Voting — Operations and Architecture

## Scope and security boundary

The system is a modular Flask/React application backed by PostgreSQL. Flask
instances are stateless apart from signed sessions; PostgreSQL is the
authoritative source for identity, eligibility, participation, anonymous
ballots, and audit evidence. Redis is required for distributed rate limiting
in production, but it is not a replacement for voting consistency checks.

There is no deployed blockchain network in this repository. The implemented
SHA-256 audit chain is local, verifiable integrity evidence—not a decentralized
blockchain. Do not describe it as one. No student PII, activation token,
session identifier, participation record, or individual ballot belongs in a
future blockchain integration.

## Role workflows

- Principal: manages branches and HOD assignments; creates President-election
  drafts for selected branches; selects only verified winners of closed branch
  CR elections; reviews candidates; starts/closes college elections; and can
  run an audit-chain verification summary.
- HOD: registers students individually or from a validated CSV/XLSX preview;
  queues activation invitations; changes account status without deleting
  students; creates CR/FR elections for an exact branch/admission-year/
  semester cohort; assigns approved symbols; reviews candidates; and views
  closed-election results.
- Student: activates the account, signs in with USN, sees only the
  server-snapshotted elections for which they are eligible, sees ballot cards
  with only symbol and USN, votes once, and sees participation—not choices—in
  voting history.

## Data and privacy model

`voter_eligibility` is an authoritative election-time snapshot. The vote
transaction locks the election, validates student eligibility and candidate
approval, inserts the unique participation row, then inserts an anonymous
ballot in one PostgreSQL transaction. `ballots` has no student ID and no link
back to `voter_participation`. Administrators never receive voter choices.

Participation timestamps still reveal that a particular student voted at a
time. The application intentionally does not attach IP address, session ID, or
candidate ID to participation or audit events. For stronger traffic-analysis
resistance, deploy an independently reviewed network/privacy design.

Candidate symbols use a server-owned fixed library. `symbol_key` is unique per
election; no arbitrary image upload capability exists. New symbols can only be
chosen while the election remains a draft. Existing historic candidates remain
unchanged by the additive migration.

## Email outbox

Student registration writes the account, student row, activation-email job,
and audit event in one transaction. A separate bounded worker claims one job
at a time with `FOR UPDATE SKIP LOCKED`, creates the opaque one-time token only
in worker memory, stores only its SHA-256 hash, and marks a job `SENT` only
after SMTP accepts `send_message`.

Temporary SMTP/timeout failures back off automatically (up to five attempts).
Permanent failures and exhausted temporary failures remain `FAILED` for an
authorized HOD retry. A resend is unavailable after credentials exist. SMTP
provider acceptance is not proof of inbox delivery, and test mode suppresses
delivery by design.

## Required safe schema rollout

Do not run `schema.sql` against an existing database. Confirm the target is an
approved backup-tested environment. The migration command is read-only unless
`--apply` is paired with the exact target database name:

```powershell
cd backend
..\.venv\Scripts\python.exe migrate.py
..\.venv\Scripts\python.exe migrate.py --apply --confirm-database ubdtce_evoting
```

The command records a version and checksum after each completed migration,
serializes concurrent invocations with a PostgreSQL advisory lock, and refuses
to rerun a changed or unknown version. Its manifest includes the academic-year
eligibility migration required by cohort-scoped elections. The integrity
migration adds candidate symbols, versioned audit metadata, and outbox retry
metadata. The performance-index migration uses nonblocking `CREATE INDEX
CONCURRENTLY`, so it can take substantial time on a large database. Neither
migration deletes records or alters ballots. Take a protected `pg_dump`,
verify its restoration elsewhere, and do not use `--apply` for a
previously-manual rollout until a DBA has initialized and reviewed the ledger.

## Local operation

```powershell
# terminal 1
cd backend
.\.venv\Scripts\python.exe app.py

# terminal 2
cd frontend
npm run dev

# bounded email worker; do not run against unapproved recipients
cd backend
.\.venv\Scripts\python.exe email_worker.py --limit 25

# one long-running bounded worker process (production service-manager target)
.\.venv\Scripts\python.exe email_worker.py --watch --limit 25 --interval-seconds 30

# verification
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd ..\frontend
npm run lint
npm run build
```

Use `/api/health` for database liveness and `/api/ready` for load-balancer
readiness. Responses include an `X-Request-ID` suitable for correlating logs;
do not place personal or ballot data in log search queries.

## Production topology

```text
Browser → CDN / WAF → TLS load balancer → stateless Flask instances
                                         ├─ PostgreSQL primary
                                         ├─ Redis rate-limit store
                                         └─ bounded email worker deployment → SMTP provider
```

Use a reverse proxy for HTTPS, secure cookies, exact CORS origins, a long
secret managed outside source control, shared Redis, least-privilege database
accounts, centralized redacted logs, metrics, tracing, tested backups, and a
documented restore runbook. Deploy application instances separately from
email workers. PostgreSQL failover and backup recovery must be rehearsed, not
assumed.

## Initial objectives—not measured capacity claims

The 10-million-account target is a sizing objective, not an achieved result.
Initial planning scenarios should be tested on isolated infrastructure:

| Scenario | Assumption | Test objective |
| --- | --- | --- |
| Normal peak | 10,000 concurrent sessions; 150 login RPS; 500 election-list RPS | p95 read latency under 300 ms, error rate under 0.1% |
| Election opening | 10,000 sessions; 200 vote submissions/sec burst | p95 successful vote under 750 ms; no duplicate participation |
| Registration campaign | 100,000 imports/day | bounded queue depth, no lost jobs, provider rate obeyed |
| Audit volume | 100 events/sec during peaks | chain writes serialized safely; monitor database latency |

These are proposed SLOs: monthly API availability 99.9%, successful valid
vote transaction rate 99.99%, email-job first-attempt processing within 15
minutes subject to provider capacity, and tested recovery objectives chosen by
the institution. They are not evidence that the current laptop or database
supports those levels.

Before scale testing, provision PostgreSQL connection pooling (for example
PgBouncer), read replicas only for safely stale dashboard reads, appropriate
indexes/query plans, queue-depth metrics, worker/provider rate limits, and
load generation using synthetic identities. Test progressively at 100, 500,
1,000, 5,000, and 10,000 concurrent users. Capture RPS, p50/p95/p99, errors,
database connection and query latency, cache hit ratio, worker queue depth,
CPU, memory, and duplicate-vote outcomes. Never load-test real students or
elections.

## Security review checklist

- Keep `backend/.env` unmodified and out of source control.
- Enforce HTTPS, secure session cookies, exact credentialed CORS origins, and
  a shared non-memory limiter in production.
- Do not expose raw SMTP errors, tokens, reset links, credentials, ballot
  choices, or audit event payloads in API responses or logs.
- Re-run authorization, direct-object-reference, concurrent-vote, token reuse,
  SQL injection, XSS, CSRF, CSV/XLSX upload, and email retry tests before each
  release.
- Obtain independent application-security and election-process review before
  representing the system as secure for a live college election.

## Known limitations

- No blockchain network is configured or claimed.
- Database connection creation is direct Psycopg; a production pooling layer
  is still an infrastructure requirement.
- Results are available at closure; the schema does not yet model a separate
  results-publication state.
- The current test suite is contract-focused. Full role journeys, provider
  acceptance, migration execution, concurrent database voting, and load
  measurements require isolated authorized test infrastructure.
