# Deployment and Operations

This project uses a Flask API, PostgreSQL, and a Vite/React frontend. Keep the
existing `backend/.env` in place; do not commit it or replace its values.

## Windows development

From the project root, start the API:

```powershell
cd backend
.\.venv\Scripts\python.exe app.py
```

In a second terminal, start the frontend:

```powershell
cd frontend
npm run dev
```

The default frontend expects the API on port 5000. Set `VITE_API_BASE` only
when the deployed API uses a different public URL.

## Database migrations

Back up PostgreSQL before applying any migration. Do not run `schema.sql` on
an existing database: it is the initial schema and is not a production
recreation command. Apply only the applicable additive migration files from
the backend directory, one at a time, with PostgreSQL credentials supplied by
the deployment environment:

```powershell
psql -v ON_ERROR_STOP=1 -f voting_reliability_migration.sql
psql -v ON_ERROR_STOP=1 -f email_management_migration.sql
psql -v ON_ERROR_STOP=1 -f hod_management_migration.sql
psql -v ON_ERROR_STOP=1 -f integrity_symbols_outbox_migration.sql
psql -v ON_ERROR_STOP=1 -f performance_indexes_migration.sql
```

Review each file and confirm the target database before execution. These
migrations must be run once only on installations that need their objects.

## Production API

Install the pinned-range dependencies from `backend/requirements.txt`, set
production environment configuration outside source control, then serve the
WSGI application with Waitress on Windows:

```powershell
cd backend
.\.venv\Scripts\python.exe -m waitress --listen=127.0.0.1:5000 wsgi:app
```

Place a TLS-terminating reverse proxy in front of Waitress. In production,
configure `APP_ENV=production`, a long random `FLASK_SECRET_KEY`,
`SESSION_COOKIE_SECURE=true`, exact HTTPS `CORS_ORIGINS`, and a shared
non-memory `RATELIMIT_STORAGE_URI`. The application deliberately refuses to
start in production with an in-memory rate-limit store or insecure session
cookie configuration.

## Frontend production build

```powershell
cd frontend
npm run lint
npm run build
```

Deploy `frontend/dist` through the same HTTPS origin or configure the exact
API origin in `VITE_API_BASE` before building.

## Activation email worker

Run one bounded worker invocation from the backend directory (typically via a
scheduled task). It processes only queued jobs and never prints recipients or
activation links:

```powershell
.\.venv\Scripts\python.exe email_worker.py --limit 25
```

For a single bounded worker process that continually picks up invitations,
run it under a service manager or scheduled-task wrapper:

```powershell
.\.venv\Scripts\python.exe email_worker.py --watch --limit 25 --interval-seconds 30
```

Do not run the worker for a bulk invitation campaign until an authorized
administrator has approved the recipients and the configured mail service has
been verified. Failed jobs remain recoverable through the HOD resend/retry
controls.

## Backups and release hygiene

Take regular PostgreSQL logical backups with `pg_dump` using a protected
service account and test restoration separately. Keep `.env`, `cookies.txt`,
virtual environments, `node_modules`, generated builds, logs, and `.backup`
out of Git and release archives.
