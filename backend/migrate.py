"""Inspect and apply the repository's PostgreSQL migrations safely.

This command is deliberately separate from Flask startup: an API process must
never change a database schema just because it was restarted. By default the
command only reports status. Applying migrations requires both ``--apply`` and
an exact database-name confirmation, records a SHA-256 checksum for each
completed migration, and refuses to continue if an applied SQL file changed.

The performance-index migration remains last and is run with autocommit
enabled because it contains ``CREATE INDEX CONCURRENTLY``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable

from db import get_db_connection


MIGRATION_LOCK_KEY = "ubdtce-secure-schema-migrations-v1"


@dataclass(frozen=True)
class Migration:
    version: str
    filename: str
    mode: str = "self_managed"

    @property
    def path(self) -> Path:
        return Path(__file__).resolve().parent / self.filename

    @property
    def checksum(self) -> str:
        return sha256(self.path.read_bytes()).hexdigest()


# Keep this list append-only. Existing filenames are part of the database
# migration identity and must never be reused for a different schema change.
MIGRATIONS = (
    Migration("001_voting_reliability", "voting_reliability_migration.sql"),
    Migration("002_email_management", "email_management_migration.sql"),
    Migration("003_hod_management", "hod_management_migration.sql"),
    Migration("004_academic_year_eligibility", "academic_year_eligibility_migration.sql"),
    Migration("005_integrity_symbols_outbox", "integrity_symbols_outbox_migration.sql"),
    Migration("006_performance_indexes", "performance_indexes_migration.sql", "nontransactional"),
    Migration("007_college_election_categories", "college_election_categories_migration.sql", "transactional"),
    Migration(
        "008_academic_year_index_repair",
        "academic_year_index_repair_migration.sql",
        "nontransactional",
    ),
)


def create_migration_ledger(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(100) PRIMARY KEY,
            checksum CHAR(64) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def applied_migrations(cur) -> dict[str, str]:
    cur.execute("SELECT version, checksum FROM schema_migrations ORDER BY version;")
    return {version: checksum.strip() for version, checksum in cur.fetchall()}


def pending_migrations(applied: dict[str, str]) -> Iterable[Migration]:
    known_versions = {migration.version for migration in MIGRATIONS}
    unknown_versions = set(applied) - known_versions
    if unknown_versions:
        raise RuntimeError(
            "The migration ledger contains unknown versions: "
            + ", ".join(sorted(unknown_versions))
        )

    pending = []
    missing_predecessor = None
    for migration in MIGRATIONS:
        checksum = migration.checksum
        recorded_checksum = applied.get(migration.version)
        if recorded_checksum is None:
            if missing_predecessor is None:
                missing_predecessor = migration.version
            pending.append(migration)
        elif recorded_checksum != checksum:
            raise RuntimeError(
                f"Checksum mismatch for {migration.version}. The applied SQL file was changed; "
                "stop and review the database before creating a new migration."
            )
        elif missing_predecessor is not None:
            raise RuntimeError(
                f"Migration history is out of order: {migration.version} is recorded, "
                f"but required predecessor {missing_predecessor} is missing."
            )
    return pending


def current_database(cur) -> str:
    cur.execute("SELECT current_database();")
    return cur.fetchone()[0]


def execute_nontransactional_migration(cur, sql: str) -> None:
    """Run each simple nontransactional statement in its own autocommit unit.

    PostgreSQL rejects ``CREATE INDEX CONCURRENTLY`` when several statements
    are sent as one implicit transaction block. Nontransactional migrations in
    this project contain only standalone index statements and line comments;
    remove those comments before splitting the statements for execution.
    """
    uncommented_sql = "\n".join(
        line for line in sql.splitlines()
        if not line.lstrip().startswith("--")
    )
    statements = [
        statement.strip()
        for statement in uncommented_sql.split(";")
        if statement.strip()
    ]
    if not statements:
        raise RuntimeError("Nontransactional migration contains no SQL statements.")

    for statement in statements:
        cur.execute(statement)


def show_status(cur) -> int:
    cur.execute("SELECT to_regclass('public.schema_migrations');")
    if cur.fetchone()[0] is None:
        print("Migration ledger: not initialized")
        for migration in MIGRATIONS:
            print(f"PENDING  {migration.version}  {migration.filename}")
        return 1

    pending = list(pending_migrations(applied_migrations(cur)))
    pending_versions = {migration.version for migration in pending}
    for migration in MIGRATIONS:
        state = "PENDING" if migration.version in pending_versions else "APPLIED"
        print(f"{state:<8} {migration.version}  {migration.filename}")
    return 1 if pending else 0


def apply_migrations(cur, expected_database: str) -> None:
    database = current_database(cur)
    if database != expected_database:
        raise RuntimeError(
            f"Database confirmation does not match: connected to {database!r}, "
            f"not {expected_database!r}."
        )

    create_migration_ledger(cur)
    pending = list(pending_migrations(applied_migrations(cur)))
    if not pending:
        print("No pending migrations.")
        return

    for migration in pending:
        print(f"Applying {migration.version}: {migration.filename}")
        sql = migration.path.read_text(encoding="utf-8")
        if migration.mode == "transactional":
            # Keep new schema changes and their ledger record atomic. These
            # files must not contain BEGIN/COMMIT of their own.
            cur.execute("BEGIN;")
            try:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s);",
                    (migration.version, migration.checksum),
                )
                cur.execute("COMMIT;")
            except Exception:
                cur.execute("ROLLBACK;")
                raise
        else:
            # Legacy files retain their own transaction boundaries for
            # checksum compatibility; concurrent indexes require autocommit.
            # Both types are idempotent, so recovery after an interruption
            # before ledger insertion is a forward-only rerun.
            if migration.mode == "nontransactional":
                execute_nontransactional_migration(cur, sql)
            else:
                cur.execute(sql)
            cur.execute(
                "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s);",
                (migration.version, migration.checksum),
            )
        print(f"Applied {migration.version}.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or apply tracked UBDTCE PostgreSQL migrations."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply pending migrations. Without this flag the command is read-only.",
    )
    parser.add_argument(
        "--confirm-database",
        help="Exact current_database() value required together with --apply.",
    )
    args = parser.parse_args()

    if args.apply and not args.confirm_database:
        parser.error("--apply requires --confirm-database with the exact database name.")
    if args.confirm_database and not args.apply:
        parser.error("--confirm-database is only valid with --apply.")

    try:
        with get_db_connection() as conn:
            # Explicit transaction blocks in migration files and concurrent
            # indexes both require the runner itself to use autocommit.
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_lock(hashtext(%s));", (MIGRATION_LOCK_KEY,))
                try:
                    if args.apply:
                        apply_migrations(cur, args.confirm_database)
                        return 0
                    return show_status(cur)
                finally:
                    cur.execute("SELECT pg_advisory_unlock(hashtext(%s));", (MIGRATION_LOCK_KEY,))
    except Exception as exc:
        print(f"Migration command failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
