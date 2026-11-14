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
import smtplib
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

    @staticmethod
    def _smtp_environment():
        return patch.dict(os.environ, {
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
        }, clear=False)

    def _cancel_pending_activation_jobs(self):
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE student_activation_email_jobs
                    SET status = 'CANCELLED', locked_at = NULL,
                        next_attempt_at = NULL
                    WHERE status IN ('PENDING', 'PROCESSING');
                """)

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
        self._cancel_pending_activation_jobs()

        account_id, _student_id, email, _token = self._new_activation_fixture()
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO student_activation_email_jobs (account_id) VALUES (%s);",
                    (account_id,),
                )

        with self._smtp_environment():
            summary = process_pending_activation_emails(limit=1)

        self.assertEqual(summary, {"attempted": 1, "sent": 1, "failed": 0, "skipped": 0})
        server = smtp.return_value.__enter__.return_value
        message = server.send_message.call_args.args[0]
        self.assertEqual(message["To"], email)

        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, attempts, sent_at IS NOT NULL,
                           (
                               SELECT COUNT(*)
                               FROM student_activation_tokens t
                               WHERE t.account_id = %s AND t.used_at IS NULL
                           )
                    FROM student_activation_email_jobs
                    WHERE account_id = %s;
                    """,
                    (account_id, account_id),
                )
                self.assertEqual(cur.fetchone(), ("SENT", 1, True, 1))

    def test_bulk_import_queues_one_pending_job_for_each_registered_student(self):
        hod_account_id, _branch_id, number = self._new_hod_fixture()
        students = [
            {
                "name": "Synthetic Bulk One",
                "usn": f"4UB26BU{number:03d}",
                "email": f"bulk-one-{number}@example.test",
            },
            {
                "name": "Synthetic Bulk Two",
                "usn": f"4UB26BV{number:03d}",
                "email": f"bulk-two-{number}@example.test",
            },
        ]
        response = self._hod_client(hod_account_id).post(
            "/api/hod/students/bulk-upload/import",
            headers={"X-Requested-With": "XMLHttpRequest"},
            json={
                "students": students,
                "admission_year": 2026,
                "academic_year": 2026,
                "semester": 4,
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["registered_students"], 2)
        self.assertEqual(payload["rejected_count"], 0)
        self.assertEqual(payload["activation_emails_queued"], 2)
        self.assertEqual(payload["activation_emails_pending"], 2)
        self.assertEqual(payload["activation_emails_sent"], 0)
        self.assertEqual(payload["activation_emails_failed"], 0)

        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT a.email, s.usn, j.status
                    FROM student_activation_email_jobs j
                    JOIN accounts a ON a.id = j.account_id
                    JOIN students s ON s.account_id = a.id
                    WHERE a.email = ANY(%s)
                    ORDER BY a.email;
                """, ([student["email"] for student in students],))
                rows = cur.fetchall()

        self.assertEqual(rows, [
            (students[0]["email"], students[0]["usn"], "PENDING"),
            (students[1]["email"], students[1]["usn"], "PENDING"),
        ])

    def test_bulk_import_rejects_conflicts_without_queuing_an_extra_job(self):
        hod_account_id, _branch_id, number = self._new_hod_fixture()
        duplicate_email = f"bulk-duplicate-{number}@example.test"
        individual = self._hod_client(hod_account_id).post(
            "/api/hod/students",
            headers={"X-Requested-With": "XMLHttpRequest"},
            json={
                "name": "Existing Student",
                "usn": f"4UB26BW{number:03d}",
                "email": duplicate_email,
                "semester": 4,
                "admission_year": 2026,
                "academic_year": 2026,
            },
        )
        self.assertEqual(individual.status_code, 201)

        accepted_email = f"bulk-accepted-{number}@example.test"
        response = self._hod_client(hod_account_id).post(
            "/api/hod/students/bulk-upload/import",
            headers={"X-Requested-With": "XMLHttpRequest"},
            json={
                "students": [
                    {
                        "name": "Duplicate Email",
                        "usn": f"4UB26BX{number:03d}",
                        "email": duplicate_email,
                    },
                    {
                        "name": "Accepted Student",
                        "usn": f"4UB26BY{number:03d}",
                        "email": accepted_email,
                    },
                ],
                "admission_year": 2026,
                "academic_year": 2026,
                "semester": 4,
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["registered_students"], 1)
        self.assertEqual(payload["rejected_count"], 1)
        self.assertEqual(payload["activation_emails_queued"], 1)

        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT a.email, COUNT(j.id)
                    FROM accounts a
                    LEFT JOIN student_activation_email_jobs j ON j.account_id = a.id
                    WHERE a.email = ANY(%s)
                    GROUP BY a.email
                    ORDER BY a.email;
                """, ([duplicate_email, accepted_email],))
                rows = cur.fetchall()

        self.assertEqual(rows, [
            (accepted_email, 1),
            (duplicate_email, 1),
        ])

    def test_bulk_import_rejects_invalid_rows_before_any_activation_job_is_created(self):
        hod_account_id, _branch_id, number = self._new_hod_fixture()
        invalid_email = f"invalid-bulk-{number}"
        response = self._hod_client(hod_account_id).post(
            "/api/hod/students/bulk-upload/import",
            headers={"X-Requested-With": "XMLHttpRequest"},
            json={
                "students": [{
                    "name": "Invalid Email Student",
                    "usn": f"4UB26BZ{number:03d}",
                    "email": invalid_email,
                }],
                "admission_year": 2026,
                "academic_year": 2026,
                "semester": 4,
            },
        )

        self.assertEqual(response.status_code, 400)
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*)
                    FROM student_activation_email_jobs j
                    JOIN accounts a ON a.id = j.account_id
                    WHERE a.email = %s;
                """, (invalid_email,))
                self.assertEqual(cur.fetchone(), (0,))

    @patch("app.smtplib.SMTP")
    def test_permanent_smtp_refusal_never_marks_an_activation_job_sent(self, smtp):
        self._cancel_pending_activation_jobs()
        account_id, _student_id, email, _token = self._new_activation_fixture()
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO student_activation_email_jobs (account_id) VALUES (%s);",
                    (account_id,),
                )

        smtp.return_value.__enter__.return_value.send_message.side_effect = (
            smtplib.SMTPRecipientsRefused({email: (550, b"synthetic rejection")})
        )
        with self._smtp_environment():
            summary = process_pending_activation_emails(limit=1)

        self.assertEqual(summary, {"attempted": 1, "sent": 0, "failed": 1, "skipped": 0})
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT status, attempts, sent_at IS NULL, failure_kind
                    FROM student_activation_email_jobs
                    WHERE account_id = %s;
                """, (account_id,))
                self.assertEqual(cur.fetchone(), ("FAILED", 1, True, "PERMANENT"))

    @patch("app.smtplib.SMTP")
    def test_temporary_smtp_failure_retries_then_records_sent(self, smtp):
        self._cancel_pending_activation_jobs()
        account_id, _student_id, _email, _token = self._new_activation_fixture()
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO student_activation_email_jobs (account_id) VALUES (%s);",
                    (account_id,),
                )

        smtp.return_value.__enter__.return_value.send_message.side_effect = TimeoutError(
            "synthetic timeout"
        )
        with self._smtp_environment():
            first_summary = process_pending_activation_emails(limit=1)
        self.assertEqual(first_summary, {"attempted": 1, "sent": 0, "failed": 1, "skipped": 0})

        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT status, attempts, failure_kind, next_attempt_at > CURRENT_TIMESTAMP
                    FROM student_activation_email_jobs
                    WHERE account_id = %s;
                """, (account_id,))
                self.assertEqual(cur.fetchone(), ("PENDING", 1, "TEMPORARY", True))
                cur.execute("""
                    UPDATE student_activation_email_jobs
                    SET next_attempt_at = CURRENT_TIMESTAMP - INTERVAL '1 second'
                    WHERE account_id = %s;
                """, (account_id,))

        smtp.return_value.__enter__.return_value.send_message.side_effect = None
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        with self._smtp_environment():
            second_summary = process_pending_activation_emails(limit=1)
        self.assertEqual(second_summary, {"attempted": 1, "sent": 1, "failed": 0, "skipped": 0})

        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT status, attempts, sent_at IS NOT NULL, failure_kind
                    FROM student_activation_email_jobs
                    WHERE account_id = %s;
                """, (account_id,))
                self.assertEqual(cur.fetchone(), ("SENT", 2, True, None))

    @patch("app.smtplib.SMTP")
    def test_one_bulk_invitation_failure_does_not_block_later_jobs(self, smtp):
        self._cancel_pending_activation_jobs()
        first_account_id, _first_student_id, first_email, _token = self._new_activation_fixture()
        second_account_id, _second_student_id, second_email, _token = self._new_activation_fixture()
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO student_activation_email_jobs (account_id) VALUES (%s), (%s);",
                    (first_account_id, second_account_id),
                )

        smtp.return_value.__enter__.return_value.send_message.side_effect = [
            smtplib.SMTPRecipientsRefused({first_email: (550, b"synthetic rejection")}),
            {},
        ]
        with self._smtp_environment():
            summary = process_pending_activation_emails(limit=2)

        self.assertEqual(summary, {"attempted": 2, "sent": 1, "failed": 1, "skipped": 0})
        server = smtp.return_value.__enter__.return_value
        self.assertEqual(server.send_message.call_count, 2)
        self.assertEqual(
            [call.args[0]["To"] for call in server.send_message.call_args_list],
            [first_email, second_email],
        )
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT a.email, j.status
                    FROM student_activation_email_jobs j
                    JOIN accounts a ON a.id = j.account_id
                    WHERE j.account_id = ANY(%s)
                    ORDER BY j.id;
                """, ([first_account_id, second_account_id],))
                self.assertEqual(cur.fetchall(), [
                    (first_email, "FAILED"),
                    (second_email, "SENT"),
                ])

    @patch("app.smtplib.SMTP")
    def test_worker_honors_batch_limit_for_pending_activation_jobs(self, smtp):
        self._cancel_pending_activation_jobs()
        account_ids = []
        for _ in range(3):
            account_id, _student_id, _email, _token = self._new_activation_fixture()
            account_ids.append(account_id)
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO student_activation_email_jobs (account_id) VALUES (%s);",
                    [(account_id,) for account_id in account_ids],
                )

        with self._smtp_environment():
            summary = process_pending_activation_emails(limit=2)

        self.assertEqual(summary, {"attempted": 2, "sent": 2, "failed": 0, "skipped": 0})
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT status, COUNT(*)
                    FROM student_activation_email_jobs
                    WHERE account_id = ANY(%s)
                    GROUP BY status
                    ORDER BY status;
                """, (account_ids,))
                self.assertEqual(cur.fetchall(), [("PENDING", 1), ("SENT", 2)])

    def test_pending_resend_reuses_the_single_outbox_job(self):
        hod_account_id, _branch_id, number = self._new_hod_fixture()
        email = f"resend-{number}@example.test"
        registered = self._hod_client(hod_account_id).post(
            "/api/hod/students",
            headers={"X-Requested-With": "XMLHttpRequest"},
            json={
                "name": "Pending Resend Student",
                "usn": f"4UB26CA{number:03d}",
                "email": email,
                "semester": 4,
                "admission_year": 2026,
                "academic_year": 2026,
            },
        )
        self.assertEqual(registered.status_code, 201)
        student_id = registered.get_json()["student"]["id"]

        client = self._hod_client(hod_account_id)
        first = client.post(
            f"/api/hod/students/{student_id}/resend-activation",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        second = client.post(
            f"/api/hod/students/{student_id}/resend-activation",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.get_json()["activation_email_status"], "PENDING")

        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT a.email, COUNT(j.id), MIN(j.status), MIN(j.attempts)
                    FROM accounts a
                    JOIN student_activation_email_jobs j ON j.account_id = a.id
                    WHERE a.email = %s
                    GROUP BY a.email;
                """, (email,))
                self.assertEqual(cur.fetchone(), (email, 1, "PENDING", 0))

    @patch("app.smtplib.SMTP")
    def test_resend_worker_delivers_to_the_registered_student_email(self, smtp):
        self._cancel_pending_activation_jobs()
        hod_account_id, _branch_id, number = self._new_hod_fixture()
        email = f"resend-delivery-{number}@example.test"
        registered = self._hod_client(hod_account_id).post(
            "/api/hod/students",
            headers={"X-Requested-With": "XMLHttpRequest"},
            json={
                "name": "Resend Delivery Student",
                "usn": f"4UB26CB{number:03d}",
                "email": email,
                "semester": 4,
                "admission_year": 2026,
                "academic_year": 2026,
            },
        )
        self.assertEqual(registered.status_code, 201)
        student_id = registered.get_json()["student"]["id"]
        resent = self._hod_client(hod_account_id).post(
            f"/api/hod/students/{student_id}/resend-activation",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(resent.status_code, 200)

        with self._smtp_environment():
            summary = process_pending_activation_emails(limit=1)
        self.assertEqual(summary, {"attempted": 1, "sent": 1, "failed": 0, "skipped": 0})
        message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
        self.assertEqual(message["To"], email)

    def test_activated_student_cannot_receive_another_activation_invitation(self):
        hod_account_id, _branch_id, number = self._new_hod_fixture()
        registered = self._hod_client(hod_account_id).post(
            "/api/hod/students",
            headers={"X-Requested-With": "XMLHttpRequest"},
            json={
                "name": "Activated Student",
                "usn": f"4UB26CC{number:03d}",
                "email": f"activated-{number}@example.test",
                "semester": 4,
                "admission_year": 2026,
                "academic_year": 2026,
            },
        )
        self.assertEqual(registered.status_code, 201)
        student_id = registered.get_json()["student"]["id"]
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT account_id FROM students WHERE id = %s;",
                    (student_id,),
                )
                account_id = cur.fetchone()[0]
                cur.execute("""
                    INSERT INTO account_credentials (account_id, password_hash)
                    VALUES (%s, 'synthetic-password-hash');
                """, (account_id,))

        response = self._hod_client(hod_account_id).post(
            f"/api/hod/students/{student_id}/resend-activation",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 404)

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
