"""Opt-in PostgreSQL voting transaction tests for an empty disposable DB.

These tests never read the application's configured database.  They run only
when an operator explicitly supplies ``UBDTCE_TEST_DATABASE_URL`` and sets
``UBDTCE_RUN_POSTGRES_INTEGRATION=1``.  The target must be empty and named
``*_test`` or ``*_tests``; the suite never drops, truncates, or reuses tables.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import os
import re
import sys
import unittest
from unittest.mock import patch

import psycopg


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import app, process_pending_activation_emails


class PostgreSQLVotingIntegrationTests(unittest.TestCase):
    """Exercise actual transaction atomicity only on an explicit fresh test DB."""

    @classmethod
    def setUpClass(cls):
        if os.getenv("UBDTCE_RUN_POSTGRES_INTEGRATION") != "1":
            raise unittest.SkipTest(
                "Set UBDTCE_RUN_POSTGRES_INTEGRATION=1 for a disposable PostgreSQL test database."
            )
        cls.conninfo = os.getenv("UBDTCE_TEST_DATABASE_URL")
        if not cls.conninfo:
            raise unittest.SkipTest("UBDTCE_TEST_DATABASE_URL is not configured.")

        with psycopg.connect(cls.conninfo, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), to_regclass('public.accounts');")
                database_name, accounts_table = cur.fetchone()
                if not re.fullmatch(r"[A-Za-z0-9_]*(?:_test|_tests)", database_name):
                    raise RuntimeError(
                        "Refusing integration tests: database name must end in _test or _tests."
                    )
                if accounts_table is not None:
                    raise RuntimeError(
                        "Refusing integration tests: target database is not empty. Create a fresh disposable database."
                    )
                cur.execute((BACKEND_DIR / "schema.sql").read_text(encoding="utf-8"))

        app.config.update(TESTING=True, SECRET_KEY="postgres-integration-test-secret")
        cls.get_connection_patch = patch(
            "app.get_db_connection", side_effect=lambda: psycopg.connect(cls.conninfo)
        )
        cls.get_connection_patch.start()
        cls.fixture_number = 0

    @classmethod
    def tearDownClass(cls):
        cls.get_connection_patch.stop()

    @classmethod
    def _new_vote_fixture(cls):
        """Create synthetic rows for one test; no real identity or email is used."""
        cls.fixture_number += 1
        number = cls.fixture_number
        with psycopg.connect(cls.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO branches (name, code) VALUES (%s, %s) RETURNING id;",
                    (f"Synthetic Branch {number}", f"T{number:03d}"),
                )
                branch_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO accounts (email, role, full_name)
                    VALUES (%s, 'PRINCIPAL', 'Synthetic Principal') RETURNING id;
                    """,
                    (f"principal-{number}@example.test",),
                )
                principal_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO accounts (email, role, full_name)
                    VALUES (%s, 'STUDENT', 'Synthetic Student') RETURNING id;
                    """,
                    (f"student-{number}@example.test",),
                )
                account_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO students (
                        account_id, usn, full_name, branch_id, semester,
                        admission_year, academic_year
                    ) VALUES (%s, %s, 'Synthetic Student', %s, 4, 2025, 2026)
                    RETURNING id;
                    """,
                    (account_id, f"4UB25TS{number:03d}", branch_id),
                )
                student_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO elections (
                        title, election_type, branch_id, admission_year,
                        academic_year, semester, duration_minutes, opens_at,
                        closes_at, status, created_by
                    ) VALUES (
                        %s, 'CR', %s, 2025, 2026, 4, 30,
                        CURRENT_TIMESTAMP - INTERVAL '1 minute',
                        CURRENT_TIMESTAMP + INTERVAL '30 minutes', 'OPEN', %s
                    ) RETURNING id;
                    """,
                    (f"Synthetic vote {number}", branch_id, principal_id),
                )
                election_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO voter_eligibility (election_id, student_id) VALUES (%s, %s);",
                    (election_id, student_id),
                )
                cur.execute(
                    """
                    INSERT INTO candidates (
                        election_id, student_id, symbol_key, is_approved, review_status
                    ) VALUES (%s, %s, 'book', TRUE, 'APPROVED') RETURNING id;
                    """,
                    (election_id, student_id),
                )
                candidate_id = cur.fetchone()[0]
        return account_id, election_id, candidate_id

    @staticmethod
    def _student_client(account_id):
        client = app.test_client()
        with client.session_transaction() as session_data:
            session_data["account_id"] = account_id
            session_data["role"] = "STUDENT"
        return client

    @staticmethod
    def _hod_client(account_id):
        client = app.test_client()
        with client.session_transaction() as session_data:
            session_data["account_id"] = account_id
            session_data["role"] = "HOD"
        return client

    @classmethod
    def _new_hod_fixture(cls):
        cls.fixture_number += 1
        number = cls.fixture_number
        with psycopg.connect(cls.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO branches (name, code) VALUES (%s, %s) RETURNING id;",
                    (f"Activation Branch {number}", f"A{number:03d}"),
                )
                branch_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO accounts (email, role, full_name)
                    VALUES (%s, 'HOD', 'Synthetic HOD') RETURNING id;
                    """,
                    (f"hod-activation-{number}@example.test",),
                )
                hod_account_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO hod_assignments (account_id, branch_id) VALUES (%s, %s);",
                    (hod_account_id, branch_id),
                )
        return hod_account_id, branch_id, number

    @classmethod
    def _new_activation_fixture(cls, expires_in_hours=24):
        cls.fixture_number += 1
        number = cls.fixture_number
        token = f"synthetic-activation-token-{number}"
        token_hash = hashlib.sha256(token.encode("utf-8")).digest()
        with psycopg.connect(cls.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO branches (name, code) VALUES (%s, %s) RETURNING id;",
                    (f"Token Branch {number}", f"K{number:03d}"),
                )
                branch_id = cur.fetchone()[0]
                email = f"activation-{number}@example.test"
                cur.execute(
                    """
                    INSERT INTO accounts (email, role, full_name)
                    VALUES (%s, 'STUDENT', 'Synthetic Activation Student')
                    RETURNING id;
                    """,
                    (email,),
                )
                account_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO students (
                        account_id, usn, full_name, branch_id, semester,
                        admission_year, academic_year
                    ) VALUES (%s, %s, 'Synthetic Activation Student', %s, 4, 2026, 2026)
                    RETURNING id;
                    """,
                    (account_id, f"4UB26AK{number:03d}", branch_id),
                )
                student_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO student_activation_tokens (
                        account_id, token_hash, expires_at
                    ) VALUES (%s, %s, CURRENT_TIMESTAMP + (%s * INTERVAL '1 hour'));
                    """,
                    (account_id, token_hash, expires_in_hours),
                )
        return account_id, student_id, email, token

    def _counts(self, election_id):
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM voter_participation WHERE election_id = %s),
                        (SELECT COUNT(*) FROM ballots WHERE election_id = %s),
                        (SELECT COUNT(*) FROM audit_events
                         WHERE election_id = %s AND event_type = 'VOTE_RECORDED');
                    """,
                    (election_id, election_id, election_id),
                )
                return cur.fetchone()

    def test_valid_vote_then_ambiguous_retry_records_one_participation_and_ballot(self):
        account_id, election_id, candidate_id = self._new_vote_fixture()
        client = self._student_client(account_id)
        request = {
            "headers": {"X-Requested-With": "XMLHttpRequest"},
            "json": {"candidate_id": candidate_id},
        }
        self.assertEqual(
            client.post(f"/api/student/elections/{election_id}/vote", **request).status_code,
            201,
        )
        # A client that timed out after the commit may retry safely: it cannot
        # create a second participation row or anonymous ballot.
        self.assertEqual(
            client.post(f"/api/student/elections/{election_id}/vote", **request).status_code,
            409,
        )
        self.assertEqual(self._counts(election_id), (1, 1, 1))

    def test_simultaneous_votes_for_one_student_allow_exactly_one(self):
        account_id, election_id, candidate_id = self._new_vote_fixture()

        def submit():
            client = self._student_client(account_id)
            return client.post(
                f"/api/student/elections/{election_id}/vote",
                headers={"X-Requested-With": "XMLHttpRequest"},
                json={"candidate_id": candidate_id},
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _: submit(), range(2)))
        self.assertEqual(sorted(statuses), [201, 409])
        self.assertEqual(self._counts(election_id), (1, 1, 1))

    def test_ballot_insert_failure_rolls_back_participation(self):
        account_id, election_id, candidate_id = self._new_vote_fixture()
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE FUNCTION reject_synthetic_ballot() RETURNS trigger AS $$
                    BEGIN
                        RAISE EXCEPTION 'synthetic ballot failure';
                    END;
                    $$ LANGUAGE plpgsql;
                """)
                cur.execute(f"""
                    CREATE TRIGGER reject_synthetic_ballot_trigger
                    BEFORE INSERT ON ballots
                    FOR EACH ROW WHEN (NEW.election_id = {election_id})
                    EXECUTE FUNCTION reject_synthetic_ballot();
                """)

        response = self._student_client(account_id).post(
            f"/api/student/elections/{election_id}/vote",
            headers={"X-Requested-With": "XMLHttpRequest"},
            json={"candidate_id": candidate_id},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self._counts(election_id), (0, 0, 0))

    def test_individual_registration_creates_one_pending_activation_job(self):
        hod_account_id, _branch_id, number = self._new_hod_fixture()
        email = f"new-student-{number}@example.test"
        response = self._hod_client(hod_account_id).post(
            "/api/hod/students",
            headers={"X-Requested-With": "XMLHttpRequest"},
            json={
                "name": "Synthetic New Student",
                "usn": f"4UB26AR{number:03d}",
                "email": email,
                "semester": 4,
                "admission_year": 2026,
                "academic_year": 2026,
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["activation_email_queued"])

        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT a.email, COUNT(j.id), MIN(j.status)
                    FROM accounts a
                    JOIN student_activation_email_jobs j ON j.account_id = a.id
                    WHERE LOWER(a.email) = %s
                    GROUP BY a.email;
                    """,
                    (email,),
                )
                row = cur.fetchone()
        self.assertEqual(row, (email, 1, "PENDING"))

    @patch("app.smtplib.SMTP")
    def test_worker_sends_to_registered_email_then_records_sent(self, smtp):
        # Other tests intentionally leave their registration job pending. This
        # worker test must claim only the job whose recipient it asserts.
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE student_activation_email_jobs
                    SET status = 'CANCELLED', locked_at = NULL,
                        next_attempt_at = NULL
                    WHERE status IN ('PENDING', 'PROCESSING');
                    """
                )

        account_id, _student_id, email, _token = self._new_activation_fixture()
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO student_activation_email_jobs (account_id) VALUES (%s);",
                    (account_id,),
                )

        with patch.dict(os.environ, {
            "EMAIL_TEST_MODE": "false",
            "SMTP_EMAIL": "sender@example.test",
            "SMTP_APP_PASSWORD": "synthetic-test-password",
            "SMTP_HOST": "smtp.example.test",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "sender@example.test",
            "SMTP_FROM_EMAIL": "sender@example.test",
            "SMTP_USE_SSL": "false",
            "SMTP_USE_STARTTLS": "true",
            "STUDENT_ACTIVATION_URL": "https://portal.example.test/student-activate",
        }, clear=False):
            summary = process_pending_activation_emails(limit=1)

        self.assertEqual(summary, {"attempted": 1, "sent": 1, "failed": 0, "skipped": 0})
        server = smtp.return_value.__enter__.return_value
        message = server.send_message.call_args.args[0]
        self.assertEqual(message["To"], email)

        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, attempts, sent_at IS NOT NULL
                    FROM student_activation_email_jobs
                    WHERE account_id = %s;
                    """,
                    (account_id,),
                )
                self.assertEqual(cur.fetchone(), ("SENT", 1, True))

    def test_activation_creates_credentials_and_consumes_token(self):
        account_id, _student_id, _email, token = self._new_activation_fixture()
        request = {
            "headers": {"X-Requested-With": "XMLHttpRequest"},
            "json": {
                "token": token,
                "password": "synthetic-password-123",
                "confirm_password": "synthetic-password-123",
            },
        }
        client = app.test_client()
        self.assertEqual(
            client.post("/api/student/activation/complete", **request).status_code,
            200,
        )
        self.assertEqual(
            client.post("/api/student/activation/complete", **request).status_code,
            400,
        )

        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM account_credentials WHERE account_id = %s;",
                    (account_id,),
                )
                self.assertIsNotNone(cur.fetchone())
                cur.execute(
                    """
                    SELECT used_at IS NOT NULL
                    FROM student_activation_tokens
                    WHERE account_id = %s;
                    """,
                    (account_id,),
                )
                self.assertEqual(cur.fetchone(), (True,))

    def test_activation_rejects_expired_token(self):
        account_id, _student_id, _email, token = self._new_activation_fixture(-1)
        response = app.test_client().post(
            "/api/student/activation/complete",
            headers={"X-Requested-With": "XMLHttpRequest"},
            json={
                "token": token,
                "password": "synthetic-password-123",
                "confirm_password": "synthetic-password-123",
            },
        )
        self.assertEqual(response.status_code, 400)

        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM account_credentials WHERE account_id = %s;",
                    (account_id,),
                )
                self.assertIsNone(cur.fetchone())


if __name__ == "__main__":
    unittest.main()
