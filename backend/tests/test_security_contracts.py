"""Database-safe regression tests for request guards and ballot separation.

These tests intentionally exercise only routes that are rejected before a
database lookup. They are safe to run against a configured production-like
database because they do not create, update, or query application records.
"""

from pathlib import Path
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import smtplib
import inspect

# Make discovery from either the repository root or backend directory work.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import (
    app,
    CANDIDATE_SYMBOLS,
    COLLEGE_ELECTION_POLICIES,
    compute_audit_event_hash,
    compute_election_result_commitment,
    is_retryable_email_failure,
    send_email_verification_otp,
    send_hod_setup_email,
    send_reset_email,
    send_student_activation_email,
    valid_email_address,
    create_principal_election,
    cast_student_vote,
    import_hod_students_bulk,
    _principal_eligible_candidates,
)


class AuthorizationAndBallotContractTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def _set_session_role(self, role):
        with self.client.session_transaction() as session_data:
            session_data["account_id"] = 999999999
            session_data["role"] = role

    def test_state_changing_api_requires_request_verification_header(self):
        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "error")

    def test_logout_with_request_verification_header_is_safe_when_anonymous(self):
        response = self.client.post(
            "/api/auth/logout",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_student_session_cannot_reach_principal_or_hod_routes(self):
        self._set_session_role("STUDENT")
        principal = self.client.get("/api/principal/dashboard")
        hod = self.client.get("/api/hod/elections")
        self.assertEqual(principal.status_code, 403)
        self.assertEqual(hod.status_code, 403)

    def test_hod_session_cannot_reach_principal_or_student_routes(self):
        self._set_session_role("HOD")
        principal = self.client.get("/api/principal/elections")
        student = self.client.get("/api/student/dashboard")
        self.assertEqual(principal.status_code, 403)
        self.assertEqual(student.status_code, 403)

    @patch.object(app.logger, "exception")
    @patch("app.get_db_connection", side_effect=RuntimeError("database unavailable"))
    def test_hod_database_outage_returns_a_json_service_error(self, _connection, logger):
        self._set_session_role("HOD")
        response = self.client.get("/api/hod/elections")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["status"], "error")
        logger.assert_called_once()

    def test_principal_session_cannot_reach_hod_or_student_routes(self):
        self._set_session_role("PRINCIPAL")
        hod = self.client.get("/api/hod/students")
        student = self.client.get("/api/student/voting-history")
        self.assertEqual(hod.status_code, 403)
        self.assertEqual(student.status_code, 403)

    def test_activation_endpoint_rejects_malformed_token_without_database_use(self):
        response = self.client.post(
            "/api/student/activation/complete",
            headers={"X-Requested-With": "XMLHttpRequest"},
            json={"token": "", "password": "password", "confirm_password": "password"},
        )
        self.assertEqual(response.status_code, 400)

    def test_schema_keeps_ballots_separate_from_voter_identity(self):
        schema = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(
            encoding="utf-8"
        )
        ballot_section = schema.split("CREATE TABLE ballots", 1)[1].split(
            "CREATE TABLE voter_participation", 1
        )[0]
        participation_section = schema.split("CREATE TABLE voter_participation", 1)[1].split(
            "CREATE TABLE audit_events", 1
        )[0]
        self.assertNotIn("student_id", ballot_section.lower())
        self.assertIn("PRIMARY KEY (election_id, student_id)", participation_section)

    def test_candidate_symbols_are_server_owned_and_schema_backed(self):
        response = self.client.get("/api/candidate-symbols")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["symbols"], list(CANDIDATE_SYMBOLS))
        schema = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("symbol_key VARCHAR(32)", schema)
        self.assertIn("uq_candidates_election_symbol_key", schema)

    def test_audit_hash_is_deterministic_domain_separated_and_tamper_evident(self):
        previous = bytes(32)
        timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        payload = {"event": "candidate-approved", "candidate_id": 7}
        version_two = compute_audit_event_hash(
            previous, "CANDIDATE_APPROVED", payload, timestamp, 2
        )
        self.assertEqual(
            version_two,
            compute_audit_event_hash(
                previous, "CANDIDATE_APPROVED", dict(reversed(list(payload.items()))), timestamp, 2
            ),
        )
        self.assertNotEqual(
            version_two,
            compute_audit_event_hash(previous, "CANDIDATE_APPROVED", payload, timestamp, 1),
        )
        self.assertNotEqual(
            version_two,
            compute_audit_event_hash(
                previous, "CANDIDATE_APPROVED", {**payload, "candidate_id": 8}, timestamp, 2
            ),
        )

    def test_result_commitment_is_deterministic_and_contains_only_aggregate_input(self):
        aggregate = {
            "version": 1,
            "election_id": 4,
            "candidate_totals": [
                {"candidate_id": 2, "vote_count": 14},
                {"candidate_id": 9, "vote_count": 11},
            ],
            "eligible_voters": 40,
            "participation_count": 25,
            "ballot_count": 25,
        }
        commitment = compute_election_result_commitment(aggregate)
        self.assertEqual(commitment, compute_election_result_commitment(dict(aggregate)))
        self.assertNotEqual(
            commitment,
            compute_election_result_commitment({**aggregate, "ballot_count": 24}),
        )
        self.assertEqual(len(commitment), 64)

    def test_email_address_validation_rejects_header_injection(self):
        self.assertTrue(valid_email_address("student@example.edu"))
        self.assertFalse(valid_email_address("student@example"))
        self.assertFalse(valid_email_address("student@example.edu\r\nBcc: victim@example.edu"))

    def test_branded_email_templates_render_plain_and_html_without_sending(self):
        with patch("app.deliver_email") as deliver:
            send_student_activation_email(
                "student@example.edu", "Synthetic Student", "4UB23CS026", "test-token"
            )
            send_email_verification_otp("student@example.edu", "123456")
            send_hod_setup_email(
                "hod@example.edu", "test-token", "Synthetic HOD", "Computer Science"
            )
            send_reset_email("principal@example.edu", "test-token", "PRINCIPAL")

        self.assertEqual(deliver.call_count, 4)
        for call in deliver.call_args_list:
            message = call.args[0]
            self.assertIn("UBDTCE", message["Subject"] + message["From"])
            self.assertIsNotNone(message.get_body(preferencelist=("plain",)))
            self.assertIsNotNone(message.get_body(preferencelist=("html",)))

    def test_smtp_retry_classification_handles_temporary_and_permanent_failures(self):
        self.assertTrue(is_retryable_email_failure(smtplib.SMTPResponseException(421, b"busy")))
        self.assertFalse(is_retryable_email_failure(smtplib.SMTPResponseException(550, b"rejected")))
        self.assertTrue(is_retryable_email_failure(TimeoutError("test timeout")))

    def test_presidential_voter_snapshot_is_not_limited_to_cr_holders(self):
        source = inspect.getsource(create_principal_election)
        self.assertNotIn("AND s.is_cr = TRUE", source)
        self.assertIn("the CR-winner rule applies to candidates, not to voters", source)

    def test_college_candidate_policy_is_enforced_server_side(self):
        self.assertEqual(
            COLLEGE_ELECTION_POLICIES["PRESIDENT"]["winner_types"], ("CR",)
        )
        self.assertEqual(
            COLLEGE_ELECTION_POLICIES["JOINT_SECRETARY"]["winner_types"], ("CR", "FR")
        )
        self.assertEqual(
            COLLEGE_ELECTION_POLICIES["CULTURAL"]["winner_types"], ()
        )
        source = inspect.getsource(_principal_eligible_candidates)
        self.assertIn("cardinality(%s::text[]) = 0", source)
        self.assertIn("branch_election.election_type = ANY(%s::text[])", source)
        self.assertIn("branch_election.status = 'CLOSED'", source)

    def test_vote_transaction_rechecks_state_and_audits_without_voter_identity(self):
        source = inspect.getsource(cast_student_vote)
        self.assertIn("FOR SHARE OF s, a, b", source)
        self.assertIn('write_audit_event(cur, "VOTE_RECORDED"', source)
        vote_audit_segment = source.split('write_audit_event(cur, "VOTE_RECORDED"', 1)[1]
        self.assertNotIn("student_id", vote_audit_segment.split("}, election_id)", 1)[0])
        self.assertNotIn("candidate_id", vote_audit_segment.split("}, election_id)", 1)[0])

    def test_bulk_import_uses_row_savepoints_for_partial_duplicate_recovery(self):
        source = inspect.getsource(import_hod_students_bulk)
        self.assertIn("SAVEPOINT", source)
        self.assertIn("psycopg.errors.UniqueViolation", source)

    def test_election_forms_send_the_complete_academic_cohort(self):
        root = Path(__file__).resolve().parents[2]
        hod_dashboard = (root / "frontend" / "src" / "HODDashboard.jsx").read_text(
            encoding="utf-8"
        )
        principal_app = (root / "frontend" / "src" / "App.jsx").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "Academic year<select value={electionForm.academic_year}",
            hod_dashboard,
        )
        self.assertIn(
            "academic_year: Number(electionForm.academic_year)", hod_dashboard
        )
        self.assertIn("presidentAcademicYear", principal_app)
        self.assertIn(
            "requestBody.academic_year = Number(presidentAcademicYear);",
            principal_app,
        )

    def test_student_dashboard_keeps_available_sections_usable(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "frontend"
            / "src"
            / "StudentDashboard.jsx"
        ).read_text(encoding="utf-8")
        self.assertIn("Promise.allSettled", source)
        self.assertIn("AbortController", source)

    def test_migration_manifest_has_a_tracked_safe_order(self):
        from migrate import MIGRATIONS, pending_migrations

        versions = [migration.version for migration in MIGRATIONS]
        self.assertEqual(
            versions,
            [
                "001_voting_reliability",
                "002_email_management",
                "003_hod_management",
                "004_academic_year_eligibility",
                "005_integrity_symbols_outbox",
                "006_performance_indexes",
                "007_college_election_categories",
                "008_academic_year_index_repair",
            ],
        )
        self.assertEqual(list(pending_migrations({})), list(MIGRATIONS))
        with self.assertRaises(RuntimeError):
            list(pending_migrations({"001_voting_reliability": "incorrect"}))
        with self.assertRaises(RuntimeError):
            list(pending_migrations({
                "001_voting_reliability": MIGRATIONS[0].checksum,
                "003_hod_management": MIGRATIONS[2].checksum,
            }))

    def test_schema_supports_college_election_position_names(self):
        schema = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(
            encoding="utf-8"
        )
        migration = (
            Path(__file__).resolve().parents[1]
            / "college_election_categories_migration.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("position_name VARCHAR(120)", schema)
        self.assertIn("'JOINT_SECRETARY'", schema)
        self.assertIn("ADD COLUMN IF NOT EXISTS position_name", migration)


if __name__ == "__main__":
    unittest.main()
