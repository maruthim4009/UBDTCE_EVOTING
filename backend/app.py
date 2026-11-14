
import os
import hashlib
import secrets
import smtplib
import ssl
import hmac
import json
from datetime import timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html import escape
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import csv
import io
import re
import psycopg
from openpyxl import load_workbook


from dotenv import load_dotenv
from flask import Flask, jsonify, request, session, g
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db_connection

# Keep configuration discovery stable whether the API is started from the
# repository root, backend directory, a Windows service, or a test runner.
# Environment variables supplied by the host still take precedence.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = Flask(__name__)


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]

app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", ""),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE=os.getenv("SESSION_COOKIE_SAMESITE", "Lax"),
    SESSION_COOKIE_SECURE=env_bool("SESSION_COOKIE_SECURE", False),
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
)

if not app.config["SECRET_KEY"]:
    if os.getenv("APP_ENV", "development").strip().lower() == "production":
        raise RuntimeError("FLASK_SECRET_KEY must be configured in production.")
    app.logger.warning(
        "FLASK_SECRET_KEY is not configured. Authenticated sessions will not work safely."
    )

CORS(
    app,
    resources={r"/api/*": {"origins": CORS_ORIGINS}},
    supports_credentials=True,
    allow_headers=["Content-Type", "X-Requested-With"],
    methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
)

RATE_LIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
if os.getenv("APP_ENV", "development").strip().lower() == "production":
    if len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("FLASK_SECRET_KEY must contain at least 32 characters in production.")
    if RATE_LIMIT_STORAGE_URI.startswith("memory://"):
        raise RuntimeError("Configure a shared RATELIMIT_STORAGE_URI such as Redis in production.")
    if "*" in CORS_ORIGINS:
        raise RuntimeError("CORS_ORIGINS cannot contain * when credentialed CORS is enabled.")
    if not app.config["SESSION_COOKIE_SECURE"]:
        raise RuntimeError("SESSION_COOKIE_SECURE must be true in production.")

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=RATE_LIMIT_STORAGE_URI,
)


# Server-owned allow-list: symbols are persisted by key, never uploaded as
# arbitrary files. This keeps ballot presentation safe and consistent.
CANDIDATE_SYMBOLS = (
    {"key": "book", "label": "Book", "glyph": "📘"},
    {"key": "compass", "label": "Compass", "glyph": "🧭"},
    {"key": "gear", "label": "Gear", "glyph": "⚙️"},
    {"key": "lamp", "label": "Lamp", "glyph": "🪔"},
    {"key": "leaf", "label": "Leaf", "glyph": "🍃"},
    {"key": "pen", "label": "Pen", "glyph": "🖊️"},
    {"key": "shield", "label": "Shield", "glyph": "🛡️"},
    {"key": "star", "label": "Star", "glyph": "⭐"},
    {"key": "torch", "label": "Torch", "glyph": "🔦"},
    {"key": "tree", "label": "Tree", "glyph": "🌳"},
)
CANDIDATE_SYMBOL_BY_KEY = {symbol["key"]: symbol for symbol in CANDIDATE_SYMBOLS}

# College-level elections are independently managed. Candidate eligibility is
# deliberately explicit: the database has authoritative CR/FR election
# results, but no verified cultural or sporting achievement records.
COLLEGE_ELECTION_POLICIES = {
    "PRESIDENT": {
        "label": "College President",
        "eligibility": "CR_WINNER",
        "eligibility_label": "Verified winners of completed CR elections",
        "winner_types": ("CR",),
    },
    "JOINT_SECRETARY": {
        "label": "Joint Secretary",
        "eligibility": "REPRESENTATIVE_WINNER",
        "eligibility_label": "Verified winners of completed CR or FR elections",
        "winner_types": ("CR", "FR"),
    },
    "CULTURAL": {
        "label": "Cultural President",
        "eligibility": "ACTIVE_STUDENT",
        "eligibility_label": "Active students in the selected branches and cohort",
        "winner_types": (),
    },
    "SPORTS": {
        "label": "Sports President",
        "eligibility": "ACTIVE_STUDENT",
        "eligibility_label": "Active students in the selected branches and cohort",
        "winner_types": (),
    },
    "OTHER": {
        "label": "Other college representative position",
        "eligibility": "ACTIVE_STUDENT",
        "eligibility_label": "Active students in the selected branches and cohort",
        "winner_types": (),
    },
}
COLLEGE_ELECTION_TYPES = tuple(COLLEGE_ELECTION_POLICIES)

MIN_ADMISSION_YEAR = 2022
MAX_ADMISSION_YEAR = 2048
EMAIL_ADDRESS_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$",
    re.IGNORECASE,
)


def valid_email_address(value):
    """Accept a normal mailbox address and reject header-injection input."""
    if not isinstance(value, str):
        return False
    value = value.strip()
    return (
        3 <= len(value) <= 254
        and "\r" not in value
        and "\n" not in value
        and EMAIL_ADDRESS_PATTERN.fullmatch(value) is not None
    )


def valid_admission_year(value):
    return type(value) is int and MIN_ADMISSION_YEAR <= value <= MAX_ADMISSION_YEAR


def candidate_symbol_payload(symbol_key):
    """Return a presentation-safe symbol descriptor, or None for legacy data."""
    return CANDIDATE_SYMBOL_BY_KEY.get(symbol_key)


def valid_candidate_symbol(symbol_key):
    return isinstance(symbol_key, str) and symbol_key in CANDIDATE_SYMBOL_BY_KEY


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.before_request
def assign_request_id():
    """Attach a non-sensitive correlation id to every request."""
    supplied = request.headers.get("X-Request-ID", "")
    g.request_id = supplied if re.fullmatch(r"[A-Za-z0-9_-]{8,128}", supplied) else secrets.token_hex(12)


@app.after_request
def add_security_response_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Request-ID", getattr(g, "request_id", ""))
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
        )
    return response


@app.before_request
def enforce_api_csrf_header():
    """Reject browser state-changing API calls without the custom CSRF header."""
    if not request.path.startswith("/api/") or request.method in SAFE_METHODS:
        return None

    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return jsonify({
            "status": "error",
            "message": "Missing required request verification header.",
        }), 403

    origin = request.headers.get("Origin")
    if (
        os.getenv("APP_ENV", "development").strip().lower() == "production"
        and not origin
    ):
        return jsonify({
            "status": "error",
            "message": "A verified request origin is required.",
        }), 403
    if origin and origin.rstrip("/") not in CORS_ORIGINS:
        return jsonify({
            "status": "error",
            "message": "Request origin is not allowed.",
        }), 403

    return None


def login_email_rate_limit_key():
    """Rate-limit login attempts by normalized target email, not only IP."""
    data = request.get_json(silent=True) or {}
    email = data.get("email", "") if isinstance(data, dict) else ""
    if isinstance(email, str) and email.strip():
        return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    return "invalid-email"


def require_principal():
    """Return an error response unless the current session is Principal."""
    if not session.get("account_id"):
        return jsonify({
            "status": "error",
            "message": "Please log in to continue."
        }), 401

    if session.get("role") != "PRINCIPAL":
        return jsonify({
            "status": "error",
            "message": "Principal access is required."
        }), 403

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1
                    FROM accounts
                    WHERE id = %s
                      AND role = 'PRINCIPAL'
                      AND is_active = TRUE;
                """, (session["account_id"],))
                if not cur.fetchone():
                    session.clear()
                    return jsonify({
                        "status": "error",
                        "message": "Your Principal account is inactive."
                    }), 403
    except Exception:
        app.logger.exception("Principal session validation failed")
        return jsonify({
            "status": "error",
            "message": "Principal access is temporarily unavailable."
        }), 503

    return None


def require_hod():
    """Verify that the logged-in HOD has an active branch assignment."""

    if not session.get("account_id"):
        return jsonify({
            "status": "error",
            "message": "Please log in to continue."
        }), 401

    if session.get("role") != "HOD":
        return jsonify({
            "status": "error",
            "message": "HOD access is required."
        }), 403

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1
                    FROM accounts a
                    JOIN hod_assignments h
                        ON h.account_id = a.id
                    JOIN branches b
                        ON b.id = h.branch_id
                    WHERE a.id = %s
                      AND a.role = 'HOD'
                      AND a.is_active = TRUE
                      AND b.is_active = TRUE;
                """, (session["account_id"],))

                if not cur.fetchone():
                    session.clear()
                    return jsonify({
                        "status": "error",
                        "message": "Your HOD account has no active department assignment."
                    }), 403
    except Exception:
        app.logger.exception("HOD session validation failed")
        return jsonify({
            "status": "error",
            "message": "HOD access is temporarily unavailable."
        }), 503

    return None


def require_student():
    """Return an error response unless the session belongs to an active student."""
    if not session.get("account_id"):
        return jsonify({"status": "error", "message": "Please log in to continue."}), 401
    if session.get("role") != "STUDENT":
        return jsonify({"status": "error", "message": "Student access is required."}), 403

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    JOIN branches b ON b.id = s.branch_id
                    WHERE a.id = %s
                      AND a.role = 'STUDENT'
                      AND a.is_active = TRUE
                      AND b.is_active = TRUE;
                """, (session["account_id"],))
                if not cur.fetchone():
                    return jsonify({
                        "status": "error",
                        "message": "Your student account is inactive or has no active department."
                    }), 403
    except Exception:
        app.logger.exception("Student session validation failed")
        return jsonify({
            "status": "error",
            "message": "Student access is temporarily unavailable."
        }), 503
    return None


AUDIT_HASH_VERSION = 2
AUDIT_HASH_DOMAIN_V2 = b"UBDTCE-AUDIT-EVENT\x00v2\x00"


def canonical_json(value):
    """Produce deterministic JSON for integrity commitments."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_audit_event_hash(previous_hash, event_type, event_data, created_at, hash_version):
    """Calculate a versioned audit-chain hash without database state.

    Version 1 remains only for verification of historic records. Version 2
    adds explicit domain separation so audit hashes cannot be misused as a
    commitment of another type.
    """
    if not isinstance(event_type, str):
        raise ValueError("Audit event type must be text.")
    if hash_version not in (1, 2):
        raise ValueError("Unsupported audit hash version.")
    if not isinstance(previous_hash, (bytes, bytearray)) or len(previous_hash) != 32:
        raise ValueError("Audit previous hash must be 32 bytes.")
    if created_at.tzinfo is None:
        raise ValueError("Audit timestamps must be timezone-aware.")
    canonical_data = canonical_json(event_data)
    common = (
        bytes(previous_hash)
        + event_type.encode("utf-8")
        + b"\x00"
        + canonical_data.encode("utf-8")
        + b"\x00"
        + created_at.astimezone(timezone.utc).isoformat().encode("utf-8")
    )
    hash_input = common if hash_version == 1 else AUDIT_HASH_DOMAIN_V2 + common
    return hashlib.sha256(hash_input).digest()


def write_audit_event(cur, event_type, event_data, election_id=None):
    """Append a versioned SHA-256-linked audit event in the caller transaction."""
    cur.execute("SELECT pg_advisory_xact_lock(%s);", (7419202601,))
    cur.execute("""
        SELECT event_hash
        FROM audit_events
        ORDER BY id DESC
        LIMIT 1;
    """)
    previous_row = cur.fetchone()
    previous_hash = bytes(previous_row[0]) if previous_row else bytes(32)

    cur.execute("SELECT clock_timestamp();")
    created_at = cur.fetchone()[0]
    canonical_data = canonical_json(event_data)
    event_hash = compute_audit_event_hash(
        previous_hash, event_type, event_data, created_at, AUDIT_HASH_VERSION
    )

    cur.execute("""
        INSERT INTO audit_events (
            election_id, event_type, event_data,
            previous_hash, event_hash, created_at, hash_version
        )
        VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s);
    """, (
        election_id,
        event_type,
        canonical_data,
        previous_hash,
        event_hash,
        created_at,
        AUDIT_HASH_VERSION,
    ))


def verify_audit_chain(cur):
    """Verify the complete chain without returning sensitive audit data."""
    cur.execute("""
        SELECT id, event_type, event_data, previous_hash, event_hash,
               created_at, hash_version
        FROM audit_events
        ORDER BY id ASC;
    """)
    expected_previous = bytes(32)
    checked = 0
    for row in cur:
        event_id, event_type, event_data, previous_hash, event_hash, created_at, hash_version = row
        stored_previous = bytes(previous_hash) if previous_hash is not None else bytes(32)
        stored_hash = bytes(event_hash)
        try:
            expected_hash = compute_audit_event_hash(
                stored_previous, event_type, event_data, created_at, hash_version
            )
        except (TypeError, ValueError):
            return {"valid": False, "checked": checked, "first_invalid_event_id": event_id}
        if stored_previous != expected_previous or not hmac.compare_digest(stored_hash, expected_hash):
            return {"valid": False, "checked": checked, "first_invalid_event_id": event_id}
        expected_previous = stored_hash
        checked += 1
    return {"valid": True, "checked": checked, "first_invalid_event_id": None}


ELECTION_RESULT_COMMITMENT_DOMAIN = b"UBDTCE-ELECTION-RESULT\x00v1\x00"


def compute_election_result_commitment(payload):
    """Return the domain-separated SHA-256 aggregate result commitment."""
    return hashlib.sha256(
        ELECTION_RESULT_COMMITMENT_DOMAIN + canonical_json(payload).encode("utf-8")
    ).hexdigest()


def election_result_commitment(cur, election_id):
    """Commit a closed election's aggregate outcome without voter identity.

    The returned SHA-256 value is local integrity evidence. It is not a
    blockchain transaction and includes no email, USN, participation row, or
    ballot reference. Candidate IDs are sufficient to recompute the public
    aggregate from the protected ballot box.
    """
    cur.execute("""
        SELECT c.id, COUNT(b.id)
        FROM candidates c
        LEFT JOIN ballots b
          ON b.election_id = c.election_id
         AND b.candidate_id = c.id
        WHERE c.election_id = %s
          AND c.is_approved = TRUE
          AND c.review_status = 'APPROVED'
        GROUP BY c.id
        ORDER BY c.id;
    """, (election_id,))
    candidate_totals = [
        {"candidate_id": row[0], "vote_count": row[1]}
        for row in cur.fetchall()
    ]
    cur.execute("""
        SELECT
            (SELECT COUNT(*) FROM voter_eligibility WHERE election_id = %s),
            (SELECT COUNT(*) FROM voter_participation WHERE election_id = %s),
            (SELECT COUNT(*) FROM ballots WHERE election_id = %s);
    """, (election_id, election_id, election_id))
    eligible_voters, participation_count, ballot_count = cur.fetchone()
    payload = {
        "version": 1,
        "election_id": election_id,
        "candidate_totals": candidate_totals,
        "eligible_voters": eligible_voters,
        "participation_count": participation_count,
        "ballot_count": ballot_count,
    }
    commitment = compute_election_result_commitment(payload)
    return payload, commitment


def write_election_result_commitment(cur, election_id):
    """Write one aggregate result commitment per closed election."""
    cur.execute("""
        SELECT 1 FROM audit_events
        WHERE election_id = %s AND event_type = 'ELECTION_RESULT_COMMITTED'
        LIMIT 1;
    """, (election_id,))
    if cur.fetchone():
        return None
    payload, commitment = election_result_commitment(cur, election_id)
    write_audit_event(cur, "ELECTION_RESULT_COMMITTED", {
        "commitment_version": 1,
        "result_commitment_sha256": commitment,
        "eligible_voters": payload["eligible_voters"],
        "participation_count": payload["participation_count"],
        "ballot_count": payload["ballot_count"],
    }, election_id)
    return commitment


# FIX: Use RESET_URL consistently in the email function below.
RESET_URL = os.getenv(
    "RESET_URL",
    "http://localhost:5173/reset-password"
)
STUDENT_RESET_URL = os.getenv(
    "STUDENT_RESET_URL",
    "http://localhost:5173/student-reset-password"
)

RESET_TOKEN_MINUTES = 15
HOD_SETUP_TOKEN_HOURS = 24
ACTIVATION_EMAIL_JOB_LEASE_MINUTES = 15
ACTIVATION_EMAIL_MAX_ATTEMPTS = 5


def _smtp_port():
    """Return a validated SMTP port without exposing configuration values."""
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as exc:
        raise RuntimeError("SMTP_PORT must be a valid TCP port.") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("SMTP_PORT must be a valid TCP port.")
    return port


def configured_sender_address():
    """Return the verified envelope/header sender configured for this service."""
    return os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_EMAIL", "")).strip()


def set_message_identity_headers(message):
    """Add ordinary RFC mail identity headers without exposing configuration."""
    sender = configured_sender_address()
    # The fallback is used only while rendering/mocking messages. deliver_email
    # rejects a missing or invalid configured sender before any network call.
    if not valid_email_address(sender):
        sender = "no-reply@ubdtce.invalid"
    message["From"] = formataddr(("UBDTCE Secure E-Voting", sender))
    message["Reply-To"] = sender
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid("ubdtce", domain=sender.rsplit("@", 1)[-1])


def deliver_email(message):
    """Deliver one message, or deliberately suppress it in safe test mode.

    `EMAIL_TEST_MODE=true` is intentionally opt-in and never records a raw
    activation/reset token. It lets tests exercise the complete application
    workflow without contacting real student addresses.
    """
    if env_bool("EMAIL_TEST_MODE", False):
        app.logger.info("Email delivery suppressed because EMAIL_TEST_MODE is enabled.")
        return

    smtp_email = os.getenv("SMTP_EMAIL")
    smtp_password = os.getenv("SMTP_APP_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_username = os.getenv("SMTP_USERNAME", smtp_email or "").strip()
    smtp_from_email = configured_sender_address()
    use_ssl = env_bool("SMTP_USE_SSL", False)
    use_starttls = env_bool("SMTP_USE_STARTTLS", True)

    if (
        not smtp_email
        or not valid_email_address(smtp_email)
        or not valid_email_address(smtp_from_email)
        or not smtp_password
        or not smtp_host
        or not smtp_username
        or not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", smtp_host)
        or "\r" in smtp_username
        or "\n" in smtp_username
        or not (use_ssl or use_starttls)
    ):
        app.logger.error("SMTP configuration is missing.")
        raise RuntimeError("Email service is not configured.")

    port = _smtp_port()
    timeout_seconds = 15
    if use_ssl:
        with smtplib.SMTP_SSL(
            smtp_host,
            port,
            timeout=timeout_seconds,
            context=ssl.create_default_context(),
        ) as server:
            server.ehlo()
            server.login(smtp_username, smtp_password)
            server.send_message(message)
        return

    with smtplib.SMTP(smtp_host, port, timeout=timeout_seconds) as server:
        server.ehlo()
        if use_starttls:
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        server.login(smtp_username, smtp_password)
        server.send_message(message)


def is_retryable_email_failure(exc):
    """Classify SMTP failures without retaining provider details in the outbox."""
    if isinstance(exc, smtplib.SMTPResponseException):
        return 400 <= exc.smtp_code < 500
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        response_codes = [details[0] for details in exc.recipients.values()]
        return bool(response_codes) and all(400 <= code < 500 for code in response_codes)
    # SMTPResponseException inherits from OSError on supported Python versions,
    # so response-code classification must happen before the generic network
    # failure branch. A 5xx recipient rejection is permanent, not retryable.
    if isinstance(exc, (TimeoutError, OSError, smtplib.SMTPServerDisconnected)):
        return True
    return False


def build_branded_email(
    subject,
    recipient,
    heading,
    eyebrow,
    plain_body,
    html_body,
    *,
    action_label=None,
    action_url=None,
    expires_text=None,
):
    """Create the common responsive UBDTCE email shell.

    Callers provide only escaped display fragments and an opaque URL where
    appropriate. This helper intentionally does not log a recipient, token,
    URL, or message body.
    """
    message = EmailMessage()
    message["Subject"] = subject
    set_message_identity_headers(message)
    message["To"] = recipient
    message.set_content(
        "UBDTCE SECURE E-VOTING SYSTEM\n\n"
        f"{heading}\n\n{plain_body}\n\n"
        "Security notice: Never share a password, verification code, or secure link.\n"
        "UBDTCE Secure E-Voting Team"
    )

    action_markup = ""
    if action_label and action_url:
        action_markup = (
            '<p style="margin:28px 0;text-align:center">'
            f'<a href="{escape(action_url, quote=True)}" '
            'style="display:inline-block;background:#142d4e;border:1px solid #d7b66d;'
            'border-radius:7px;color:#ffffff;font-size:14px;font-weight:700;'
            'padding:13px 24px;text-decoration:none">'
            f"{escape(action_label)}</a></p>"
        )
    expiry_markup = (
        f'<p style="color:#475569;font-size:13px;line-height:1.7">{escape(expires_text)}</p>'
        if expires_text else ""
    )
    message.add_alternative(
        "<!doctype html><html lang=\"en\"><head>"
        "<meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{escape(heading)}</title></head>"
        "<body style=\"margin:0;padding:24px 12px;background:#f1f4f8;font-family:Arial,Helvetica,sans-serif;color:#263449\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\"><tr><td align=\"center\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" "
        "style=\"max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden\">"
        "<tr><td align=\"center\" style=\"background:#142d4e;padding:28px 20px\">"
        "<div style=\"display:inline-block;width:42px;height:42px;line-height:42px;background:#d7b66d;"
        "border-radius:8px;color:#142d4e;font-size:23px;font-weight:700\">U</div>"
        "<h1 style=\"margin:12px 0 5px;color:#ffffff;font-size:23px;letter-spacing:1px\">UBDTCE</h1>"
        "<p style=\"margin:0;color:#e4cc91;font-size:11px;letter-spacing:1.8px\">SECURE E-VOTING SYSTEM</p>"
        "</td></tr><tr><td style=\"padding:30px 26px\">"
        f"<p style=\"margin:0 0 8px;color:#9a722b;font-size:11px;font-weight:700;letter-spacing:1.4px\">{escape(eyebrow)}</p>"
        f"<h2 style=\"margin:0 0 16px;color:#142d4e;font-size:24px;line-height:1.3\">{escape(heading)}</h2>"
        f"{html_body}{action_markup}{expiry_markup}"
        "<div style=\"background:#fff8e8;border-left:3px solid #c6a45b;margin-top:22px;padding:12px 14px\">"
        "<p style=\"margin:0;color:#66552f;font-size:12px;line-height:1.7\"><strong>Security notice:</strong> "
        "Never share a password, verification code, or secure link. If you did not expect this message, contact the college administration.</p>"
        "</div></td></tr><tr><td align=\"center\" style=\"background:#f8fafc;border-top:1px solid #e2e8f0;padding:17px\">"
        "<p style=\"margin:0;color:#64748b;font-size:11px;line-height:1.6\">Automated security notification. Please do not reply.<br>UBDTCE Secure E-Voting System</p>"
        "</td></tr></table></td></tr></table></body></html>",
        subtype="html",
    )
    return message


def send_reset_email(email, token, account_role):
    """Send a one-time password recovery email in the shared brand style."""

    if account_role == "HOD":
        role_slug = "hod"
        reset_url = RESET_URL

    elif account_role == "STUDENT":
        role_slug = "student"
        reset_url = STUDENT_RESET_URL

    else:
        role_slug = "principal"
        reset_url = RESET_URL

    reset_link = (
    f"{reset_url}?"
    f"{urlencode({'token': token, 'role': role_slug})}"
    )

    message = build_branded_email(
        "Reset your UBDTCE E-Voting password",
        email,
        "Reset your password",
        "ACCOUNT SECURITY",
        (
            "A password reset was requested for your UBDTCE Secure E-Voting account.\n\n"
            f"Use this one-time link within {RESET_TOKEN_MINUTES} minutes:\n{reset_link}\n\n"
            "If you did not request this reset, you can safely ignore this email."
        ),
        "<p style=\"font-size:15px;line-height:1.8;color:#475569\">A password reset was requested for your account. Use the secure one-time button below to choose a new password.</p>",
        action_label="Set a new password",
        action_url=reset_link,
        expires_text=f"This one-time link expires in {RESET_TOKEN_MINUTES} minutes.",
    )
    deliver_email(message)




def send_hod_setup_email(email, token, hod_name, branch_name):
    """Send the one-time invitation that lets a newly assigned HOD create a password."""
    setup_link = f"{RESET_URL}?{urlencode({'token': token, 'role': 'hod', 'setup': '1'})}"
    safe_name = escape(hod_name)
    safe_branch = escape(branch_name)
    message = build_branded_email(
        "Create your UBDTCE HOD account password",
        email,
        "Welcome to UBDTCE Secure E-Voting",
        "HOD ACCOUNT INVITATION",
        (
            f"Hello {hod_name},\n\nThe Principal has assigned you as the HOD for {branch_name}.\n\n"
            f"Create your password with this one-time link:\n{setup_link}\n\n"
            "If you were not expecting this invitation, contact the college administration."
        ),
        f"<p style=\"font-size:15px;line-height:1.8;color:#475569\">Hello {safe_name},</p>"
        f"<p style=\"font-size:15px;line-height:1.8;color:#475569\">The Principal has assigned you as the HOD for <strong>{safe_branch}</strong>. Create your own account password to begin.</p>",
        action_label="Create HOD password",
        action_url=setup_link,
        expires_text=f"This link expires in {HOD_SETUP_TOKEN_HOURS} hours and can be used only once.",
    )
    deliver_email(message)


def send_email_verification_otp(email, otp):
    """Send a professional HTML email containing the verification OTP."""
    message = EmailMessage()
    message["Subject"] = (
        "Your Email Verification Code | UBDTCE Secure E-Voting"
    )
    set_message_identity_headers(message)
    message["To"] = email

    # Plain-text fallback for email clients that do not support HTML.
    message.set_content(
        "UBDTCE SECURE E-VOTING SYSTEM\n\n"
        "Verify your email address\n\n"
        f"Your verification code is: {otp}\n\n"
        "This code expires in 3 minutes.\n"
        "Do not share this code with anyone.\n\n"
        "If you did not request this verification, ignore this email.\n\n"
        "UBDTCE Secure E-Voting System"
    )

    # Professional HTML email with a prominent OTP box.
    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>UBDTCE Email Verification</title>
</head>
<body style="margin:0;padding:0;background:#f1f4f8;
             font-family:Arial,Helvetica,sans-serif;color:#263449;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
         style="background:#f1f4f8;padding:28px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0"
               cellpadding="0"
               style="max-width:560px;background:#ffffff;
                      border-radius:12px;overflow:hidden;">

          <tr>
            <td align="center"
                style="background:#142d4e;padding:30px 20px;">
              <div style="display:inline-block;width:48px;height:48px;
                          line-height:48px;border-radius:10px;
                          background:#d7b66d;color:#142d4e;
                          font-size:30px;font-weight:bold;">
                U
              </div>
              <h1 style="margin:14px 0 6px;color:#ffffff;
                         font-size:23px;letter-spacing:1px;">
                UBDTCE
              </h1>
              <p style="margin:0;color:#e4cc91;font-size:12px;
                        letter-spacing:2px;">
                SECURE E-VOTING SYSTEM
              </p>
            </td>
          </tr>

          <tr>
            <td style="padding:32px 26px;">
              <p style="margin:0 0 8px;color:#9a722b;font-size:11px;
                        font-weight:bold;letter-spacing:1.5px;">
                ACCOUNT SECURITY
              </p>

              <h2 style="margin:0 0 18px;color:#142d4e;
                         font-size:25px;line-height:1.3;">
                Verify your email address
              </h2>

              <p style="font-size:15px;line-height:1.8;color:#475569;">
                A request was made to add this email address to your
                UBDTCE Secure E-Voting account. Enter the verification
                code below to confirm ownership of the address.
              </p>

              <table role="presentation" width="100%" cellspacing="0"
                     cellpadding="0" style="margin:25px 0;">
                <tr>
                  <td align="center"
                      style="background:#f4f7fb;
                             border:1px solid #d7b66d;
                             border-radius:10px;padding:24px 12px;">
                    <p style="margin:0 0 14px;color:#64748b;
                              font-size:11px;font-weight:bold;
                              letter-spacing:1.5px;">
                      YOUR VERIFICATION CODE
                    </p>
                    <div style="font-size:36px;font-weight:bold;
                                letter-spacing:10px;color:#142d4e;
                                line-height:1.5;">
                      {otp}
                    </div>
                    <p style="margin:12px 0 0;color:#64748b;
                              font-size:12px;">
                      Enter this code on the verification page.
                    </p>
                  </td>
                </tr>
              </table>

              <p style="font-size:14px;line-height:1.7;color:#475569;">
                <strong style="color:#142d4e;">
                  Time limit:
                </strong>
                This code expires in 3 minutes.
              </p>

              <div style="background:#fff8e8;border-left:3px solid #c6a45b;
                          padding:13px 15px;margin-top:20px;">
                <p style="margin:0;font-size:13px;line-height:1.7;
                          color:#66552f;">
                  <strong>Security notice:</strong>
                  Never share this code with anyone. If you did not request
                  this verification, ignore this email.
                </p>
              </div>

              <p style="margin:26px 0 0;font-size:14px;line-height:1.7;
                        color:#475569;">
                Regards,<br>
                <strong style="color:#142d4e;">
                  UBDTCE Secure E-Voting Team
                </strong>
              </p>
            </td>
          </tr>

          <tr>
            <td align="center"
                style="background:#f8fafc;border-top:1px solid #e2e8f0;
                       padding:19px 15px;">
              <p style="margin:0;color:#64748b;font-size:11px;
                        line-height:1.7;">
                Automated security notification. Please do not reply.<br>
                UBDTCE Secure E-Voting System
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    message.add_alternative(html_body, subtype="html")

    deliver_email(message)
# ==========================================
# STUDENT ACCOUNT ACTIVATION: REQUEST OTP
# ==========================================

@app.post("/api/student/activation/send-otp")
@limiter.limit("5 per minute")
@limiter.limit("5 per hour")
def send_student_activation_otp():

    data = request.get_json(silent=True) or {}

    usn = data.get("usn", "")
    email = data.get("email", "")

    if not isinstance(usn, str) or not isinstance(email, str):
        return jsonify({
            "status": "error",
            "message": "Enter a valid USN and email address."
        }), 400

    usn = usn.strip().upper()
    email = email.strip().lower()

    if not re.fullmatch(r"[0-9]UB[0-9]{2}[A-Z]{2}[0-9]{3}", usn):
        return jsonify({
            "status": "error",
            "message": "Enter a valid 10-character USN."
        }), 400

    if not valid_email_address(email):
        return jsonify({
            "status": "error",
            "message": "Enter a valid email address."
        }), 400

    secret_key = app.config.get("SECRET_KEY")

    if not secret_key:
        return jsonify({
            "status": "error",
            "message": "Email verification is not configured."
        }), 500

    try:
        account_id = None
        otp = None
        challenge_id = None

        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Find the pre-registered student.
                # Do not reveal whether a USN or email exists.
                cur.execute("""
                    SELECT a.id
                    FROM accounts a
                    JOIN students s
                        ON s.account_id = a.id
                    LEFT JOIN account_credentials ac
                        ON ac.account_id = a.id
                    WHERE UPPER(s.usn) = %s
                      AND LOWER(a.email) = %s
                      AND a.role = 'STUDENT'
                      AND a.is_active = TRUE
                      AND ac.account_id IS NULL
                    FOR UPDATE OF a;
                """, (usn, email))

                account = cur.fetchone()

                if account:
                    account_id = account[0]

                    # Enforce the two-minute resend delay.
                    cur.execute("""
                        SELECT CEIL(EXTRACT(EPOCH FROM (
                            created_at
                            + INTERVAL '2 minutes'
                            - CURRENT_TIMESTAMP
                        )))::INTEGER
                        FROM email_otp_challenges
                        WHERE account_id = %s
                          AND LOWER(target_email) = %s
                        ORDER BY created_at DESC
                        LIMIT 1;
                    """, (account_id, email))

                    recent = cur.fetchone()

                    if recent and recent[0] > 0:
                        return jsonify({
                            "status": "error",
                            "message": "Please wait before requesting another code.",
                            "retry_after_seconds": recent[0]
                        }), 429

                    # Consume earlier unused challenges.
                    cur.execute("""
                        UPDATE email_otp_challenges
                        SET consumed_at = CURRENT_TIMESTAMP
                        WHERE account_id = %s
                          AND LOWER(target_email) = %s
                          AND consumed_at IS NULL;
                    """, (account_id, email))

                    otp = f"{secrets.randbelow(1_000_000):06d}"

                    otp_hash = hmac.new(
                        secret_key.encode("utf-8"),
                        otp.encode("utf-8"),
                        hashlib.sha256
                    ).digest()

                    cur.execute("""
                        INSERT INTO email_otp_challenges (
                            account_id,
                            target_email,
                            otp_hash,
                            expires_at
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            CURRENT_TIMESTAMP + INTERVAL '3 minutes'
                        )
                        RETURNING id;
                    """, (account_id, email, otp_hash))

                    challenge_id = cur.fetchone()[0]

        # Send OTP only after the database transaction commits.
        if account_id is not None:
            try:
                send_email_verification_otp(email, otp)

            except Exception:
                app.logger.exception(
                    "Student activation OTP email failed."
                )

                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE email_otp_challenges
                            SET consumed_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                              AND consumed_at IS NULL;
                        """, (challenge_id,))

                return jsonify({
                    "status": "error",
                    "message": "Verification email could not be sent. Please try again later."
                }), 503

        # Same response whether or not the details matched.
        return jsonify({
            "status": "ok",
            "message": (
                "If the details match an eligible student account, "
                "a verification code has been sent."
            ),
            "expires_in_seconds": 180,
            "resend_after_seconds": 120
        }), 200

    except Exception:
        app.logger.exception(
            "Student activation OTP request failed."
        )

        return jsonify({
            "status": "error",
            "message": "Student account verification is temporarily unavailable."
        }), 503

# ==========================================
# STUDENT: ACTIVATE ACCOUNT USING EMAIL LINK
# ==========================================

@app.post("/api/student/activation/complete")
@limiter.limit("10 per minute")
def complete_student_activation():

    data = request.get_json(silent=True) or {}

    token = data.get("token", "")
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")

    if not all(
        isinstance(value, str)
        for value in (token, password, confirm_password)
    ):
        return jsonify({
            "status": "error",
            "message": "Invalid activation details."
        }), 400

    if not token or len(token) > 200:
        return jsonify({
            "status": "error",
            "message": "Invalid or expired activation link."
        }), 400

    if len(password) < 12 or len(password) > 128:
        return jsonify({
            "status": "error",
            "message": "Password must contain 12–128 characters."
        }), 400

    if password != confirm_password:
        return jsonify({
            "status": "error",
            "message": "The passwords do not match."
        }), 400

    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).digest()

    password_hash = generate_password_hash(password)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Lock the account and validate the token.
                cur.execute("""
                    SELECT
                        t.id,
                        a.id,
                        a.email,
                        a.full_name
                    FROM student_activation_tokens t
                    JOIN accounts a ON a.id = t.account_id
                    JOIN students s ON s.account_id = a.id
                    LEFT JOIN account_credentials ac
                        ON ac.account_id = a.id
                    WHERE t.token_hash = %s
                      AND t.used_at IS NULL
                      AND t.expires_at > CURRENT_TIMESTAMP
                      AND a.role = 'STUDENT'
                      AND a.is_active = TRUE
                      AND ac.account_id IS NULL
                    FOR UPDATE OF t, a;
                """, (token_hash,))

                activation = cur.fetchone()

                if not activation:
                    return jsonify({
                        "status": "error",
                        "message": (
                            "This activation link is invalid, expired "
                            "or already used. Request a new invitation."
                        )
                    }), 400

                token_id, account_id, email, student_name = activation

                # Create the student's password credentials.
                cur.execute("""
                    INSERT INTO account_credentials (
                        account_id,
                        password_hash,
                        password_changed_at
                    )
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (account_id) DO NOTHING
                    RETURNING account_id;
                """, (account_id, password_hash))

                if not cur.fetchone():
                    return jsonify({
                        "status": "error",
                        "message": "This student account is already activated."
                    }), 409

                # Mark the activation link as used.
                cur.execute("""
                    UPDATE student_activation_tokens
                    SET used_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND used_at IS NULL;
                """, (token_id,))

                # A student may activate before a queued invitation is
                # claimed (for example after an authorized resend). Do not
                # leave that unsent job misleadingly PENDING forever.
                cur.execute("""
                    UPDATE student_activation_email_jobs
                    SET status = 'CANCELLED', locked_at = NULL,
                        next_attempt_at = NULL,
                        last_error = 'Invitation no longer needed; account activated.',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE account_id = %s
                      AND status IN ('PENDING', 'PROCESSING');
                """, (account_id,))

                # Record account activation in the audit chain.
                write_audit_event(
                    cur,
                    "STUDENT_ACCOUNT_ACTIVATED",
                    {
                        "account_id": account_id
                    }
                )

        return jsonify({
            "status": "ok",
            "message": (
                "Your student account has been activated successfully. "
                "You can now log in."
            )
        }), 200

    except Exception:
        app.logger.exception("Student account activation failed.")

        return jsonify({
            "status": "error",
            "message": "Account activation is temporarily unavailable."
        }), 503
    
# ==========================================
# STUDENT ACCOUNT ACTIVATION: VERIFY OTP
# AND CREATE PASSWORD
# ==========================================

@app.post("/api/student/activation/verify-otp")
@limiter.limit("10 per minute")
@limiter.limit("20 per hour")
def verify_student_activation_otp():

    data = request.get_json(silent=True) or {}

    usn = data.get("usn", "")
    email = data.get("email", "")
    otp = data.get("otp", "")
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")

    if not all(
        isinstance(value, str)
        for value in (usn, email, otp, password, confirm_password)
    ):
        return jsonify({
            "status": "error",
            "message": "Enter all required details."
        }), 400

    usn = usn.strip().upper()
    email = email.strip().lower()

    if not re.fullmatch(r"[0-9]UB[0-9]{2}[A-Z]{2}[0-9]{3}", usn):
        return jsonify({
            "status": "error",
            "message": "Enter a valid 10-character USN."
        }), 400

    if not valid_email_address(email):
        return jsonify({
            "status": "error",
            "message": "Enter a valid email address."
        }), 400

    if not re.fullmatch(r"[0-9]{6}", otp):
        return jsonify({
            "status": "error",
            "message": "Enter the six-digit verification code."
        }), 400

    if len(password) < 12 or len(password) > 128:
        return jsonify({
            "status": "error",
            "message": "Password must contain 12–128 characters."
        }), 400

    if password != confirm_password:
        return jsonify({
            "status": "error",
            "message": "The passwords do not match."
        }), 400

    secret_key = app.config.get("SECRET_KEY")

    if not secret_key:
        return jsonify({
            "status": "error",
            "message": "Email verification is not configured."
        }), 500

    otp_hash = hmac.new(
        secret_key.encode("utf-8"),
        otp.encode("utf-8"),
        hashlib.sha256
    ).digest()

    password_hash = generate_password_hash(password)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Verify the pre-registered student account.
                # Lock the account to prevent simultaneous activation.
                cur.execute("""
                    SELECT a.id
                    FROM accounts a
                    JOIN students s
                        ON s.account_id = a.id
                    LEFT JOIN account_credentials ac
                        ON ac.account_id = a.id
                    WHERE UPPER(s.usn) = %s
                      AND LOWER(a.email) = %s
                      AND a.role = 'STUDENT'
                      AND a.is_active = TRUE
                      AND ac.account_id IS NULL
                    FOR UPDATE OF a;
                """, (usn, email))

                account = cur.fetchone()

                if not account:
                    return jsonify({
                        "status": "error",
                        "message": (
                            "Invalid activation request or account "
                            "already activated. Check your details."
                        )
                    }), 400

                account_id = account[0]

                # Retrieve the latest valid OTP challenge.
                cur.execute("""
                    SELECT id, otp_hash, attempts
                    FROM email_otp_challenges
                    WHERE account_id = %s
                      AND LOWER(target_email) = %s
                      AND consumed_at IS NULL
                      AND expires_at > CURRENT_TIMESTAMP
                      AND attempts < 10
                    ORDER BY created_at DESC
                    LIMIT 1
                    FOR UPDATE;
                """, (account_id, email))

                challenge = cur.fetchone()

                if not challenge:
                    return jsonify({
                        "status": "error",
                        "message": (
                            "Verification code is invalid or expired. "
                            "Request a new code."
                        )
                    }), 400

                challenge_id = challenge[0]
                stored_hash = bytes(challenge[1])

                # Verify the OTP without exposing the stored hash.
                if not hmac.compare_digest(stored_hash, otp_hash):

                    cur.execute("""
                        UPDATE email_otp_challenges
                        SET attempts = attempts + 1,
                            consumed_at = CASE
                                WHEN attempts + 1 >= 10
                                THEN CURRENT_TIMESTAMP
                                ELSE consumed_at
                            END
                        WHERE id = %s
                        RETURNING attempts;
                    """, (challenge_id,))

                    attempts = cur.fetchone()[0]

                    if attempts >= 10:
                        message = (
                            "Too many incorrect attempts. "
                            "Request a new verification code."
                        )
                    else:
                        message = "The verification code is incorrect."

                    return jsonify({
                        "status": "error",
                        "message": message
                    }), 400

                # Consume the successfully verified OTP.
                cur.execute("""
                    UPDATE email_otp_challenges
                    SET consumed_at = CURRENT_TIMESTAMP
                    WHERE id = %s;
                """, (challenge_id,))

                # Save the student's password hash.
                cur.execute("""
                    INSERT INTO account_credentials (
                        account_id,
                        password_hash,
                        password_changed_at
                    )
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (account_id) DO NOTHING
                    RETURNING account_id;
                """, (account_id, password_hash))

                if not cur.fetchone():
                    return jsonify({
                        "status": "error",
                        "message": "This student account is already activated."
                    }), 409

                cur.execute("""
                    UPDATE student_activation_email_jobs
                    SET status = 'CANCELLED', locked_at = NULL,
                        next_attempt_at = NULL,
                        last_error = 'Invitation no longer needed; account activated.',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE account_id = %s
                      AND status IN ('PENDING', 'PROCESSING');
                """, (account_id,))
                write_audit_event(cur, "STUDENT_ACCOUNT_ACTIVATED", {
                    "account_id": account_id,
                    "activation_method": "EMAIL_OTP",
                })

        return jsonify({
            "status": "ok",
            "message": (
                "Student account activated successfully. "
                "You can now log in."
            )
        }), 200

    except Exception:
        app.logger.exception(
            "Student account activation failed."
        )

        return jsonify({
            "status": "error",
            "message": (
                "Student account activation is temporarily unavailable."
            )
        }), 503            

# ==========================================
# STUDENT ACCOUNT ACTIVATION EMAIL
# ==========================================

def create_student_activation_token(cur, account_id):
    """Create a one-time, 24-hour student activation token.

    Existing usable tokens remain valid until SMTP accepts a replacement
    invitation. This prevents a transient delivery failure from invalidating
    the only link a student can currently use.
    """

    token = secrets.token_urlsafe(32)

    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).digest()

    cur.execute("""
        INSERT INTO student_activation_tokens (
            account_id,
            token_hash,
            expires_at
        )
        VALUES (
            %s,
            %s,
            CURRENT_TIMESTAMP + INTERVAL '24 hours'
        );
    """, (account_id, token_hash))

    return token


def student_activation_link(token):
    """Build the configured public student-activation link safely."""
    if not isinstance(token, str) or not token:
        raise ValueError("Activation token is invalid.")

    # Preserve the original local frontend route for installations that have
    # not yet supplied a deployment-specific public URL. Any configured value
    # remains strictly validated below, so a typo cannot send a broken link.
    configured_url = os.getenv(
        "STUDENT_ACTIVATION_URL",
        "http://localhost:5173/student-activate",
    ).strip()
    parsed = urlsplit(configured_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.fragment
        or parsed.path.rstrip("/") != "/student-activate"
    ):
        raise RuntimeError(
            "STUDENT_ACTIVATION_URL must be an absolute frontend /student-activate URL."
        )

    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != "token"
    ]
    query.append(("token", token))
    return urlunsplit((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        urlencode(query),
        "",
    ))


def send_student_activation_email(email, student_name, usn, token):
    """Send a professional student account activation invitation."""

    if not valid_email_address(email):
        raise ValueError("Student activation recipient is invalid.")

    activation_link = student_activation_link(token)

    safe_name = escape(student_name)
    safe_usn = escape(usn)
    safe_link = escape(activation_link, quote=True)

    message = EmailMessage()

    message["Subject"] = (
        "Activate Your Student Account | UBDTCE Secure E-Voting"
    )
    set_message_identity_headers(message)
    message["To"] = email

    message.set_content(
        "UBDTCE SECURE E-VOTING SYSTEM\n\n"
        f"Dear {student_name},\n\n"
        "Your student account has been registered by your department.\n\n"
        f"USN: {usn}\n\n"
        "Activate your account and create your password using this link:\n"
        f"{activation_link}\n\n"
        "This one-time activation link expires in 24 hours.\n"
        "Never share this link with anyone.\n\n"
        "If you did not expect this invitation, contact your department.\n\n"
        "Regards,\n"
        "UBDTCE Secure E-Voting Team"
    )

    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Activate Student Account</title>
</head>
<body style="margin:0;padding:28px 12px;background:#f1f4f8;
             font-family:Arial,Helvetica,sans-serif;color:#263449;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0"
               cellpadding="0"
               style="max-width:560px;background:#ffffff;
                      border-radius:12px;overflow:hidden;">

          <tr>
            <td align="center"
                style="background:#142d4e;padding:30px 20px;">
              <h1 style="margin:0;color:#ffffff;font-size:25px;">
                UBDTCE
              </h1>
              <p style="margin:8px 0 0;color:#e4cc91;
                        font-size:12px;letter-spacing:2px;">
                SECURE E-VOTING SYSTEM
              </p>
            </td>
          </tr>

          <tr>
            <td style="padding:32px 26px;">
              <p style="color:#9a722b;font-size:11px;
                        font-weight:bold;letter-spacing:1.5px;">
                STUDENT ACCOUNT INVITATION
              </p>

              <h2 style="color:#142d4e;font-size:25px;">
                Welcome to UBDTCE!
              </h2>

              <p style="font-size:15px;line-height:1.8;color:#475569;">
                Dear <strong>{safe_name}</strong>,
              </p>

              <p style="font-size:15px;line-height:1.8;color:#475569;">
                Your student account has been registered by your
                department. Complete the activation process to access
                the UBDTCE Secure E-Voting System.
              </p>

              <div style="background:#f4f7fb;border:1px solid #e2e8f0;
                          border-radius:9px;padding:18px;margin:22px 0;">
                <p style="margin:0 0 8px;color:#64748b;font-size:12px;">
                  YOUR UNIVERSITY SEAT NUMBER
                </p>
                <strong style="font-size:19px;color:#142d4e;">
                  {safe_usn}
                </strong>
              </div>

              <p style="text-align:center;margin:28px 0;">
                <a href="{safe_link}"
                   style="display:inline-block;padding:14px 26px;
                          background:#142d4e;color:#ffffff;
                          text-decoration:none;border-radius:7px;
                          font-weight:bold;font-size:14px;">
                  Set Your Password
                </a>
              </p>

              <p style="font-size:13px;line-height:1.8;color:#64748b;">
                This secure, one-time activation link expires after
                24 hours. Do not share it with anyone.
              </p>

              <p style="font-size:13px;line-height:1.8;color:#64748b;">
                If the button does not work, copy this link into your
                browser:<br>
                <a href="{safe_link}" style="color:#315d91;">
                  {safe_link}
                </a>
              </p>

              <p style="margin-top:26px;color:#475569;font-size:14px;">
                Regards,<br>
                <strong style="color:#142d4e;">
                  UBDTCE Secure E-Voting Team
                </strong>
              </p>
            </td>
          </tr>

          <tr>
            <td align="center"
                style="background:#f8fafc;border-top:1px solid #e2e8f0;
                       padding:19px;">
              <p style="margin:0;color:#64748b;font-size:11px;
                        line-height:1.7;">
                Automated account notification. Please do not reply.<br>
                UBDTCE Secure E-Voting System
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    message.add_alternative(html_body, subtype="html")

    deliver_email(message)


def queue_student_activation_email(cur, account_id, *, reset_attempts=False):
    """Queue one fresh activation invitation without persisting its raw token.

    A human-authorized retry resets the retry budget for the single existing
    outbox row. Normal registration keeps the budget intact, so repeated
    programmatic queueing cannot create unbounded delivery attempts.
    """
    cur.execute("""
        INSERT INTO student_activation_email_jobs (account_id, status)
        VALUES (%s, 'PENDING')
        ON CONFLICT (account_id) DO UPDATE
        SET status = 'PENDING',
            attempts = CASE WHEN %s THEN 0 ELSE student_activation_email_jobs.attempts END,
            locked_at = NULL,
            last_error = NULL,
            failure_kind = NULL,
            next_attempt_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id;
    """, (account_id, reset_attempts))
    return cur.fetchone()[0]


def process_pending_activation_emails(limit=25):
    """Deliver queued invitations safely in bounded batches.

    The worker creates an opaque token only after it claims a job. The raw
    secret consequently exists only in process memory while one email is
    composed; PostgreSQL retains just its SHA-256 hash. `SKIP LOCKED` permits
    more than one worker without sending a job twice.
    """
    if not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")

    summary = {"attempted": 0, "sent": 0, "failed": 0, "skipped": 0}
    # A worker can be terminated after claiming a job. Expired leases below
    # the retry ceiling are reclaimed below; exhausted leases are stopped here
    # rather than silently producing an unbounded series of replacement links.
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE student_activation_email_jobs
                    SET status = 'FAILED', locked_at = NULL,
                        next_attempt_at = NULL,
                        failure_kind = 'TEMPORARY_EXHAUSTED',
                        last_error = 'Delivery attempts exhausted; manual retry is required.',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE attempts >= %s
                      AND (
                          status = 'PENDING'
                          OR (
                              status = 'PROCESSING'
                              AND locked_at < CURRENT_TIMESTAMP
                                  - (%s * INTERVAL '1 minute')
                          )
                      );
                """, (ACTIVATION_EMAIL_MAX_ATTEMPTS, ACTIVATION_EMAIL_JOB_LEASE_MINUTES))
                summary["skipped"] = cur.rowcount
    except Exception:
        app.logger.exception("Could not recover exhausted activation email jobs")
        return summary

    for _ in range(limit):
        claimed = None
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT j.id, a.id, a.email, a.full_name, s.id, s.usn, j.attempts
                        FROM student_activation_email_jobs j
                        JOIN accounts a ON a.id = j.account_id
                        JOIN students s ON s.account_id = a.id
                        LEFT JOIN account_credentials c ON c.account_id = a.id
                        WHERE (
                            (j.status = 'PENDING'
                             AND (j.next_attempt_at IS NULL OR j.next_attempt_at <= CURRENT_TIMESTAMP))
                            OR (
                                j.status = 'PROCESSING'
                                AND j.locked_at < CURRENT_TIMESTAMP
                                    - (%s * INTERVAL '1 minute')
                            )
                        )
                          AND a.role = 'STUDENT'
                          AND a.is_active = TRUE
                          AND c.account_id IS NULL
                          AND j.attempts < %s
                        ORDER BY j.created_at, j.id
                        FOR UPDATE OF j SKIP LOCKED
                        LIMIT 1;
                    """, (
                        ACTIVATION_EMAIL_JOB_LEASE_MINUTES,
                        ACTIVATION_EMAIL_MAX_ATTEMPTS,
                    ))
                    job = cur.fetchone()
                    if not job:
                        break

                    job_id, account_id, email, full_name, student_id, usn, prior_attempts = job
                    token = create_student_activation_token(cur, account_id)
                    cur.execute("""
                        UPDATE student_activation_email_jobs
                        SET status = 'PROCESSING',
                            attempts = attempts + 1,
                            locked_at = CURRENT_TIMESTAMP,
                            last_attempt_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s;
                    """, (job_id,))
                    claimed = {
                        "job_id": job_id,
                        "account_id": account_id,
                        "student_id": student_id,
                        "email": email,
                        "full_name": full_name,
                        "usn": usn,
                        "token": token,
                        "attempts": prior_attempts + 1,
                    }
        except Exception:
            app.logger.exception("Could not claim a student activation email job")
            summary["failed"] += 1
            continue

        summary["attempted"] += 1
        delivered = False
        try:
            send_student_activation_email(
                claimed["email"],
                claimed["full_name"],
                claimed["usn"],
                claimed["token"],
            )
            delivered = True
        except Exception as exc:
            # Do not log email addresses, tokens, SMTP responses, or other
            # delivery details that could reveal sensitive configuration.
            app.logger.exception("Student activation email delivery failed")
            retryable_failure = is_retryable_email_failure(exc)

        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    if delivered:
                        cur.execute("""
                            UPDATE student_activation_email_jobs
                            SET status = 'SENT', sent_at = CURRENT_TIMESTAMP,
                                locked_at = NULL, last_error = NULL,
                                failure_kind = NULL, next_attempt_at = NULL,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s;
                        """, (claimed["job_id"],))
                        write_audit_event(cur, "STUDENT_ACTIVATION_EMAIL_SENT", {
                            "account_id": claimed["account_id"],
                            "student_id": claimed["student_id"],
                            "job_id": claimed["job_id"],
                        })
                    else:
                        token_hash = hashlib.sha256(
                            claimed["token"].encode("utf-8")
                        ).digest()
                        cur.execute("""
                            UPDATE student_activation_tokens
                            SET used_at = CURRENT_TIMESTAMP
                            WHERE token_hash = %s AND used_at IS NULL;
                        """, (token_hash,))
                        automatic_retry = (
                            retryable_failure
                            and claimed["attempts"] < ACTIVATION_EMAIL_MAX_ATTEMPTS
                        )
                        if automatic_retry:
                            retry_delay_minutes = min(2 ** claimed["attempts"], 60)
                            cur.execute("""
                                UPDATE student_activation_email_jobs
                                SET status = 'PENDING', locked_at = NULL,
                                    failure_kind = 'TEMPORARY',
                                    next_attempt_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 minute'),
                                    last_error = 'Temporary delivery failure; retry scheduled.',
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s;
                            """, (retry_delay_minutes, claimed["job_id"]))
                        else:
                            cur.execute("""
                                UPDATE student_activation_email_jobs
                                SET status = 'FAILED', locked_at = NULL,
                                    failure_kind = %s,
                                    next_attempt_at = NULL,
                                    last_error = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s;
                            """, (
                                "TEMPORARY_EXHAUSTED" if retryable_failure else "PERMANENT",
                                "Delivery attempts exhausted; manual retry is required."
                                if retryable_failure else "Permanent delivery failure; correct the recipient or provider configuration.",
                                claimed["job_id"],
                            ))
                        write_audit_event(cur, "STUDENT_ACTIVATION_EMAIL_RETRY_SCHEDULED" if automatic_retry else "STUDENT_ACTIVATION_EMAIL_FAILED", {
                            "account_id": claimed["account_id"],
                            "student_id": claimed["student_id"],
                            "job_id": claimed["job_id"],
                            "attempt": claimed["attempts"],
                        })
        except Exception:
            app.logger.exception("Could not persist student activation delivery status")
            summary["failed"] += 1
            continue

        summary["sent" if delivered else "failed"] += 1

    return summary

# ------------------------------------------
# 1. DATABASE HEALTH CHECK
# ------------------------------------------
@app.get("/api/health")
@limiter.limit("30 per minute")
def health():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_timestamp;")
                server_time = cur.fetchone()[0]

        return jsonify({
            "status": "ok",
            "database": "connected",
            "database_time": server_time.isoformat(),
        }), 200

    except Exception:
        app.logger.exception("Health check failed")
        return jsonify({
            "status": "error",
            "message": "Database health check failed",
        }), 503


@app.get("/api/ready")
@limiter.limit("30 per minute")
def readiness():
    """A load-balancer readiness probe that verifies the primary data store."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        return jsonify({"status": "ok", "ready": True}), 200
    except Exception:
        app.logger.exception("Readiness check failed")
        return jsonify({"status": "error", "ready": False}), 503


@app.get("/api/candidate-symbols")
@limiter.limit("60 per minute")
def list_candidate_symbols():
    """List the fixed election symbol library; no upload endpoint exists."""
    return jsonify({"status": "ok", "symbols": list(CANDIDATE_SYMBOLS)}), 200


# ------------------------------------------
# 2. ACTIVE BRANCHES
# ------------------------------------------
@app.get("/api/branches")
@limiter.limit("60 per minute")
def get_branches():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, code, name
                    FROM branches
                    WHERE is_active = TRUE
                    ORDER BY id;
                """)
                rows = cur.fetchall()

        branches = [
            {"id": row[0], "code": row[1], "name": row[2]}
            for row in rows
        ]

        return jsonify({
            "status": "ok",
            "count": len(branches),
            "branches": branches,
        }), 200

    except Exception:
        app.logger.exception("Branch retrieval failed")
        return jsonify({
            "status": "error",
            "message": "Could not retrieve branches",
        }), 503


# ------------------------------------------
# 3. COLLEGE AND DEPARTMENT STATISTICS
# ------------------------------------------
@app.get("/api/statistics")
@limiter.limit("30 per minute")
def get_statistics():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) AS total_students,
                        COUNT(*) FILTER (WHERE is_cr = TRUE),
                        COUNT(*) FILTER (WHERE is_fr = TRUE),
                        (
                            SELECT COUNT(*)
                            FROM elections
                            WHERE status = 'OPEN'
                              AND opens_at <= CURRENT_TIMESTAMP
                              AND closes_at > CURRENT_TIMESTAMP
                        )
                    FROM students;
                """)
                total_students, total_crs, total_frs, active_elections = cur.fetchone()

                cur.execute("""
                    SELECT b.id, b.code, b.name, COUNT(s.id)
                    FROM branches AS b
                    LEFT JOIN students AS s ON s.branch_id = b.id
                    WHERE b.is_active = TRUE
                    GROUP BY b.id, b.code, b.name
                    ORDER BY b.id;
                """)
                rows = cur.fetchall()

        departments = [
            {
                "id": row[0],
                "code": row[1],
                "name": row[2],
                "student_count": row[3],
            }
            for row in rows
        ]

        return jsonify({
            "status": "ok",
            "total_students": total_students,
            "total_crs": total_crs,
            "total_frs": total_frs,
            "active_elections": active_elections,
            "total_departments": len(departments),
            "departments": departments,
        }), 200

    except Exception:
        app.logger.exception("Statistics retrieval failed")
        return jsonify({
            "status": "error",
            "message": "Could not retrieve statistics",
        }), 503

# ------------------------------------------
# PRINCIPAL / HOD LOGIN
# Supports primary emails and verified additional
# Principal emails with separate password hashes.
# ------------------------------------------
@app.post("/api/auth/login")
@limiter.limit("5 per minute")
@limiter.limit("10 per 15 minutes", key_func=login_email_rate_limit_key)

def login():
    data = request.get_json(silent=True) or {}

    email = data.get("email", "")
    usn = data.get("usn", "")
    password = data.get("password", "")

    if not all(
        isinstance(value, str)
        for value in (email, usn, password)
    ):
        return jsonify({
            "status": "error",
            "message": "Enter your login details."
        }), 400

    email = email.strip().lower()
    usn = usn.strip().upper()

    if bool(email) == bool(usn):
        return jsonify({
            "status": "error",
            "message": "Enter your registered email or student USN."
        }), 400

    if not password:
        return jsonify({
            "status": "error",
            "message": "Enter your password."
        }), 400

    if usn and not re.fullmatch(
        r"[0-9]UB[0-9]{2}[A-Z]{2}[0-9]{3}", usn
    ):
        return jsonify({
            "status": "error",
            "message": "Enter a valid 10-character USN."
        }), 400

    if email and not valid_email_address(email):
        return jsonify({
            "status": "error",
            "message": "Enter a valid email address."
        }), 400

    if not app.config["SECRET_KEY"]:
        return jsonify({
            "status": "error",
            "message": "Login is not configured correctly."
        }), 500

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                if usn:
                    # Student login using USN.
                    cur.execute("""
                        SELECT
                            a.id,
                            a.email,
                            a.role,
                            c.password_hash,
                            a.full_name
                        FROM students s
                        JOIN accounts a
                            ON a.id = s.account_id
                        JOIN account_credentials c
                            ON c.account_id = a.id
                        WHERE UPPER(s.usn) = %s
                          AND a.role = 'STUDENT'
                          AND a.is_active = TRUE
                        LIMIT 1;
                    """, (usn,))

                else:
                    # Principal and HOD login using email.
                    cur.execute("""
                        SELECT
                            a.id,
                            a.email,
                            a.role,
                            c.password_hash,
                            a.full_name
                        FROM accounts a
                        JOIN account_credentials c
                            ON c.account_id = a.id
                        WHERE LOWER(a.email) = %s
                          AND a.is_active = TRUE
                          AND a.role IN ('PRINCIPAL', 'HOD')
                          AND (
                              a.role = 'PRINCIPAL'
                              OR EXISTS (
                                  SELECT 1
                                  FROM hod_assignments ha
                                  JOIN branches hb
                                      ON hb.id = ha.branch_id
                                  WHERE ha.account_id = a.id
                                    AND hb.is_active = TRUE
                              )
                          )

                        UNION ALL

                        SELECT
                            a.id,
                            a.email,
                            a.role,
                            e.password_hash,
                            a.full_name
                        FROM account_email_addresses e
                        JOIN accounts a
                            ON a.id = e.account_id
                        WHERE LOWER(e.email) = %s
                          AND e.is_verified = TRUE
                          AND e.password_hash IS NOT NULL
                          AND a.is_active = TRUE
                          AND a.role = 'PRINCIPAL'

                        LIMIT 1;
                    """, (email, email))

                account = cur.fetchone()

        if (
            not account
            or not account[3]
            or not check_password_hash(account[3], password)
        ):
            return jsonify({
                "status": "error",
                "message": "Invalid login details."
            }), 401

        # Administrative authentication events are auditable. Passwords and
        # session values are intentionally never included in the event data.
        try:
            with get_db_connection() as audit_conn:
                with audit_conn.cursor() as audit_cur:
                    write_audit_event(audit_cur, "ACCOUNT_LOGIN", {
                        "account_id": account[0], "role": account[2]
                    })
        except Exception:
            app.logger.exception("Authentication audit event could not be recorded")

        session.clear()
        session.permanent = True
        session["account_id"] = account[0]
        session["email"] = email if email else account[1]
        session["role"] = account[2]

        return jsonify({
            "status": "ok",
            "message": "Login successful.",
            "user": {
                "email": account[1],
                "role": account[2],
                "full_name": account[4] or ""
            }
        }), 200

    except Exception:
        app.logger.exception("Login failed")

        return jsonify({
            "status": "error",
            "message": "Login service is temporarily unavailable."
        }), 503


# ------------------------------------------
# AUTHENTICATION: LOG OUT
# ------------------------------------------
@app.post("/api/auth/logout")
@limiter.limit("20 per minute")
def logout():
    account_id = session.get("account_id")
    role = session.get("role")
    session.clear()
    if account_id and role:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    write_audit_event(cur, "ACCOUNT_LOGOUT", {
                        "account_id": account_id, "role": role
                    })
        except Exception:
            # Logout must remain effective even if the audit database is down.
            app.logger.exception("Logout audit event could not be recorded")
    response = jsonify({"status": "ok", "message": "Logged out successfully."})
    response.delete_cookie(
        app.config.get("SESSION_COOKIE_NAME", "session"),
        path=app.config.get("SESSION_COOKIE_PATH", "/"),
        domain=app.config.get("SESSION_COOKIE_DOMAIN"),
        secure=app.config.get("SESSION_COOKIE_SECURE", False),
        httponly=app.config.get("SESSION_COOKIE_HTTPONLY", True),
        samesite=app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
    )
    return response, 200


# ------------------------------------------
# PRINCIPAL DASHBOARD SUMMARY
# ------------------------------------------
@app.get("/api/principal/dashboard")
@limiter.limit("30 per minute")
def principal_dashboard():
    auth_error = require_principal()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        (SELECT COUNT(*)
                         FROM branches
                         WHERE is_active = TRUE),
                        (SELECT COUNT(*)
                         FROM students),
                        (SELECT COUNT(*)
                         FROM hod_assignments h
                         JOIN accounts a ON a.id = h.account_id
                         JOIN branches b ON b.id = h.branch_id
                         WHERE a.role = 'HOD'
                           AND a.is_active = TRUE
                           AND b.is_active = TRUE),
                        (SELECT COUNT(*)
                         FROM elections),
                        (SELECT COUNT(*)
                         FROM elections
                         WHERE status = 'OPEN'
                           AND opens_at <= CURRENT_TIMESTAMP
                           AND closes_at > CURRENT_TIMESTAMP),
                        (SELECT COUNT(*)
                         FROM elections
                         WHERE status = 'CLOSED')
                """)
                row = cur.fetchone()

                cur.execute("""
                    SELECT
                        b.id,
                        b.code,
                        b.name,
                        b.is_active,
                        COUNT(DISTINCT s.id) AS student_count,
                        COUNT(DISTINCT h.account_id) AS hod_count
                    FROM branches AS b
                    LEFT JOIN students AS s
                        ON s.branch_id = b.id
                    LEFT JOIN hod_assignments AS h
                        ON h.branch_id = b.id
                    GROUP BY b.id, b.code, b.name, b.is_active
                    ORDER BY b.name
                """)
                branch_rows = cur.fetchall()

        return jsonify({
            "status": "ok",
            "summary": {
                "active_branches": row[0],
                "total_students": row[1],
                "active_hods": row[2],
                "total_elections": row[3],
                "open_elections": row[4],
                "completed_elections": row[5],
            },
            "branches": [
                {
                    "id": b[0],
                    "code": b[1],
                    "name": b[2],
                    "is_active": b[3],
                    "student_count": b[4],
                    "hod_count": b[5],
                }
                for b in branch_rows
            ],
        }), 200

    except Exception:
        app.logger.exception("Principal dashboard retrieval failed")
        return jsonify({
            "status": "error",
            "message": "Could not load Principal dashboard."
        }), 503


@app.get("/api/principal/audit-integrity")
@limiter.limit("10 per minute")
def principal_audit_integrity():
    """Verify hash-chain continuity without disclosing audit event contents."""
    auth_error = require_principal()
    if auth_error:
        return auth_error
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                result = verify_audit_chain(cur)
        return jsonify({"status": "ok", "audit_chain": result}), 200
    except Exception:
        app.logger.exception("Audit integrity verification failed")
        return jsonify({
            "status": "error",
            "message": "Audit integrity verification is temporarily unavailable.",
        }), 503

# ------------------------------------------
# PRINCIPAL EMAIL MANAGEMENT: LIST EMAILS
# ------------------------------------------
@app.get("/api/principal/settings/emails")
@limiter.limit("30 per minute")
def list_principal_emails():
    auth_error = require_principal()
    if auth_error:
        return auth_error

    account_id = session["account_id"]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT email
                    FROM accounts
                    WHERE id = %s
                      AND role = 'PRINCIPAL'
                      AND is_active = TRUE;
                """, (account_id,))

                primary = cur.fetchone()

                if not primary:
                    return jsonify({
                        "status": "error",
                        "message": "Principal account not found."
                    }), 404

                cur.execute("""
                    SELECT id, email, verified_at
                    FROM account_email_addresses
                    WHERE account_id = %s
                      AND is_verified = TRUE
                    ORDER BY created_at;
                """, (account_id,))

                additional = cur.fetchall()

        return jsonify({
            "status": "ok",
            "primary_email": primary[0],
            "additional_emails": [
                {
                    "id": row[0],
                    "email": row[1],
                    "verified_at": (
                        row[2].isoformat() if row[2] else None
                    )
                }
                for row in additional
            ]
        }), 200

    except Exception:
        app.logger.exception("Principal email list retrieval failed")
        return jsonify({
            "status": "error",
            "message": "Could not retrieve email addresses."
        }), 503

        # ------------------------------------------
# PRINCIPAL EMAIL MANAGEMENT: DELETE EXTRA EMAIL
# ------------------------------------------
@app.delete("/api/principal/settings/emails/<int:email_id>")
@limiter.limit("10 per minute")
def delete_principal_email(email_id):
    auth_error = require_principal()
    if auth_error:
        return auth_error

    account_id = session["account_id"]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM account_email_addresses
                    WHERE id = %s
                      AND account_id = %s
                      AND is_verified = TRUE
                    RETURNING email;
                """, (email_id, account_id))

                removed = cur.fetchone()

                if not removed:
                    return jsonify({
                        "status": "error",
                        "message": (
                            "Verified additional email not found."
                        )
                    }), 404

        return jsonify({
            "status": "ok",
            "message": "Additional email removed successfully."
        }), 200

    except Exception:
        app.logger.exception("Additional email removal failed")
        return jsonify({
            "status": "error",
            "message": "Could not remove the additional email."
        }), 503


    # ------------------------------------------
# DELETE PRIMARY EMAIL SAFELY
# Promote the verified additional email first.
# ------------------------------------------
@app.delete("/api/principal/settings/emails/primary")
@limiter.limit("10 per minute")
def delete_principal_primary_email():
    auth_error = require_principal()
    if auth_error:
        return auth_error

    account_id = session["account_id"]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        a.email,
                        e.id,
                        e.email,
                        e.password_hash
                    FROM accounts AS a
                    JOIN account_email_addresses AS e
                      ON e.account_id = a.id
                     AND e.is_verified = TRUE
                    WHERE a.id = %s
                      AND a.role = 'PRINCIPAL'
                      AND a.is_active = TRUE
                    FOR UPDATE OF a, e;
                """, (account_id,))

                row = cur.fetchone()

                if not row:
                    return jsonify({
                        "status": "error",
                        "message": (
                            "You cannot delete the only remaining email."
                        )
                    }), 409

                old_email, extra_id, extra_email, extra_hash = row

                if not extra_hash:
                    return jsonify({
                        "status": "error",
                        "message": (
                            "The additional email has no password. "
                            "Set its password before deleting the primary email."
                        )
                    }), 409

                # Transfer the additional email's separate password
                # to the account's primary credential record.
                cur.execute("""
                    UPDATE account_credentials
                    SET password_hash = %s,
                        password_changed_at = CURRENT_TIMESTAMP
                    WHERE account_id = %s
                    RETURNING account_id;
                """, (extra_hash, account_id))

                if cur.fetchone() is None:
                    raise RuntimeError(
                        "Principal credential record was not found."
                    )

                # Remove its former secondary slot, then promote it.
                # Both operations are inside this transaction: a failure rolls
                # the deletion back and leaves the original primary email intact.
                cur.execute("""
                    DELETE FROM account_email_addresses
                    WHERE id = %s
                      AND account_id = %s;
                """, (extra_id, account_id))

                cur.execute("""
                    UPDATE accounts
                    SET email = %s
                    WHERE id = %s
                      AND role = 'PRINCIPAL';
                """, (extra_email, account_id))

        session["email"] = extra_email

        return jsonify({
            "status": "ok",
            "message": (
                "The old primary email was removed. "
                "The remaining email and its password are now the primary login."
            )
        }), 200

    except Exception:
        app.logger.exception("Primary email removal failed")
        return jsonify({
            "status": "error",
            "message": "Could not remove the primary email."
        }), 503
    
# ------------------------------------------
# PRINCIPAL BRANCH MANAGEMENT
# ------------------------------------------

# ------------------------------------------
# PRINCIPAL EMAIL MANAGEMENT: SEND OTP
# ------------------------------------------
@app.post("/api/principal/settings/email/send-otp")
@limiter.limit("10 per hour")
def send_principal_email_otp():
    auth_error = require_principal()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    email = data.get("email", "")

    if not isinstance(email, str):
        return jsonify({
            "status": "error",
            "message": "Enter a valid email address."
        }), 400

    email = email.strip().lower()

    if not valid_email_address(email):
        return jsonify({
            "status": "error",
            "message": "Enter a valid email address."
        }), 400

    secret_key = app.config["SECRET_KEY"]
    if not secret_key:
        return jsonify({
            "status": "error",
            "message": "Email verification is not configured."
        }), 500

    account_id = session["account_id"]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Do not allow the primary email to be added again.
                cur.execute("""
                    SELECT email
                    FROM accounts
                    WHERE id = %s AND is_active = TRUE
                    FOR UPDATE;
                """, (account_id,))

                account = cur.fetchone()

                if not account:
                    return jsonify({
                        "status": "error",
                        "message": "Please log in again."
                    }), 401

                if email == account[0].lower():
                    return jsonify({
                        "status": "error",
                        "message": "This is already your primary email."
                    }), 409

                # Do not allow an email already registered to an account.
                cur.execute("""
                    SELECT
                        EXISTS (
                            SELECT 1 FROM accounts
                            WHERE LOWER(email) = %s
                        )
                        OR
                        EXISTS (
                            SELECT 1 FROM account_email_addresses
                            WHERE LOWER(email) = %s
                        );
                """, (email, email))

                if cur.fetchone()[0]:
                    return jsonify({
                        "status": "error",
                        "message": "This email address is already registered."
                    }), 409

                # Enforce a two-minute resend delay for this account
                # and destination email.
                cur.execute("""
                    SELECT
                        CEIL(EXTRACT(EPOCH FROM (
                            created_at
                            + INTERVAL '2 minutes'
                            - CURRENT_TIMESTAMP
                        )))::INTEGER
                    FROM email_otp_challenges
                    WHERE account_id = %s
                      AND LOWER(target_email) = %s
                    ORDER BY created_at DESC
                    LIMIT 1;
                """, (account_id, email))

                recent = cur.fetchone()

                if recent and recent[0] > 0:
                    return jsonify({
                        "status": "error",
                        "message": (
                            "Please wait before requesting another code."
                        ),
                        "retry_after_seconds": recent[0]
                    }), 429

                # Invalidate earlier unused codes for this address.
                cur.execute("""
                    UPDATE email_otp_challenges
                    SET consumed_at = CURRENT_TIMESTAMP
                    WHERE account_id = %s
                      AND LOWER(target_email) = %s
                      AND consumed_at IS NULL;
                """, (account_id, email))

                otp = f"{secrets.randbelow(1_000_000):06d}"

                otp_hash = hmac.new(
                    secret_key.encode("utf-8"),
                    otp.encode("utf-8"),
                    hashlib.sha256
                ).digest()

                cur.execute("""
                    INSERT INTO email_otp_challenges (
                        account_id,
                        target_email,
                        otp_hash,
                        expires_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        CURRENT_TIMESTAMP + INTERVAL '3 minutes'
                    )
                    RETURNING id;
                """, (account_id, email, otp_hash))

                challenge_id = cur.fetchone()[0]

                

        # Send the message after the database transaction commits.
        try:
            send_email_verification_otp(email, otp)
        except Exception:
            app.logger.exception("Email verification message could not be sent")

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE email_otp_challenges
                        SET consumed_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                          AND consumed_at IS NULL;
                    """, (challenge_id,))

            return jsonify({
                "status": "error",
                "message": (
                    "The verification email could not be sent. "
                    "Check the email service configuration."
                )
            }), 503

        return jsonify({
            "status": "ok",
            "message": "Verification code sent to the requested email.",
            "expires_in_seconds": 180,
            "resend_after_seconds": 120
        }), 200

    except Exception:
        app.logger.exception("Email verification request failed")
        return jsonify({
            "status": "error",
            "message": "Email verification is temporarily unavailable."
        }), 503
# ------------------------------------------
# PRINCIPAL EMAIL MANAGEMENT: VERIFY OTP
# ------------------------------------------
@app.post("/api/principal/settings/email/verify-otp")
@limiter.limit("10 per minute")
def verify_principal_email_otp():
    auth_error = require_principal()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}

    email = data.get("email", "")
    otp = data.get("otp", "")
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")

    if not all(
    isinstance(value, str)
    for value in (email, otp, password, confirm_password)
):
        return jsonify({
            "status": "error",
            "message": "Enter the email address and verification code."
        }), 400

    email = email.strip().lower()

    if not valid_email_address(email) or len(otp) != 6 or not otp.isdigit():
        return jsonify({
            "status": "error",
            "message": "Enter a valid email address and six-digit code."
        }), 400

    if len(password) < 12:
       return jsonify({
        "status": "error",
        "message": "The password must contain at least 12 characters."
    }), 400

    if password != confirm_password:
       return jsonify({
        "status": "error",
        "message": "The passwords do not match."
    }), 400

    secret_key = app.config["SECRET_KEY"]
    if not secret_key:
        return jsonify({
            "status": "error",
            "message": "Email verification is not configured."
        }), 500

    account_id = session["account_id"]

    otp_hash = hmac.new(
        secret_key.encode("utf-8"),
        otp.encode("utf-8"),
        hashlib.sha256
    ).digest()
    password_hash = generate_password_hash(password)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Confirm the account is still active.
                cur.execute("""
                    SELECT email
                    FROM accounts
                    WHERE id = %s
                      AND role = 'PRINCIPAL'
                      AND is_active = TRUE
                    FOR UPDATE;
                """, (account_id,))

                account = cur.fetchone()

                if not account:
                    return jsonify({
                        "status": "error",
                        "message": "Please log in again."
                    }), 401

                if email == account[0].strip().lower():
                    return jsonify({
                        "status": "error",
                        "message": "This is already your primary email."
                    }), 409

                # The account supports one additional email address.
                cur.execute("""
                    SELECT id
                    FROM account_email_addresses
                    WHERE account_id = %s;
                """, (account_id,))

                if cur.fetchone():
                    return jsonify({
                        "status": "error",
                        "message": (
                            "An additional email is already saved. "
                            "Remove it before adding another."
                        )
                    }), 409

                # Find the latest unused, unexpired OTP.
                cur.execute("""
                    SELECT id, otp_hash, attempts
                    FROM email_otp_challenges
                    WHERE account_id = %s
                      AND LOWER(target_email) = %s
                      AND consumed_at IS NULL
                      AND expires_at > CURRENT_TIMESTAMP
                      AND attempts < 10
                    ORDER BY created_at DESC
                    LIMIT 1
                    FOR UPDATE;
                """, (account_id, email))

                challenge = cur.fetchone()

                if not challenge:
                    return jsonify({
                        "status": "error",
                        "message": (
                            "The code is invalid or expired. "
                            "Request a new code."
                        )
                    }), 400

                challenge_id = challenge[0]
                stored_hash = bytes(challenge[1])

                if not hmac.compare_digest(stored_hash, otp_hash):
                    cur.execute("""
                        UPDATE email_otp_challenges
                        SET attempts = attempts + 1,
                            consumed_at = CASE
                                WHEN attempts + 1 >= 10
                                THEN CURRENT_TIMESTAMP
                                ELSE consumed_at
                            END
                        WHERE id = %s
                        RETURNING attempts;
                    """, (challenge_id,))

                    attempts = cur.fetchone()[0]

                    if attempts >= 10:
                        message = (
                            "Too many incorrect attempts. "
                            "Request a new verification code."
                        )
                    else:
                        message = "The verification code is incorrect."

                    return jsonify({
                        "status": "error",
                        "message": message
                    }), 400

                # Save the verified address and consume the OTP.
                cur.execute("""
                    UPDATE email_otp_challenges
                    SET consumed_at = CURRENT_TIMESTAMP
                    WHERE id = %s;
                """, (challenge_id,))

                cur.execute("""
    INSERT INTO account_email_addresses (
        account_id,
        email,
        is_verified,
        verified_at,
        password_hash
    )
    VALUES (%s, %s, TRUE, CURRENT_TIMESTAMP, %s)
    RETURNING id, email, is_verified, verified_at;
""", (account_id, email, password_hash))

                saved_email = cur.fetchone()

        return jsonify({
            "status": "ok",
            "message": "Email address verified successfully.",
            "email": {
                "id": saved_email[0],
                "email": saved_email[1],
                "is_verified": saved_email[2],
                "verified_at": saved_email[3].isoformat()
            }
        }), 200

    except Exception as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            return jsonify({
                "status": "error",
                "message": (
                    "This email is already registered, or an "
                    "additional email is already saved."
                )
            }), 409

        app.logger.exception("Principal email verification failed")

        return jsonify({
            "status": "error",
            "message": "Email verification is temporarily unavailable."
        }), 503
    # ------------------------------------------
# PRINCIPAL PASSWORD MANAGEMENT
# Change the password for one selected email.
# ------------------------------------------
@app.post("/api/principal/settings/password")
@limiter.limit("5 per minute")
def change_principal_email_password():
    auth_error = require_principal()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}

    email = data.get("email", "")
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    confirm_password = data.get("confirm_password", "")

    if not all(isinstance(value, str) for value in (
        email, current_password, new_password, confirm_password
    )):
        return jsonify({
            "status": "error",
            "message": "Please complete all password fields."
        }), 400

    email = email.strip().lower()

    if not valid_email_address(email) or not current_password:
        return jsonify({
            "status": "error",
            "message": "Email and current password are required."
        }), 400

    if len(new_password) < 12:
        return jsonify({
            "status": "error",
            "message": "Use a password with at least 12 characters."
        }), 400

    if new_password != confirm_password:
        return jsonify({
            "status": "error",
            "message": "The new passwords do not match."
        }), 400

    account_id = session["account_id"]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Load and lock the Principal's account credentials.
                cur.execute("""
                    SELECT a.email, c.password_hash
                    FROM accounts AS a
                    JOIN account_credentials AS c
                      ON c.account_id = a.id
                    WHERE a.id = %s
                      AND a.role = 'PRINCIPAL'
                      AND a.is_active = TRUE
                    FOR UPDATE OF a, c;
                """, (account_id,))

                account = cur.fetchone()

                if not account:
                    return jsonify({
                        "status": "error",
                        "message": "Principal account not found. Log in again."
                    }), 401

                primary_email, primary_hash = account

                if email == primary_email.strip().lower():
                    # The selected email is the primary address.
                    if not check_password_hash(
                        primary_hash, current_password
                    ):
                        return jsonify({
                            "status": "error",
                            "message": "The current password is incorrect."
                        }), 401

                    # Keep the two email passwords different.
                    cur.execute("""
                        SELECT password_hash
                        FROM account_email_addresses
                        WHERE account_id = %s
                          AND is_verified = TRUE;
                    """, (account_id,))

                    additional = cur.fetchone()

                    if (
                        additional
                        and additional[0]
                        and check_password_hash(
                            additional[0], new_password
                        )
                    ):
                        return jsonify({
                            "status": "error",
                            "message": (
                                "Use a different password from the "
                                "additional email's password."
                            )
                        }), 400

                    new_hash = generate_password_hash(new_password)

                    cur.execute("""
                        UPDATE account_credentials
                        SET password_hash = %s,
                            password_changed_at = CURRENT_TIMESTAMP
                        WHERE account_id = %s;
                    """, (new_hash, account_id))

                else:
                    # The selected email must be verified and belong
                    # to this Principal's account.
                    cur.execute("""
                        SELECT id, password_hash
                        FROM account_email_addresses
                        WHERE account_id = %s
                          AND LOWER(email) = %s
                          AND is_verified = TRUE
                        FOR UPDATE;
                    """, (account_id, email))

                    additional = cur.fetchone()

                    if not additional:
                        return jsonify({
                            "status": "error",
                            "message": (
                                "That verified email does not belong "
                                "to your account."
                            )
                        }), 404

                    additional_id, additional_hash = additional

                    if not additional_hash:
                        return jsonify({
                            "status": "error",
                            "message": (
                                "This email has no password set yet. "
                                "Verify it and set its password first."
                            )
                        }), 409

                    if not check_password_hash(
                        additional_hash, current_password
                    ):
                        return jsonify({
                            "status": "error",
                            "message": "The current password is incorrect."
                        }), 401

                    # Prevent both emails from using the same password.
                    if check_password_hash(primary_hash, new_password):
                        return jsonify({
                            "status": "error",
                            "message": (
                                "Use a different password from the "
                                "primary email's password."
                            )
                        }), 400

                    new_hash = generate_password_hash(new_password)

                    cur.execute("""
                        UPDATE account_email_addresses
                        SET password_hash = %s
                        WHERE id = %s
                          AND account_id = %s
                          AND is_verified = TRUE;
                    """, (new_hash, additional_id, account_id))

        return jsonify({
            "status": "ok",
            "message": "Password updated for the selected email only."
        }), 200

    except Exception:
        app.logger.exception("Principal email password update failed")
        return jsonify({
            "status": "error",
            "message": "Could not update the password. Please try again."
        }), 503

@app.get("/api/principal/hods")
@limiter.limit("30 per minute")
def list_principal_hods():
    auth_error = require_principal()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        b.id, b.name, b.code, b.is_active,
                        a.id, a.full_name, a.email, a.is_active,
                        EXISTS (
                            SELECT 1 FROM account_credentials c
                            WHERE c.account_id = a.id
                        ) AS password_set,
                        (
                            SELECT MAX(t.expires_at)
                            FROM hod_setup_tokens t
                            WHERE t.account_id = a.id
                              AND t.used_at IS NULL
                              AND t.expires_at > CURRENT_TIMESTAMP
                        ) AS setup_expires_at
                    FROM branches b
                    LEFT JOIN hod_assignments h ON h.branch_id = b.id
                    LEFT JOIN accounts a ON a.id = h.account_id
                    ORDER BY b.name;
                """)
                rows = cur.fetchall()

        return jsonify({
            "status": "ok",
            "assignments": [
                {
                    "branch_id": row[0],
                    "branch_name": row[1],
                    "branch_code": row[2],
                    "branch_active": row[3],
                    "assigned": row[4] is not None,
                    "hod_account_id": row[4],
                    "hod_name": row[5],
                    "hod_email": row[6],
                    "hod_active": row[7],
                    "password_set": bool(row[8]) if row[4] is not None else False,
                    "setup_expires_at": row[9].isoformat() if row[9] else None,
                }
                for row in rows
            ],
        }), 200
    except Exception as exc:
        app.logger.exception("Principal HOD assignments could not be loaded")
        sqlstate = getattr(exc, "sqlstate", None)
        if sqlstate in {"42P01", "42703"}:
            return jsonify({
                "status": "error",
                "message": (
                    "HOD management database setup is incomplete. "
                    "Run backend/hod_management_migration.sql against ubdtce_evoting, "
                    "then restart Flask."
                ),
            }), 503
        return jsonify({
            "status": "error",
            "message": (
                "Could not load HOD assignments. Check the Flask terminal for the "
                "database error, then retry."
            ),
        }), 503


@app.post("/api/principal/hods")
@limiter.limit("10 per hour")
def assign_hod_to_branch():
    auth_error = require_principal()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    branch_id = data.get("branch_id")
    hod_name = data.get("hod_name", "")
    email = data.get("email", "")

    try:
        branch_id = int(branch_id)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Select a valid branch."}), 400

    if not isinstance(hod_name, str) or not isinstance(email, str):
        return jsonify({"status": "error", "message": "HOD name and email are required."}), 400

    hod_name = " ".join(hod_name.split())
    email = email.strip().lower()
    if not hod_name or len(hod_name) > 150:
        return jsonify({"status": "error", "message": "Enter the HOD's full name (maximum 150 characters)."}), 400
    if not valid_email_address(email):
        return jsonify({"status": "error", "message": "Enter a valid HOD email address."}), 400

    raw_token = None
    token_hash = None
    invited_name = hod_name
    invited_branch = None
    invitation_needed = False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, code, is_active
                    FROM branches
                    WHERE id = %s
                    FOR UPDATE;
                """, (branch_id,))
                branch = cur.fetchone()
                if not branch:
                    return jsonify({"status": "error", "message": "The selected branch does not exist."}), 404
                if not branch[3]:
                    return jsonify({"status": "error", "message": "Enable this branch before assigning an HOD."}), 409

                cur.execute("SELECT account_id FROM hod_assignments WHERE branch_id = %s FOR UPDATE;", (branch_id,))
                if cur.fetchone():
                    return jsonify({"status": "error", "message": "This branch already has an assigned HOD."}), 409

                cur.execute("""
                    SELECT id, role, full_name, is_active
                    FROM accounts
                    WHERE LOWER(email) = %s
                    FOR UPDATE;
                """, (email,))
                account = cur.fetchone()

                if account:
                    account_id, account_role, existing_name, account_active = account
                    if account_role != "HOD":
                        return jsonify({"status": "error", "message": "This email already belongs to a different account role."}), 409
                    if not account_active:
                        return jsonify({"status": "error", "message": "This HOD account is inactive. Contact the system administrator before assigning it."}), 409

                    cur.execute("SELECT branch_id FROM hod_assignments WHERE account_id = %s FOR UPDATE;", (account_id,))
                    existing_assignment = cur.fetchone()
                    if existing_assignment:
                        return jsonify({"status": "error", "message": "This HOD email is already assigned to another branch."}), 409

                    cur.execute("""
                        UPDATE accounts
                        SET full_name = %s
                        WHERE id = %s;
                    """, (hod_name, account_id))
                    invited_name = hod_name or existing_name or "HOD"
                else:
                    cur.execute("""
                        INSERT INTO accounts (email, role, full_name)
                        VALUES (%s, 'HOD', %s)
                        RETURNING id;
                    """, (email, hod_name))
                    account_id = cur.fetchone()[0]

                cur.execute("INSERT INTO hod_assignments (account_id, branch_id) VALUES (%s, %s);", (account_id, branch_id))
                cur.execute("SELECT EXISTS (SELECT 1 FROM account_credentials WHERE account_id = %s);", (account_id,))
                invitation_needed = not cur.fetchone()[0]

                if invitation_needed:
                    raw_token = secrets.token_urlsafe(32)
                    token_hash = hashlib.sha256(raw_token.encode("utf-8")).digest()
                    cur.execute("""
                        UPDATE hod_setup_tokens
                        SET used_at = CURRENT_TIMESTAMP
                        WHERE account_id = %s AND used_at IS NULL;
                    """, (account_id,))
                    cur.execute("""
                        INSERT INTO hod_setup_tokens
                            (account_id, branch_id, target_email, token_hash, expires_at)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP + (%s * INTERVAL '1 hour'));
                    """, (account_id, branch_id, email, token_hash, HOD_SETUP_TOKEN_HOURS))

                    # Sending inside the database transaction prevents an assigned,
                    # password-less account from being committed without its invitation.
                    send_hod_setup_email(email, raw_token, invited_name, branch[1])

                write_audit_event(cur, "HOD_ASSIGNED_TO_BRANCH", {
                    "actor_account_id": session["account_id"],
                    "hod_account_id": account_id,
                    "branch_id": branch_id,
                    "branch_code": branch[2],
                    "hod_email": email,
                    "invitation_sent": invitation_needed,
                })
                invited_branch = branch[1]

        return jsonify({
            "status": "ok",
            "message": (
                f"{invited_name} was assigned to {invited_branch}. A one-time password-creation link was sent to {email}."
                if invitation_needed else
                f"{invited_name} was assigned to {invited_branch}. This HOD account already has a password."
            ),
            "invitation_sent": invitation_needed,
        }), 201
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            return jsonify({"status": "error", "message": "This email or branch is already assigned. Refresh the HOD list and try again."}), 409
        app.logger.exception("HOD assignment failed")
        if getattr(exc, "sqlstate", None) in {"42P01", "42703"}:
            return jsonify({
                "status": "error",
                "message": (
                    "HOD management database setup is incomplete. "
                    "Run backend/hod_management_migration.sql against ubdtce_evoting, "
                    "then restart Flask."
                ),
            }), 503
        return jsonify({
            "status": "error",
            "message": (
                "The HOD could not be assigned. Check the Flask terminal for the "
                "server-side error and verify the email service configuration."
            ),
        }), 503


@app.post("/api/principal/hods/<int:account_id>/resend-invitation")
@limiter.limit("5 per hour")
def resend_hod_setup_invitation(account_id):
    auth_error = require_principal()
    if auth_error:
        return auth_error

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).digest()
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT a.email, a.full_name, b.id, b.name
                    FROM accounts a
                    JOIN hod_assignments h ON h.account_id = a.id
                    JOIN branches b ON b.id = h.branch_id
                    WHERE a.id = %s AND a.role = 'HOD'
                      AND a.is_active = TRUE AND b.is_active = TRUE
                    FOR UPDATE OF a, h, b;
                """, (account_id,))
                record = cur.fetchone()
                if not record:
                    return jsonify({"status": "error", "message": "Assigned HOD account not found."}), 404

                cur.execute("SELECT 1 FROM account_credentials WHERE account_id = %s;", (account_id,))
                if cur.fetchone():
                    return jsonify({"status": "error", "message": "This HOD has already created a password. They can now sign in."}), 409

                email, hod_name, branch_id, branch_name = record
                cur.execute("""
                    UPDATE hod_setup_tokens
                    SET used_at = CURRENT_TIMESTAMP
                    WHERE account_id = %s AND used_at IS NULL;
                """, (account_id,))
                cur.execute("""
                    INSERT INTO hod_setup_tokens
                        (account_id, branch_id, target_email, token_hash, expires_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP + (%s * INTERVAL '1 hour'));
                """, (account_id, branch_id, email, token_hash, HOD_SETUP_TOKEN_HOURS))
                send_hod_setup_email(email, raw_token, hod_name or "HOD", branch_name)
                write_audit_event(cur, "HOD_SETUP_INVITATION_RESENT", {
                    "actor_account_id": session["account_id"],
                    "hod_account_id": account_id,
                    "branch_id": branch_id,
                    "hod_email": email,
                })

        return jsonify({"status": "ok", "message": f"A new password-creation link was sent to {email}."}), 200
    except Exception:
        app.logger.exception("HOD setup invitation resend failed")
        return jsonify({"status": "error", "message": "The invitation could not be resent. Check the email service and try again."}), 503


@app.delete("/api/principal/hods/<int:account_id>")
@limiter.limit("10 per hour")
def remove_hod_assignment(account_id):

    auth_error = require_principal()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Find the assigned HOD
                cur.execute("""
                    SELECT a.id, a.email, a.full_name,
                           h.branch_id, b.name
                    FROM accounts a
                    JOIN hod_assignments h ON h.account_id = a.id
                    JOIN branches b ON b.id = h.branch_id
                    WHERE a.id = %s
                      AND a.role = 'HOD'
                    FOR UPDATE OF a, h;
                """, (account_id,))

                hod = cur.fetchone()

                if not hod:
                    return jsonify({
                        "status": "error",
                        "message": "HOD assignment not found."
                    }), 404

                hod_id, email, name, branch_id, branch_name = hod

                # Cancel unused invitation links
                cur.execute("""
                    UPDATE hod_setup_tokens
                    SET used_at = CURRENT_TIMESTAMP
                    WHERE account_id = %s
                      AND used_at IS NULL;
                """, (hod_id,))

                # Remove HOD from department
                cur.execute("""
                    DELETE FROM hod_assignments
                    WHERE account_id = %s;
                """, (hod_id,))

                # Disable old HOD account
                cur.execute("""
                    UPDATE accounts
                    SET is_active = FALSE
                    WHERE id = %s;
                """, (hod_id,))

                # Save audit record
                write_audit_event(
                    cur,
                    "HOD_REMOVED_FROM_BRANCH",
                    {
                        "actor_account_id": session["account_id"],
                        "hod_account_id": hod_id,
                        "hod_email": email,
                        "branch_id": branch_id,
                        "branch_name": branch_name
                    }
                )

        return jsonify({
            "status": "ok",
            "message": f"{name} removed from {branch_name} successfully."
        }), 200

    except Exception:
        app.logger.exception("HOD removal failed")

        return jsonify({
            "status": "error",
            "message": "Unable to remove HOD. Please try again."
        }), 503    

@app.post("/api/principal/branches")
@limiter.limit("20 per minute")
def create_branch():
    auth_error = require_principal()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    name = data.get("name")
    code = data.get("code")

    if not isinstance(name, str) or not isinstance(code, str):
        return jsonify({"status": "error", "message": "Branch name and code are required."}), 400

    name = name.strip()
    code = code.strip().upper()
    if not name or not code or len(name) > 120 or len(code) > 20:
        return jsonify({"status": "error", "message": "Enter a valid branch name and code."}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO branches (name, code)
                    VALUES (%s, %s)
                    RETURNING id, name, code, is_active;
                """, (name, code))
                branch = cur.fetchone()
                write_audit_event(cur, "BRANCH_CREATED", {
                    "actor_account_id": session["account_id"],
                    "branch_id": branch[0], "name": branch[1], "code": branch[2]
                })

        return jsonify({
            "status": "ok",
            "message": "Branch created successfully.",
            "branch": {"id": branch[0], "name": branch[1], "code": branch[2], "is_active": branch[3]},
        }), 201
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            return jsonify({"status": "error", "message": "A branch with that name or code already exists."}), 409
        app.logger.exception("Branch creation failed")
        return jsonify({"status": "error", "message": "Could not create branch."}), 503


@app.patch("/api/principal/branches/<int:branch_id>")
@limiter.limit("30 per minute")
def update_branch(branch_id):
    auth_error = require_principal()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    allowed_fields = {"name", "code", "is_active"}
    if not data or not set(data).issubset(allowed_fields):
        return jsonify({"status": "error", "message": "Provide name, code, and/or is_active."}), 400

    updates, values = [], []
    if "name" in data:
        name = data["name"]
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            return jsonify({"status": "error", "message": "Branch name must contain 1–120 characters."}), 400
        updates.append("name = %s")
        values.append(name.strip())
    if "code" in data:
        code = data["code"]
        if not isinstance(code, str) or not code.strip() or len(code.strip()) > 20:
            return jsonify({"status": "error", "message": "Branch code must contain 1–20 characters."}), 400
        updates.append("code = %s")
        values.append(code.strip().upper())
    if "is_active" in data:
        if not isinstance(data["is_active"], bool):
            return jsonify({"status": "error", "message": "is_active must be true or false."}), 400
        updates.append("is_active = %s")
        values.append(data["is_active"])

    values.append(branch_id)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name, code, is_active FROM branches WHERE id = %s FOR UPDATE;", (branch_id,))
                old = cur.fetchone()
                if old is None:
                    return jsonify({"status": "error", "message": "Branch not found."}), 404

                if "is_active" in data and data["is_active"] is False and old[3] is True:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM elections e
                            WHERE (
                                e.status = 'SCHEDULED'
                                OR (e.status = 'OPEN' AND e.closes_at > CURRENT_TIMESTAMP)
                            )
                              AND (
                                e.branch_id = %s
                                OR EXISTS (
                                    SELECT 1 FROM election_eligible_branches eb
                                    WHERE eb.election_id = e.id AND eb.branch_id = %s
                                )
                              )
                        );
                    """, (branch_id, branch_id))
                    if cur.fetchone()[0]:
                        return jsonify({
                            "status": "error",
                            "message": "This branch cannot be deactivated while it participates in a scheduled or open election."
                        }), 409

                cur.execute(
                    f"UPDATE branches SET {', '.join(updates)} WHERE id = %s RETURNING id, name, code, is_active;",
                    values,
                )
                branch = cur.fetchone()
                write_audit_event(cur, "BRANCH_UPDATED", {
                    "actor_account_id": session["account_id"],
                    "branch_id": branch_id,
                    "before": {"name": old[1], "code": old[2], "is_active": old[3]},
                    "after": {"name": branch[1], "code": branch[2], "is_active": branch[3]},
                })

        return jsonify({
            "status": "ok", "message": "Branch updated successfully.",
            "branch": {"id": branch[0], "name": branch[1], "code": branch[2], "is_active": branch[3]},
        }), 200
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            return jsonify({"status": "error", "message": "A branch with that name or code already exists."}), 409
        app.logger.exception("Branch update failed")
        return jsonify({"status": "error", "message": "Could not update branch."}), 503


@app.delete("/api/principal/branches/<int:branch_id>")
@limiter.limit("10 per minute")
def delete_branch(branch_id):
    auth_error = require_principal()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name, code FROM branches WHERE id = %s FOR UPDATE;", (branch_id,))
                branch = cur.fetchone()
                if branch is None:
                    return jsonify({"status": "error", "message": "Branch not found."}), 404

                cur.execute("""
                    SELECT
                      EXISTS (SELECT 1 FROM students WHERE branch_id = %s),
                      EXISTS (SELECT 1 FROM hod_assignments WHERE branch_id = %s),
                      EXISTS (SELECT 1 FROM elections WHERE branch_id = %s),
                      EXISTS (SELECT 1 FROM election_eligible_branches WHERE branch_id = %s);
                """, (branch_id, branch_id, branch_id, branch_id))
                dependencies = cur.fetchone()
                if any(dependencies):
                    return jsonify({
                        "status": "error",
                        "message": "This branch still has students, an assigned HOD, or election records. Disable it instead of deleting it."
                    }), 409

                write_audit_event(cur, "BRANCH_DELETED", {
                    "actor_account_id": session["account_id"],
                    "branch_id": branch[0], "name": branch[1], "code": branch[2]
                })
                cur.execute("DELETE FROM branches WHERE id = %s;", (branch_id,))

        return jsonify({"status": "ok", "message": "Branch deleted successfully."}), 200
    except Exception:
        app.logger.exception("Branch deletion failed")
        return jsonify({"status": "error", "message": "Could not delete branch."}), 503


@app.post("/api/principal/elections")
@limiter.limit("10 per minute")
def create_principal_election():
    auth_error = require_principal()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    title = data.get("title")
    description = data.get("description", "")
    election_type = data.get("election_type", "PRESIDENT")
    position_name = data.get("position_name")
    branch_ids = data.get("branch_ids")
    duration = data.get("duration_minutes")
    admission_year = data.get("admission_year")
    academic_year = data.get("academic_year")
    semester = data.get("semester")

    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
        return jsonify({"status": "error", "message": "Enter an election title (maximum 200 characters)."}), 400
    if not isinstance(description, str) or len(description.strip()) > 5000:
        return jsonify({"status": "error", "message": "Election description must contain at most 5000 characters."}), 400
    if not isinstance(election_type, str) or election_type not in COLLEGE_ELECTION_TYPES:
        return jsonify({"status": "error", "message": "Choose a supported college-level election category."}), 400
    if position_name is not None and not isinstance(position_name, str):
        return jsonify({"status": "error", "message": "Invalid representative position name."}), 400
    position_name = position_name.strip() if isinstance(position_name, str) else None
    if election_type == "OTHER" and (not position_name or len(position_name) > 120):
        return jsonify({"status": "error", "message": "Enter an other representative position name (maximum 120 characters)."}), 400
    if election_type != "OTHER" and position_name:
        return jsonify({"status": "error", "message": "A custom position name is only valid for Other college positions."}), 400
    if not isinstance(branch_ids, list) or not branch_ids or any(type(value) is not int or value <= 0 for value in branch_ids):
        return jsonify({"status": "error", "message": "Select at least one valid participating branch."}), 400
    branch_ids = sorted(set(branch_ids))
    if not isinstance(duration, int) or not 1 <= duration <= 10080:
        return jsonify({"status": "error", "message": "Voting duration must be between 1 and 10080 minutes."}), 400
    cohort_values = (admission_year, academic_year, semester)
    if any(value is not None for value in cohort_values) and not all(
        value is not None for value in cohort_values
    ):
        return jsonify({
            "status": "error",
            "message": "Select admission year, academic year, and semester together, or leave the voter cohort unrestricted.",
        }), 400
    if admission_year is not None:
        if not valid_admission_year(admission_year):
            return jsonify({"status": "error", "message": "Invalid admission year."}), 400
        if not valid_admission_year(academic_year):
            return jsonify({"status": "error", "message": "Invalid academic year."}), 400
        if type(semester) is not int or not 1 <= semester <= 12:
            return jsonify({"status": "error", "message": "Invalid semester."}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM branches WHERE id = ANY(%s) AND is_active = TRUE ORDER BY id;", (branch_ids,))
                valid_branches = [row[0] for row in cur.fetchall()]
                if valid_branches != branch_ids:
                    return jsonify({"status": "error", "message": "One or more selected branches do not exist or are inactive."}), 400

                # Snapshot active students in the selected branches. The optional
                # class filter makes college-election voter eligibility explicit;
                # the CR-winner rule applies to candidates, not to voters.
                cur.execute("""
                    SELECT COUNT(*)
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    WHERE s.branch_id = ANY(%s)
                      AND (%s::smallint IS NULL OR s.admission_year = %s)
                      AND (%s::smallint IS NULL OR s.academic_year = %s)
                      AND (%s::smallint IS NULL OR s.semester = %s)
                      AND a.role = 'STUDENT'
                      AND a.is_active = TRUE;
                """, (
                    branch_ids, admission_year, admission_year,
                    academic_year, academic_year, semester, semester,
                ))
                eligible_count = cur.fetchone()[0]
                if eligible_count == 0:
                    return jsonify({"status": "error", "message": "No active students match the selected branches and academic cohort."}), 409

                cur.execute("""
                    INSERT INTO elections (
                        title, description, election_type, position_name, branch_id, admission_year, academic_year, semester,
                        duration_minutes, opens_at, closes_at, status, created_by
                    )
                    VALUES (
                        %s, %s, %s, %s, NULL, %s, %s, %s,
                        %s,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP + (%s * INTERVAL '1 minute'),
                        'DRAFT', %s
                    )
                    RETURNING id, title, opens_at, closes_at;
                """, (
                    title.strip(),
                    description.strip(),
                    election_type,
                    position_name,
                    admission_year,
                    academic_year,
                    semester,
                    duration,
                    duration,
                    session["account_id"],
                ))
                election = cur.fetchone()

                for branch_id in branch_ids:
                    cur.execute("""
                        INSERT INTO election_eligible_branches (election_id, branch_id)
                        VALUES (%s, %s);
                    """, (election[0], branch_id))

                cur.execute("""
                    INSERT INTO voter_eligibility (election_id, student_id)
                    SELECT %s, s.id
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    WHERE s.branch_id = ANY(%s)
                      AND (%s::smallint IS NULL OR s.admission_year = %s)
                      AND (%s::smallint IS NULL OR s.academic_year = %s)
                      AND (%s::smallint IS NULL OR s.semester = %s)
                      AND a.role = 'STUDENT'
                      AND a.is_active = TRUE;
                """, (
                    election[0], branch_ids, admission_year, admission_year,
                    academic_year, academic_year, semester, semester,
                ))
                inserted_eligible_count = cur.rowcount
                if inserted_eligible_count != eligible_count:
                    raise RuntimeError("Voter eligibility rows could not be created consistently.")

                write_audit_event(cur, "ELECTION_CREATED", {
                    "actor_account_id": session["account_id"],
                    "election_id": election[0],
                    "title": election[1],
                    "description": description.strip(),
                    "election_type": election_type,
                    "position_name": position_name,
                    "branch_ids": branch_ids,
                    "admission_year": admission_year,
                    "academic_year": academic_year,
                    "semester": semester,
                    "duration_minutes": duration,
                    "eligible_voters": eligible_count,
                }, election_id=election[0])

        return jsonify({
            "status": "ok",
            "message": (
                f"{COLLEGE_ELECTION_POLICIES[election_type]['label']} election created as a draft. "
                "Register and approve at least two eligible candidates before starting voting."
            ),
            "election": {
                "id": election[0], "title": election[1],
                "opens_at": election[2].isoformat(),
                "closes_at": election[3].isoformat(),
                "eligible_voters": eligible_count,
                "admission_year": admission_year,
                "academic_year": academic_year,
                "semester": semester,
                "election_type": election_type,
                "position_name": position_name,
                "candidate_eligibility": COLLEGE_ELECTION_POLICIES[election_type]["eligibility"],
                "status": "DRAFT",
            },
        }), 201
    except Exception:
        app.logger.exception("College election creation failed")
        return jsonify({"status": "error", "message": "Could not create the election."}), 503


def _principal_college_election(cur, election_id, lock=False):
    """Return a Principal-owned college election without exposing ballots."""
    lock_clause = " FOR UPDATE OF e" if lock else ""
    cur.execute(f"""
        SELECT e.id, e.title, e.description, e.election_type, e.status,
               e.opens_at, e.closes_at, e.duration_minutes, e.admission_year, e.academic_year, e.semester,
               (SELECT COUNT(*) FROM voter_eligibility ve
                WHERE ve.election_id = e.id) AS eligible_voters,
               (SELECT COUNT(*) FROM voter_participation vp
                WHERE vp.election_id = e.id) AS participation_count,
               (SELECT COUNT(*) FROM candidates c
                WHERE c.election_id = e.id) AS candidate_count,
               (SELECT COUNT(*) FROM candidates c
                WHERE c.election_id = e.id
                  AND c.is_approved = TRUE
                  AND c.review_status = 'APPROVED') AS approved_candidate_count,
               e.position_name
        FROM elections e
        WHERE e.id = %s
          AND e.branch_id IS NULL
          AND e.election_type = ANY(%s)
        {lock_clause};
    """, (election_id, list(COLLEGE_ELECTION_TYPES)))
    return cur.fetchone()


def _principal_college_election_payload(row):
    policy = COLLEGE_ELECTION_POLICIES[row[3]]
    return {
        "id": row[0],
        "title": row[1],
        "description": row[2] or "",
        "election_type": row[3],
        "status": row[4],
        "opens_at": _isoformat(row[5]),
        "closes_at": _isoformat(row[6]),
        "duration_minutes": row[7],
        "admission_year": row[8],
        "academic_year": row[9],
        "semester": row[10],
        "eligible_voters": row[11],
        "participation_count": row[12],
        "candidate_count": row[13],
        "approved_candidate_count": row[14],
        "position_name": row[15],
        "position_label": row[15] or policy["label"],
        "candidate_eligibility": policy["eligibility"],
        "candidate_eligibility_label": policy["eligibility_label"],
    }


@app.get("/api/principal/elections")
@limiter.limit("60 per minute")
def list_principal_elections():
    """List only college-wide elections for the authenticated Principal."""
    auth_error = require_principal()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT e.id, e.title, e.description, e.election_type, e.status,
                           e.opens_at, e.closes_at, e.duration_minutes, e.admission_year, e.academic_year, e.semester,
                           (SELECT COUNT(*) FROM voter_eligibility ve
                            WHERE ve.election_id = e.id),
                           (SELECT COUNT(*) FROM voter_participation vp
                            WHERE vp.election_id = e.id),
                           (SELECT COUNT(*) FROM candidates c
                            WHERE c.election_id = e.id),
                           (SELECT COUNT(*) FROM candidates c
                            WHERE c.election_id = e.id
                              AND c.is_approved = TRUE
                              AND c.review_status = 'APPROVED'),
                           e.position_name
                    FROM elections e
                    WHERE e.branch_id IS NULL
                      AND e.election_type = ANY(%s)
                    ORDER BY e.created_at DESC, e.id DESC;
                """, (list(COLLEGE_ELECTION_TYPES),))
                elections = [
                    _principal_college_election_payload(row)
                    for row in cur.fetchall()
                ]
        return jsonify({"status": "ok", "elections": elections}), 200
    except Exception:
        app.logger.exception("Principal election list retrieval failed")
        return jsonify({
            "status": "error",
            "message": "Could not retrieve college-wide elections.",
        }), 503


@app.get("/api/principal/elections/<int:election_id>/candidates")
@limiter.limit("60 per minute")
def list_principal_election_candidates(election_id):
    auth_error = require_principal()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                election = _principal_college_election(cur, election_id)
                if not election:
                    return jsonify({
                        "status": "error",
                        "message": "College-wide election not found.",
                    }), 404
                cur.execute("""
                    SELECT c.id, s.full_name, s.usn, b.name, c.manifesto,
                           c.symbol_key, c.is_approved, c.review_status, c.created_at
                    FROM candidates c
                    JOIN students s ON s.id = c.student_id
                    JOIN branches b ON b.id = s.branch_id
                    WHERE c.election_id = %s
                    ORDER BY c.created_at ASC, c.id ASC;
                """, (election_id,))
                candidates = [
                    {
                        "id": row[0],
                        "name": row[1],
                        "usn": row[2],
                        "branch": row[3],
                        "manifesto": row[4] or "",
                        "symbol_key": row[5],
                        "symbol": candidate_symbol_payload(row[5]),
                        "is_approved": row[6],
                        "review_status": row[7],
                        "created_at": _isoformat(row[8]),
                    }
                    for row in cur.fetchall()
                ]
        return jsonify({
            "status": "ok",
            "election": _principal_college_election_payload(election),
            "candidates": candidates,
        }), 200
    except Exception:
        app.logger.exception("Principal candidate list retrieval failed")
        return jsonify({
            "status": "error",
            "message": "Could not retrieve college-wide candidates.",
        }), 503


def _principal_eligible_candidates(cur, election_id, election_type, usn=None):
    """Return students eligible to stand in a college-wide election.

    The selected branches and optional cohort always apply.  Where the policy
    requires an elected representative, a student must be an approved
    candidate with a non-zero, tied-or-winning total in a *closed* CR/FR
    election.  A legacy ``is_cr``/``is_fr`` flag is never sufficient.
    """
    policy = COLLEGE_ELECTION_POLICIES[election_type]
    winner_types = list(policy["winner_types"])
    cur.execute("""
        WITH representative_winners AS (
            SELECT DISTINCT ON (elected.student_id, branch_election.branch_id)
                elected.student_id,
                branch_election.branch_id,
                elected.symbol_key,
                branch_election.election_type,
                branch_election.title
            FROM elections branch_election
            JOIN candidates elected
              ON elected.election_id = branch_election.id
             AND elected.is_approved = TRUE
             AND elected.review_status = 'APPROVED'
            WHERE branch_election.election_type = ANY(%s::text[])
              AND branch_election.status = 'CLOSED'
              AND (
                  SELECT COUNT(*)
                  FROM ballots winning_ballot
                  WHERE winning_ballot.election_id = branch_election.id
                    AND winning_ballot.candidate_id = elected.id
              ) > 0
              AND NOT EXISTS (
                  SELECT 1
                  FROM candidates challenger
                  WHERE challenger.election_id = branch_election.id
                    AND challenger.is_approved = TRUE
                    AND challenger.review_status = 'APPROVED'
                    AND (
                        SELECT COUNT(*) FROM ballots challenger_ballot
                        WHERE challenger_ballot.election_id = branch_election.id
                          AND challenger_ballot.candidate_id = challenger.id
                    ) > (
                        SELECT COUNT(*) FROM ballots elected_ballot
                        WHERE elected_ballot.election_id = branch_election.id
                          AND elected_ballot.candidate_id = elected.id
                    )
              )
            ORDER BY elected.student_id, branch_election.branch_id,
                     branch_election.closes_at DESC, branch_election.id DESC,
                     elected.id
        )
        SELECT DISTINCT
            s.id,
            s.full_name,
            s.usn,
            b.name,
            representative_winners.symbol_key,
            representative_winners.election_type,
            representative_winners.title
        FROM students s
        JOIN accounts a ON a.id = s.account_id
        JOIN branches b ON b.id = s.branch_id
        JOIN election_eligible_branches eb
          ON eb.branch_id = s.branch_id AND eb.election_id = %s
        JOIN elections college_election
          ON college_election.id = eb.election_id
        LEFT JOIN representative_winners
          ON representative_winners.student_id = s.id
         AND representative_winners.branch_id = s.branch_id
        WHERE (%s::text IS NULL OR UPPER(s.usn) = %s)
          AND a.role = 'STUDENT'
          AND a.is_active = TRUE
          AND b.is_active = TRUE
          AND (college_election.admission_year IS NULL
               OR s.admission_year = college_election.admission_year)
          AND (college_election.academic_year IS NULL
               OR s.academic_year = college_election.academic_year)
          AND (college_election.semester IS NULL
               OR s.semester = college_election.semester)
          AND (
              cardinality(%s::text[]) = 0
               OR representative_winners.student_id IS NOT NULL
          )
        ORDER BY b.name, s.usn;
    """, (winner_types, election_id, usn, usn, winner_types))
    return cur.fetchall()


def _principal_eligible_candidate(cur, election_id, election_type, usn):
    """Return one policy-eligible student for registration, if present."""
    candidates = _principal_eligible_candidates(cur, election_id, election_type, usn)
    return candidates[0] if candidates else None


@app.get("/api/principal/elections/<int:election_id>/eligible-candidates")
@limiter.limit("60 per minute")
def list_principal_eligible_candidates(election_id):
    """List the students eligible under the college election's policy."""
    auth_error = require_principal()
    if auth_error:
        return auth_error
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                election = _principal_college_election(cur, election_id)
                if not election:
                    return jsonify({"status": "error", "message": "College-wide election not found."}), 404
                rows = _principal_eligible_candidates(cur, election_id, election[3])
                candidates = [
                    {
                        "name": row[1],
                        "usn": row[2],
                        "branch": row[3],
                        "representative_symbol_key": row[4],
                        "representative_symbol": candidate_symbol_payload(row[4]),
                        "representative_type": row[5],
                        "representative_election": row[6],
                    }
                    for row in rows
                ]
        return jsonify({
            "status": "ok",
            "candidate_eligibility": COLLEGE_ELECTION_POLICIES[election[3]]["eligibility"],
            "candidates": candidates,
        }), 200
    except Exception:
        app.logger.exception("Eligible college candidate list retrieval failed")
        return jsonify({"status": "error", "message": "Could not load eligible candidates."}), 503


@app.post("/api/principal/elections/<int:election_id>/candidates")
@limiter.limit("20 per minute")
def add_principal_election_candidate(election_id):
    auth_error = require_principal()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    usn = data.get("usn", "")
    manifesto = data.get("manifesto", "")
    symbol_key = data.get("symbol_key")
    if not isinstance(usn, str) or not isinstance(manifesto, str):
        return jsonify({"status": "error", "message": "Invalid candidate details."}), 400
    usn = usn.strip().upper()
    manifesto = manifesto.strip()
    if not re.fullmatch(r"[0-9]UB[0-9]{2}[A-Z]{2}[0-9]{3}", usn):
        return jsonify({"status": "error", "message": "Enter a valid 10-character USN."}), 400
    if len(manifesto) > 5000:
        return jsonify({"status": "error", "message": "Manifesto cannot exceed 5000 characters."}), 400
    if not valid_candidate_symbol(symbol_key):
        return jsonify({"status": "error", "message": "Choose an approved election symbol."}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                election = _principal_college_election(cur, election_id, lock=True)
                if not election:
                    return jsonify({"status": "error", "message": "College-wide election not found."}), 404
                if election[4] != "DRAFT":
                    return jsonify({
                        "status": "error",
                        "message": "Candidates can be registered only while the election is a draft.",
                    }), 409
                student = _principal_eligible_candidate(cur, election_id, election[3], usn)
                if not student:
                    return jsonify({
                        "status": "error",
                        "message": "This student does not satisfy the candidate policy for the selected branches and cohort.",
                    }), 404
                cur.execute("""
                    SELECT 1 FROM candidates
                    WHERE election_id = %s AND symbol_key = %s;
                """, (election_id, symbol_key))
                if cur.fetchone():
                    return jsonify({
                        "status": "error",
                        "message": "That symbol is already assigned in this election.",
                    }), 409
                cur.execute("""
                    INSERT INTO candidates (election_id, student_id, manifesto, symbol_key)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (election_id, student_id) DO NOTHING
                    RETURNING id;
                """, (election_id, student[0], manifesto or None, symbol_key))
                candidate = cur.fetchone()
                if not candidate:
                    return jsonify({
                        "status": "error",
                        "message": "This student is already registered as a candidate.",
                    }), 409
                candidate_id = candidate[0]
                write_audit_event(cur, "PRINCIPAL_CANDIDATE_REGISTERED", {
                    "candidate_id": candidate_id,
                    "student_id": student[0],
                    "usn": usn,
                    "symbol_key": symbol_key,
                    "registered_by": session["account_id"],
                }, election_id)
        return jsonify({
            "status": "ok",
            "message": "Candidate registered successfully. Approval is pending.",
            "candidate": {
                "id": candidate_id,
                "name": student[1],
                "usn": usn,
                "branch": student[3],
                "manifesto": manifesto,
                "symbol_key": symbol_key,
                "symbol": candidate_symbol_payload(symbol_key),
                "is_approved": False,
                "review_status": "PENDING",
            },
        }), 201
    except Exception:
        app.logger.exception("Principal candidate registration failed")
        return jsonify({"status": "error", "message": "Could not register the candidate."}), 503


@app.post("/api/principal/elections/<int:election_id>/candidates/<int:candidate_id>/<action>")
@limiter.limit("30 per minute")
def review_principal_election_candidate(election_id, candidate_id, action):
    auth_error = require_principal()
    if auth_error:
        return auth_error
    if action not in {"approve", "reject"}:
        return jsonify({"status": "error", "message": "Invalid candidate review action."}), 404

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                election = _principal_college_election(cur, election_id, lock=True)
                if not election:
                    return jsonify({"status": "error", "message": "College-wide election not found."}), 404
                if election[4] != "DRAFT":
                    return jsonify({
                        "status": "error",
                        "message": "Candidates cannot be reviewed after voting starts.",
                    }), 409
                cur.execute("""
                    SELECT c.student_id, s.usn
                    FROM candidates c
                    JOIN students s ON s.id = c.student_id
                    WHERE c.id = %s AND c.election_id = %s
                    FOR UPDATE OF c;
                """, (candidate_id, election_id))
                candidate = cur.fetchone()
                if not candidate:
                    return jsonify({"status": "error", "message": "Candidate not found."}), 404
                approved = action == "approve"
                review_status = "APPROVED" if approved else "REJECTED"
                cur.execute("""
                    UPDATE candidates
                    SET is_approved = %s,
                        review_status = %s,
                        reviewed_at = CURRENT_TIMESTAMP,
                        reviewed_by = %s
                    WHERE id = %s AND election_id = %s;
                """, (
                    approved,
                    review_status,
                    session["account_id"],
                    candidate_id,
                    election_id,
                ))
                write_audit_event(cur, f"PRINCIPAL_CANDIDATE_{review_status}", {
                    "candidate_id": candidate_id,
                    "student_id": candidate[0],
                    "usn": candidate[1],
                    "reviewed_by": session["account_id"],
                }, election_id)
        return jsonify({
            "status": "ok",
            "message": f"Candidate {action}d successfully.",
        }), 200
    except Exception:
        app.logger.exception("Principal candidate review failed")
        return jsonify({"status": "error", "message": "Could not review the candidate."}), 503


@app.post("/api/principal/elections/<int:election_id>/start")
@limiter.limit("10 per minute")
def start_principal_election(election_id):
    auth_error = require_principal()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                election = _principal_college_election(cur, election_id, lock=True)
                if not election:
                    return jsonify({"status": "error", "message": "College-wide election not found."}), 404
                if election[4] != "DRAFT":
                    return jsonify({"status": "error", "message": "Only draft elections can be started."}), 409
                if not election[7] or not 1 <= election[7] <= 10080:
                    return jsonify({"status": "error", "message": "Invalid election duration."}), 400
                if election[14] < 2:
                    return jsonify({
                        "status": "error",
                        "message": "At least two approved candidates are required to start the election.",
                    }), 409
                cur.execute("""
                    WITH start_time AS (SELECT clock_timestamp() AS started_at)
                    UPDATE elections e
                    SET opens_at = start_time.started_at,
                        closes_at = start_time.started_at + (e.duration_minutes * INTERVAL '1 minute'),
                        status = 'OPEN'
                    FROM start_time
                    WHERE e.id = %s
                    RETURNING e.opens_at, e.closes_at;
                """, (election_id,))
                opens_at, closes_at = cur.fetchone()
                write_audit_event(cur, "PRINCIPAL_ELECTION_STARTED", {
                    "election_id": election_id,
                    "approved_candidates": election[14],
                    "duration_minutes": election[7],
                    "started_by": session["account_id"],
                }, election_id)
        return jsonify({
            "status": "ok",
            "message": "College-wide election started successfully.",
            "election": {
                "id": election_id,
                "status": "OPEN",
                "opens_at": _isoformat(opens_at),
                "closes_at": _isoformat(closes_at),
            },
        }), 200
    except Exception:
        app.logger.exception("Principal election start failed")
        return jsonify({"status": "error", "message": "Could not start the election."}), 503


@app.post("/api/principal/elections/<int:election_id>/close")
@limiter.limit("10 per minute")
def close_principal_election(election_id):
    auth_error = require_principal()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                election = _principal_college_election(cur, election_id, lock=True)
                if not election:
                    return jsonify({"status": "error", "message": "College-wide election not found."}), 404
                if election[4] == "CLOSED":
                    return jsonify({"status": "ok", "message": "This election is already closed."}), 200
                if election[4] != "OPEN":
                    return jsonify({"status": "error", "message": "Only open elections can be closed."}), 409
                cur.execute("""
                    UPDATE elections
                    SET status = 'CLOSED', closes_at = clock_timestamp()
                    WHERE id = %s
                    RETURNING closes_at;
                """, (election_id,))
                closes_at = cur.fetchone()[0]
                write_audit_event(cur, "PRINCIPAL_ELECTION_CLOSED", {
                    "election_id": election_id,
                    "closed_by": session["account_id"],
                    "close_reason": "PRINCIPAL_MANUAL",
                }, election_id)
                write_election_result_commitment(cur, election_id)
        return jsonify({
            "status": "ok",
            "message": "College-wide election closed successfully.",
            "election": {
                "id": election_id,
                "status": "CLOSED",
                "closes_at": _isoformat(closes_at),
            },
        }), 200
    except Exception:
        app.logger.exception("Principal election closure failed")
        return jsonify({"status": "error", "message": "Could not close the election."}), 503


@app.get("/api/principal/elections/<int:election_id>/results")
@limiter.limit("60 per minute")
def principal_election_results(election_id):
    auth_error = require_principal()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                election = _principal_college_election(cur, election_id, lock=True)
                if not election:
                    return jsonify({"status": "error", "message": "College-wide election not found."}), 404
                if election[4] == "OPEN" and election[6] <= __import__("datetime").datetime.now(timezone.utc):
                    cur.execute("UPDATE elections SET status = 'CLOSED' WHERE id = %s;", (election_id,))
                    write_audit_event(cur, "PRINCIPAL_ELECTION_AUTO_CLOSED", {
                        "election_id": election_id,
                        "close_reason": "TIME_EXPIRED",
                    }, election_id)
                    write_election_result_commitment(cur, election_id)
                    election = (*election[:4], "CLOSED", *election[5:])
                if election[4] != "CLOSED":
                    return jsonify({
                        "status": "error",
                        "message": "Results are available only after the election is closed.",
                    }), 409
                result = _election_result_payload(cur, election_id)
        return jsonify({"status": "ok", "result": result}), 200
    except Exception:
        app.logger.exception("Principal election results retrieval failed")
        return jsonify({"status": "error", "message": "Could not calculate election results."}), 503


# ------------------------------------------
# 5. REQUEST A PASSWORD RESET
# ------------------------------------------
@app.post("/api/auth/forgot-password")
@limiter.limit("3 per hour")

def forgot_password():
    data = request.get_json(silent=True) or {}

    usn = data.get("usn", "")
    email = data.get("email", "")

    if not isinstance(usn, str) or not isinstance(email, str):
        return jsonify({
            "status": "error",
            "message": "Enter a valid USN or email address."
        }), 400

    usn = usn.strip().upper()
    email = email.strip().lower()

    # Require exactly one recovery identifier.
    if bool(usn) == bool(email):
        return jsonify({
            "status": "error",
            "message": "Enter your USN or registered email address."
        }), 400

    if usn and not re.fullmatch(
        r"[0-9]UB[0-9]{2}[A-Z]{2}[0-9]{3}", usn
    ):
        return jsonify({
            "status": "error",
            "message": "Enter a valid 10-character USN."
        }), 400

    if email and not valid_email_address(email):
        return jsonify({
            "status": "error",
            "message": "Enter a valid registered email address."
        }), 400

    generic_response = {
        "status": "ok",
        "message": (
            "If an eligible account exists, password-reset "
            "instructions will be sent to its registered email."
        )
    }

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                if usn:
                    # Student recovery using USN.
                    # Only activated student accounts are eligible.
                    cur.execute("""
                        SELECT
                            a.id,
                            a.email,
                            a.email AS target_email,
                            'PRIMARY' AS credential_type,
                            a.role
                        FROM accounts a
                        JOIN students s
                            ON s.account_id = a.id
                        JOIN account_credentials c
                            ON c.account_id = a.id
                        WHERE UPPER(s.usn) = %s
                          AND a.is_active = TRUE
                          AND a.role = 'STUDENT'
                        LIMIT 1;
                    """, (usn,))

                else:
                    # Principal and HOD recovery using email.
                    # Preserve the existing additional-email
                    # recovery option for Principal accounts.
                    cur.execute("""
                        SELECT
                            a.id,
                            a.email,
                            a.email AS target_email,
                            'PRIMARY' AS credential_type,
                            a.role
                        FROM accounts a
                        WHERE LOWER(a.email) = %s
                          AND a.is_active = TRUE
                          AND a.role IN ('PRINCIPAL', 'HOD')
                          AND (
                              a.role = 'PRINCIPAL'
                              OR (
                                  a.role = 'HOD'
                                  AND EXISTS (
                                      SELECT 1
                                      FROM account_credentials c
                                      WHERE c.account_id = a.id
                                  )
                                  AND EXISTS (
                                      SELECT 1
                                      FROM hod_assignments h
                                      JOIN branches b
                                        ON b.id = h.branch_id
                                      WHERE h.account_id = a.id
                                        AND b.is_active = TRUE
                                  )
                              )
                          )

                        UNION ALL

                        SELECT
                            a.id,
                            a.email,
                            e.email AS target_email,
                            'ADDITIONAL' AS credential_type,
                            a.role
                        FROM account_email_addresses e
                        JOIN accounts a
                            ON a.id = e.account_id
                        WHERE LOWER(e.email) = %s
                          AND e.is_verified = TRUE
                          AND e.password_hash IS NOT NULL
                          AND a.is_active = TRUE
                          AND a.role = 'PRINCIPAL'

                        LIMIT 1;
                    """, (email, email))

                account = cur.fetchone()

                # Do not reveal whether an account exists.
                if not account:
                    return jsonify(generic_response), 200

                (
                    account_id,
                    primary_email,
                    target_email,
                    credential_type,
                    account_role
                ) = account

                # Invalidate previous unused reset links
                # for the same destination address.
                cur.execute("""
                    UPDATE password_reset_tokens
                    SET used_at = CURRENT_TIMESTAMP
                    WHERE account_id = %s
                      AND LOWER(target_email) = %s
                      AND used_at IS NULL;
                """, (account_id, target_email.lower()))

                raw_token = secrets.token_urlsafe(32)

                token_hash = hashlib.sha256(
                    raw_token.encode("utf-8")
                ).digest()

                cur.execute("""
                    INSERT INTO password_reset_tokens (
                        account_id,
                        target_email,
                        token_hash,
                        expires_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        CURRENT_TIMESTAMP
                            + (%s * INTERVAL '1 minute')
                    );
                """, (
                    account_id,
                    target_email,
                    token_hash,
                    RESET_TOKEN_MINUTES
                ))

        # Send email only after the database transaction commits.
        try:
            send_reset_email(
                target_email,
                raw_token,
                account_role
            )

        except Exception:
            app.logger.exception(
                "Password reset email could not be sent."
            )

            # Invalidate the undelivered reset token.
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE password_reset_tokens
                        SET used_at = CURRENT_TIMESTAMP
                        WHERE token_hash = %s
                          AND used_at IS NULL;
                    """, (token_hash,))

        return jsonify(generic_response), 200

    except Exception:
        app.logger.exception("Password reset request failed.")
        return jsonify(generic_response), 200



@app.post("/api/auth/validate-reset-token")
@limiter.limit("10 per minute")

def validate_reset_token():
    """Validate HOD setup, student activation and password reset links."""

    data = request.get_json(silent=True) or {}
    token = data.get("token", "")

    if not isinstance(token, str) or not token or len(token) > 200:
        return jsonify({
            "status": "error",
            "valid": False,
            "message": "This link is invalid or expired."
        }), 400

    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).digest()

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # 1. Check HOD password setup invitation.
                cur.execute("""
                    SELECT b.name
                    FROM hod_setup_tokens t
                    JOIN accounts a
                        ON a.id = t.account_id
                    JOIN hod_assignments h
                        ON h.account_id = a.id
                       AND h.branch_id = t.branch_id
                    JOIN branches b
                        ON b.id = h.branch_id
                    WHERE t.token_hash = %s
                      AND t.used_at IS NULL
                      AND t.expires_at > CURRENT_TIMESTAMP
                      AND LOWER(t.target_email) = LOWER(a.email)
                      AND a.is_active = TRUE
                      AND a.role = 'HOD'
                      AND b.is_active = TRUE
                      AND NOT EXISTS (
                          SELECT 1
                          FROM account_credentials c
                          WHERE c.account_id = a.id
                      )
                    LIMIT 1;
                """, (token_hash,))

                setup_record = cur.fetchone()

                if setup_record:
                    return jsonify({
                        "status": "ok",
                        "valid": True,
                        "purpose": "HOD_SETUP",
                        "branch_name": setup_record[0]
                    }), 200

                # 2. Check student account activation invitation.
                # IMPORTANT: This query and fetchone() must remain
                # inside the same cursor context.
                cur.execute("""
                    SELECT s.full_name
                    FROM student_activation_tokens t
                    JOIN accounts a
                        ON a.id = t.account_id
                    JOIN students s
                        ON s.account_id = a.id
                    LEFT JOIN account_credentials ac
                        ON ac.account_id = a.id
                    WHERE t.token_hash = %s
                      AND t.used_at IS NULL
                      AND t.expires_at > CURRENT_TIMESTAMP
                      AND a.role = 'STUDENT'
                      AND a.is_active = TRUE
                      AND ac.account_id IS NULL
                    LIMIT 1;
                """, (token_hash,))

                student_activation = cur.fetchone()

                if student_activation:
                    return jsonify({
                        "status": "ok",
                        "valid": True,
                        "purpose": "STUDENT_ACTIVATION",
                        "student_name": student_activation[0]
                    }), 200

                # 3. Check normal Principal, HOD and Student
                # password-reset invitations.
                cur.execute("""
                    SELECT 1
                    FROM password_reset_tokens t
                    JOIN accounts a
                        ON a.id = t.account_id
                    WHERE t.token_hash = %s
                      AND t.used_at IS NULL
                      AND t.expires_at > CURRENT_TIMESTAMP
                      AND a.is_active = TRUE
                      AND a.role IN (
                          'PRINCIPAL',
                          'HOD',
                          'STUDENT'
                      )
                      AND (
                          a.role = 'PRINCIPAL'

                          OR (
                              a.role = 'HOD'
                              AND EXISTS (
                                  SELECT 1
                                  FROM hod_assignments h
                                  JOIN branches b
                                      ON b.id = h.branch_id
                                  WHERE h.account_id = a.id
                                    AND b.is_active = TRUE
                              )
                          )

                          OR (
                              a.role = 'STUDENT'
                              AND EXISTS (
                                  SELECT 1
                                  FROM students s
                                  WHERE s.account_id = a.id
                              )
                          )
                      )
                      AND (
                          LOWER(t.target_email) = LOWER(a.email)

                          OR EXISTS (
                              SELECT 1
                              FROM account_email_addresses e
                              WHERE e.account_id = a.id
                                AND LOWER(e.email) =
                                    LOWER(t.target_email)
                                AND e.is_verified = TRUE
                                AND e.password_hash IS NOT NULL
                          )
                      )
                    LIMIT 1;
                """, (token_hash,))

                valid = cur.fetchone() is not None

        if not valid:
            return jsonify({
                "status": "error",
                "valid": False,
                "message": (
                    "This link has already been used or has expired. "
                    "Request a new link to continue."
                )
            }), 400

        return jsonify({
            "status": "ok",
            "valid": True,
            "purpose": "RESET"
        }), 200

    except Exception:
        app.logger.exception(
            "Password reset token validation failed"
        )

        return jsonify({
            "status": "error",
            "valid": False,
            "message": (
                "The link could not be checked right now. "
                "Please try again."
            )
        }), 503

@app.post("/api/auth/reset-password")
@limiter.limit("5 per minute")
def reset_password():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "")
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")

    if not all(isinstance(value, str) for value in (token, password, confirm_password)):
        return jsonify({"status": "error", "message": "Invalid request."}), 400
    if not token or len(token) > 200:
        return jsonify({"status": "error", "message": "This reset link is invalid or expired."}), 400
    if len(password) < 12 or len(password) > 128:
        return jsonify({"status": "error", "message": "Use a password with 12–128 characters."}), 400
    if password != confirm_password:
        return jsonify({"status": "error", "message": "Passwords do not match."}), 400

    token_hash = hashlib.sha256(token.encode("utf-8")).digest()
    new_password_hash = generate_password_hash(password)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # First handle the one-time HOD password-creation link.
                cur.execute("""
                    SELECT t.id, t.account_id, t.target_email, a.email, a.full_name, b.name
                    FROM hod_setup_tokens t
                    JOIN accounts a ON a.id = t.account_id
                    JOIN hod_assignments h ON h.account_id = a.id AND h.branch_id = t.branch_id
                    JOIN branches b ON b.id = h.branch_id
                    WHERE t.token_hash = %s
                      AND t.used_at IS NULL
                      AND t.expires_at > CURRENT_TIMESTAMP
                      AND LOWER(t.target_email) = LOWER(a.email)
                      AND a.is_active = TRUE
                      AND a.role = 'HOD'
                      AND b.is_active = TRUE
                    FOR UPDATE OF t, a;
                """, (token_hash,))
                setup_record = cur.fetchone()

                if setup_record:
                    setup_token_id, setup_account_id, _, _, _, setup_branch = setup_record
                    cur.execute(
                        "SELECT 1 FROM account_credentials WHERE account_id = %s FOR UPDATE;",
                        (setup_account_id,)
                    )
                    if cur.fetchone():
                        return jsonify({
                            "status": "error",
                            "message": "This HOD password has already been created. Please go to login."
                        }), 409

                    cur.execute("""
                        INSERT INTO account_credentials (
                            account_id, password_hash, password_changed_at
                        )
                        VALUES (%s, %s, CURRENT_TIMESTAMP);
                    """, (setup_account_id, new_password_hash))

                    cur.execute("""
                        UPDATE hod_setup_tokens
                        SET used_at = CURRENT_TIMESTAMP
                        WHERE account_id = %s AND used_at IS NULL;
                    """, (setup_account_id,))

                    write_audit_event(cur, "HOD_PASSWORD_CREATED", {
                        "hod_account_id": setup_account_id,
                        "branch_name": setup_branch,
                    })
                    return jsonify({
                        "status": "ok",
                        "message": "Your HOD password has been created successfully. You can now log in."
                    }), 200

                # Otherwise validate a normal password-reset token.
                cur.execute("""
                    SELECT t.id, t.account_id, t.target_email, a.email, a.role
                    FROM password_reset_tokens t
                    JOIN accounts a ON a.id = t.account_id
                    WHERE t.token_hash = %s
                      AND t.used_at IS NULL
                      AND t.expires_at > CURRENT_TIMESTAMP
                      AND a.is_active = TRUE
                      AND a.role IN ('PRINCIPAL', 'HOD', 'STUDENT')
                      AND (
                          a.role = 'PRINCIPAL'
                          OR (
                              a.role = 'HOD'
                              AND EXISTS (
                                  SELECT 1
                                  FROM hod_assignments h
                                  JOIN branches b ON b.id = h.branch_id
                                  WHERE h.account_id = a.id AND b.is_active = TRUE
                              )
                          )
                          OR (
                              a.role = 'STUDENT'
                              AND EXISTS (
                                  SELECT 1
                                  FROM students s
                                  WHERE s.account_id = a.id
                              )
                          )
                      )
                    FOR UPDATE OF t, a;
                """, (token_hash,))
                record = cur.fetchone()

                if not record or not record[2]:
                    return jsonify({
                        "status": "error",
                        "message": "This reset link is invalid or expired."
                    }), 400

                token_id, account_id, target_email, primary_email, role = record
                is_primary = target_email.strip().lower() == primary_email.strip().lower()

                if role == "PRINCIPAL" and is_primary:
                    cur.execute("""
                        SELECT password_hash
                        FROM account_email_addresses
                        WHERE account_id = %s AND is_verified = TRUE;
                    """, (account_id,))
                    additional = cur.fetchone()
                    if additional and additional[0] and check_password_hash(additional[0], password):
                        return jsonify({
                            "status": "error",
                            "message": "Choose a password different from the additional email password."
                        }), 400

                if is_primary:
                    if role == "STUDENT":
                        # Students may be creating their first password.
                        cur.execute("""
                            INSERT INTO account_credentials (
                                account_id, password_hash, password_changed_at
                            )
                            VALUES (%s, %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (account_id)
                            DO UPDATE SET
                                password_hash = EXCLUDED.password_hash,
                                password_changed_at = CURRENT_TIMESTAMP;
                        """, (account_id, new_password_hash))
                    else:
                        cur.execute("""
                            UPDATE account_credentials
                            SET password_hash = %s,
                                password_changed_at = CURRENT_TIMESTAMP
                            WHERE account_id = %s;
                        """, (new_password_hash, account_id))
                        if cur.rowcount != 1:
                            return jsonify({
                                "status": "error",
                                "message": "This reset link is invalid or expired."
                            }), 400
                else:
                    # A non-primary address must be verified and have its own password record.
                    cur.execute("""
                        SELECT id, password_hash
                        FROM account_email_addresses
                        WHERE account_id = %s
                          AND LOWER(email) = %s
                          AND is_verified = TRUE
                        FOR UPDATE;
                    """, (account_id, target_email.lower()))
                    extra = cur.fetchone()

                    if not extra or not extra[1]:
                        return jsonify({
                            "status": "error",
                            "message": "This reset link is invalid or expired."
                        }), 400

                    cur.execute("""
                        SELECT password_hash
                        FROM account_credentials
                        WHERE account_id = %s;
                    """, (account_id,))
                    primary = cur.fetchone()
                    if primary and check_password_hash(primary[0], password):
                        return jsonify({
                            "status": "error",
                            "message": "Choose a password different from the primary email password."
                        }), 400

                    cur.execute("""
                        UPDATE account_email_addresses
                        SET password_hash = %s
                        WHERE id = %s AND account_id = %s;
                    """, (new_password_hash, extra[0], account_id))
                    if cur.rowcount != 1:
                        return jsonify({
                            "status": "error",
                            "message": "This reset link is invalid or expired."
                        }), 400

                cur.execute("""
                    UPDATE password_reset_tokens
                    SET used_at = CURRENT_TIMESTAMP
                    WHERE account_id = %s
                      AND LOWER(target_email) = %s
                      AND used_at IS NULL;
                """, (account_id, target_email.lower()))

        return jsonify({
            "status": "ok",
            "message": "Password reset successful. You can now log in."
        }), 200

    except Exception:
        app.logger.exception("Password reset failed")
        return jsonify({
            "status": "error",
            "message": "Password reset service is temporarily unavailable."
        }), 503
# ==========================================
# HOD: CREATE CR / FR ELECTION
# ==========================================

@app.post("/api/hod/elections")
@limiter.limit("10 per minute")
def create_hod_election():

    auth_error = require_hod()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}

    title = data.get("title")
    description = data.get("description", "")
    election_type = data.get("election_type", "")
    admission_year = data.get("admission_year")
    academic_year = data.get("academic_year")
    semester = data.get("semester")
    duration_minutes = data.get("duration_minutes")

    if not isinstance(title, str) or not isinstance(description, str):
        return jsonify({
            "status": "error",
            "message": "Enter a valid election title."
        }), 400

    title = title.strip()
    description = description.strip()
    election_type = (
        election_type.upper()
        if isinstance(election_type, str)
        else ""
    )

    if not title or len(title) > 200:
        return jsonify({
            "status": "error",
            "message": "Election title must contain 1–200 characters."
        }), 400

    if len(description) > 5000:
        return jsonify({
            "status": "error",
            "message": "Election description cannot exceed 5000 characters.",
        }), 400

    if election_type not in ("CR", "FR"):
        return jsonify({
            "status": "error",
            "message": "Only CR and FR elections are allowed."
        }), 400

    try:
        admission_year = int(admission_year)
        academic_year = int(academic_year)
        semester = int(semester)
        duration_minutes = int(duration_minutes)
    except (TypeError, ValueError):
        return jsonify({
            "status": "error",
            "message": "Select a valid admission year, academic year, semester and duration."
        }), 400

    if not valid_admission_year(admission_year):
        return jsonify({
            "status": "error",
            "message": "Invalid admission year."
        }), 400

    if not valid_admission_year(academic_year):
        return jsonify({
            "status": "error",
            "message": "Invalid academic year."
        }), 400

    if not 1 <= semester <= 12:
        return jsonify({
            "status": "error",
            "message": "Semester must be between 1 and 12."
        }), 400

    if not 1 <= duration_minutes <= 10080:
        return jsonify({
            "status": "error",
            "message": "Election duration must be between 1 and 10080 minutes."
        }), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Verify the HOD's assigned branch.
                cur.execute("""
                    SELECT h.branch_id, b.name
                    FROM hod_assignments h
                    JOIN branches b ON b.id = h.branch_id
                    JOIN accounts a ON a.id = h.account_id
                    WHERE h.account_id = %s
                      AND a.is_active = TRUE
                      AND b.is_active = TRUE;
                """, (session["account_id"],))

                branch = cur.fetchone()

                if not branch:
                    return jsonify({
                        "status": "error",
                        "message": "No active department assignment found."
                    }), 403

                branch_id, branch_name = branch

                # Check the selected class has active students.
                cur.execute("""
                    SELECT COUNT(*)
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    WHERE s.branch_id = %s
                      AND s.admission_year = %s
                      AND s.academic_year = %s
                      AND s.semester = %s
                      AND a.role = 'STUDENT'
                      AND a.is_active = TRUE;
                """, (branch_id, admission_year, academic_year, semester))

                eligible_count = cur.fetchone()[0]

                if eligible_count == 0:
                    return jsonify({
                        "status": "error",
                        "message": "No active students found in this class."
                    }), 400

                # Prevent duplicate unfinished elections
                # for the same class and representative type.
                cur.execute("""
                    SELECT id
                    FROM elections
                    WHERE branch_id = %s
                      AND admission_year = %s
                      AND academic_year = %s
                      AND semester = %s
                      AND election_type = %s
                      AND status IN ('DRAFT', 'SCHEDULED', 'OPEN')
                    LIMIT 1;
                """, (
                    branch_id,
                    admission_year,
                    academic_year,
                    semester,
                    election_type
                ))

                if cur.fetchone():
                    return jsonify({
                        "status": "error",
                        "message": (
                            f"An unfinished {election_type} election "
                            "already exists for this class."
                        )
                    }), 409

                # Create election in DRAFT status.
                cur.execute("""
                    INSERT INTO elections (
                        title,
                        description,
                        election_type,
                        branch_id,
                        admission_year,
                        academic_year,
                        semester,
                        duration_minutes,
                        opens_at,
                        closes_at,
                        created_by
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP + (
                            %s * INTERVAL '1 minute'
                        ),
                        %s
                    )
                    RETURNING id;
                """, (
                    title,
                    description,
                    election_type,
                    branch_id,
                    admission_year,
                    academic_year,
                    semester,
                    duration_minutes,
                    duration_minutes,
                    session["account_id"]
                ))

                election_id = cur.fetchone()[0]

                # Snapshot eligible active voters for this class.
                cur.execute("""
                    INSERT INTO voter_eligibility (
                        election_id,
                        student_id
                    )
                    SELECT %s, s.id
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    WHERE s.branch_id = %s
                      AND s.admission_year = %s
                      AND s.academic_year = %s
                      AND s.semester = %s
                      AND a.role = 'STUDENT'
                      AND a.is_active = TRUE;
                """, (
                    election_id,
                    branch_id,
                    admission_year,
                    academic_year,
                    semester
                ))

                eligible_voters = cur.rowcount

                write_audit_event(
                    cur,
                    "HOD_ELECTION_CREATED",
                    {
                        "election_id": election_id,
                        "election_type": election_type,
                        "description": description,
                        "branch_id": branch_id,
                        "admission_year": admission_year,
                        "academic_year": academic_year,
                        "semester": semester,
                        "duration_minutes": duration_minutes,
                        "eligible_voters": eligible_voters
                    },
                    election_id
                )

        return jsonify({
            "status": "ok",
            "message": f"{election_type} election created successfully.",
            "election": {
                "id": election_id,
                "title": title,
                "description": description,
                "type": election_type,
                "branch": branch_name,
                "admission_year": admission_year,
                "academic_year": academic_year,
                "semester": semester,
                "duration_minutes": duration_minutes,
                "eligible_voters": eligible_voters,
                "status": "DRAFT"
            }
        }), 201

    except Exception:
        app.logger.exception("HOD election creation failed")
        return jsonify({
            "status": "error",
            "message": "Could not create the election."
        }), 503    
# ==========================================
# HOD: LIST CR / FR ELECTIONS
# ==========================================

@app.patch("/api/hod/elections/<int:election_id>")
@limiter.limit("20 per minute")
def update_hod_election(election_id):
    """Allow the owning HOD to edit a draft election only."""
    auth_error = require_hod()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    allowed_fields = {"title", "description", "duration_minutes"}
    if not data or not set(data).issubset(allowed_fields):
        return jsonify({
            "status": "error",
            "message": "Provide title, description, and/or duration_minutes only.",
        }), 400

    updates = []
    values = []
    if "title" in data:
        if not isinstance(data["title"], str) or not data["title"].strip() or len(data["title"].strip()) > 200:
            return jsonify({"status": "error", "message": "Election title must contain 1–200 characters."}), 400
        updates.append("title = %s")
        values.append(data["title"].strip())
    if "description" in data:
        if not isinstance(data["description"], str) or len(data["description"].strip()) > 5000:
            return jsonify({"status": "error", "message": "Election description cannot exceed 5000 characters."}), 400
        updates.append("description = %s")
        values.append(data["description"].strip())
    if "duration_minutes" in data:
        if type(data["duration_minutes"]) is not int or not 1 <= data["duration_minutes"] <= 10080:
            return jsonify({"status": "error", "message": "Duration must be between 1 and 10080 minutes."}), 400
        updates.append("duration_minutes = %s")
        values.append(data["duration_minutes"])

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT e.title, e.description, e.duration_minutes, e.status
                    FROM elections e
                    JOIN hod_assignments h ON h.branch_id = e.branch_id
                    JOIN branches b ON b.id = e.branch_id
                    WHERE e.id = %s AND h.account_id = %s AND b.is_active = TRUE
                    FOR UPDATE OF e;
                """, (election_id, session["account_id"]))
                current = cur.fetchone()
                if not current:
                    return jsonify({"status": "error", "message": "Election not found in your department."}), 404
                if current[3] != "DRAFT":
                    return jsonify({"status": "error", "message": "Only draft elections can be edited."}), 409

                values.append(election_id)
                cur.execute(f"""
                    UPDATE elections
                    SET {', '.join(updates)}
                    WHERE id = %s
                    RETURNING id, title, description, duration_minutes, status;
                """, tuple(values))
                updated = cur.fetchone()
                write_audit_event(cur, "HOD_ELECTION_UPDATED", {
                    "election_id": election_id,
                    "updated_by": session["account_id"],
                    "before": {
                        "title": current[0], "description": current[1] or "",
                        "duration_minutes": current[2],
                    },
                    "after": {
                        "title": updated[1], "description": updated[2] or "",
                        "duration_minutes": updated[3],
                    },
                }, election_id)
        return jsonify({
            "status": "ok", "message": "Draft election updated successfully.",
            "election": {
                "id": updated[0], "title": updated[1],
                "description": updated[2] or "", "duration_minutes": updated[3],
                "status": updated[4],
            },
        }), 200
    except Exception:
        app.logger.exception("HOD election update failed")
        return jsonify({"status": "error", "message": "Could not update the election."}), 503


@app.get("/api/hod/elections")
@limiter.limit("60 per minute")
def get_hod_elections():

    auth_error = require_hod()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Get the logged-in HOD's assigned branch.
                cur.execute("""
                    SELECT h.branch_id, b.name
                    FROM hod_assignments h
                    JOIN branches b ON b.id = h.branch_id
                    WHERE h.account_id = %s
                      AND b.is_active = TRUE;
                """, (session["account_id"],))

                branch = cur.fetchone()

                if not branch:
                    return jsonify({
                        "status": "error",
                        "message": "No active department assignment found."
                    }), 403

                branch_id, branch_name = branch
                # Automatically close expired CR/FR elections.
                cur.execute("""
    UPDATE elections
    SET status = 'CLOSED'
    WHERE branch_id = %s
      AND election_type IN ('CR', 'FR')
      AND status = 'OPEN'
      AND closes_at <= CURRENT_TIMESTAMP
    RETURNING id, title;
""", (branch_id,))

                expired_elections = cur.fetchall()

                for expired_id, expired_title in expired_elections:
                    write_audit_event(
                                   cur,
                                  "HOD_ELECTION_AUTO_CLOSED",
        {
            "election_id": expired_id,
            "title": expired_title,
            "close_reason": "TIME_EXPIRED"
        },
        expired_id
    )
                    write_election_result_commitment(cur, expired_id)

                # Retrieve CR/FR elections for this branch.
                cur.execute("""
                    SELECT
                        e.id,
                        e.title,
                        e.description,
                        e.election_type,
                        e.admission_year,
                        e.academic_year,
                        e.semester,
                        e.duration_minutes,
                        e.opens_at,
                        e.closes_at,
                        e.status,

                        (
                            SELECT COUNT(*)
                            FROM voter_eligibility ve
                            WHERE ve.election_id = e.id
                        ) AS eligible_voters,

                        (
                            SELECT COUNT(*)
                            FROM candidates c
                            WHERE c.election_id = e.id
                        ) AS total_candidates,

                        (
                            SELECT COUNT(*)
                            FROM candidates c
                            WHERE c.election_id = e.id
                              AND c.is_approved = TRUE
                        ) AS approved_candidates

                    FROM elections e
                    WHERE e.branch_id = %s
                      AND e.election_type IN ('CR', 'FR')
                    ORDER BY e.created_at DESC, e.id DESC;
                """, (branch_id,))

                rows = cur.fetchall()

        elections = [
            {
                "id": row[0],
                "title": row[1],
                "description": row[2] or "",
                "election_type": row[3],
                "admission_year": row[4],
                "academic_year": row[5],
                "semester": row[6],
                "duration_minutes": row[7],
                "opens_at": row[8],
                "closes_at": row[9],
                "status": row[10],
                "eligible_voters": row[11],
                "total_candidates": row[12],
                "approved_candidates": row[13]
            }
            for row in rows
        ]

        return jsonify({
            "status": "ok",
            "branch": branch_name,
            "elections": elections
        }), 200

    except Exception:
        app.logger.exception("HOD election retrieval failed")
        return jsonify({
            "status": "error",
            "message": "Could not retrieve elections."
        }), 503    


# ==========================================
# HOD: REGISTER ELECTION CANDIDATE
# ==========================================

@app.post("/api/hod/elections/<int:election_id>/candidates")
@limiter.limit("20 per minute")
def add_hod_election_candidate(election_id):

    auth_error = require_hod()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}

    usn = data.get("usn", "")
    manifesto = data.get("manifesto", "")
    symbol_key = data.get("symbol_key")

    if not isinstance(usn, str) or not isinstance(manifesto, str):
        return jsonify({
            "status": "error",
            "message": "Invalid candidate details."
        }), 400

    usn = usn.strip().upper()
    manifesto = manifesto.strip()

    if not re.fullmatch(r"[0-9]UB[0-9]{2}[A-Z]{2}[0-9]{3}", usn):
        return jsonify({
            "status": "error",
            "message": "Enter a valid 10-character USN."
        }), 400

    if len(manifesto) > 5000:
        return jsonify({
            "status": "error",
            "message": "Manifesto cannot exceed 5000 characters."
        }), 400
    if not valid_candidate_symbol(symbol_key):
        return jsonify({
            "status": "error",
            "message": "Choose an approved election symbol."
        }), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Verify election belongs to this HOD's branch.
                cur.execute("""
                    SELECT
                        e.branch_id,
                        e.admission_year,
                        e.academic_year,
                        e.semester,
                        e.election_type,
                        e.status
                    FROM elections e
                    JOIN hod_assignments h
                        ON h.branch_id = e.branch_id
                    JOIN branches b
                        ON b.id = e.branch_id
                    WHERE e.id = %s
                      AND h.account_id = %s
                      AND b.is_active = TRUE;
                """, (
                    election_id,
                    session["account_id"]
                ))

                election = cur.fetchone()

                if not election:
                    return jsonify({
                        "status": "error",
                        "message": "Election not found in your department."
                    }), 404

                branch_id, admission_year, academic_year, semester, election_type, status = election

                if status not in ("DRAFT", "SCHEDULED"):
                    return jsonify({
                        "status": "error",
                        "message": "Candidates cannot be added to this election now."
                    }), 409

                # Find an active student from the exact class.
                cur.execute("""
                    SELECT s.id, s.full_name
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    WHERE UPPER(s.usn) = %s
                      AND s.branch_id = %s
                      AND s.admission_year = %s
                      AND s.academic_year = %s
                      AND s.semester = %s
                      AND a.role = 'STUDENT'
                      AND a.is_active = TRUE;
                """, (
                    usn,
                    branch_id,
                    admission_year,
                    academic_year,
                    semester
                ))

                student = cur.fetchone()

                if not student:
                    return jsonify({
                        "status": "error",
                        "message": (
                            "Active student not found in this election's "
                            "admission year and semester."
                        )
                    }), 404

                student_id, student_name = student

                cur.execute("""
                    SELECT 1 FROM candidates
                    WHERE election_id = %s AND symbol_key = %s;
                """, (election_id, symbol_key))
                if cur.fetchone():
                    return jsonify({
                        "status": "error",
                        "message": "That symbol is already assigned in this election."
                    }), 409

                # Prevent duplicate candidate registration.
                cur.execute("""
                    INSERT INTO candidates (
                        election_id,
                        student_id,
                        manifesto,
                        symbol_key
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (election_id, student_id) DO NOTHING
                    RETURNING id;
                """, (
                    election_id,
                    student_id,
                    manifesto or None,
                    symbol_key,
                ))

                candidate_row = cur.fetchone()

                if not candidate_row:
                    return jsonify({
                        "status": "error",
                        "message": "This student is already registered as a candidate."
                    }), 409

                candidate_id = candidate_row[0]

                write_audit_event(
                    cur,
                    "HOD_CANDIDATE_REGISTERED",
                    {
                        "candidate_id": candidate_id,
                        "student_id": student_id,
                        "usn": usn,
                        "symbol_key": symbol_key,
                        "election_type": election_type,
                        "admission_year": admission_year,
                        "academic_year": academic_year,
                        "semester": semester
                    },
                    election_id
                )

        return jsonify({
            "status": "ok",
            "message": "Candidate registered successfully. Approval is pending.",
            "candidate": {
                "id": candidate_id,
                "student_id": student_id,
                "name": student_name,
                "usn": usn,
                "manifesto": manifesto,
                "symbol_key": symbol_key,
                "symbol": candidate_symbol_payload(symbol_key),
                "is_approved": False
            }
        }), 201

    except Exception:
        app.logger.exception("HOD candidate registration failed")
        return jsonify({
            "status": "error",
            "message": "Could not register the candidate."
        }), 503
# ==========================================
# HOD: APPROVE ELECTION CANDIDATE
# ==========================================

@app.post("/api/hod/elections/<int:election_id>/candidates/<int:candidate_id>/approve")
@limiter.limit("30 per minute")
def approve_hod_election_candidate(election_id, candidate_id):

    auth_error = require_hod()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Verify election, candidate and HOD branch ownership.
                cur.execute("""
                    SELECT
                        e.status,
                        c.student_id,
                        c.is_approved,
                        s.full_name,
                        s.usn
                    FROM elections e
                    JOIN hod_assignments h
                        ON h.branch_id = e.branch_id
                    JOIN branches b
                        ON b.id = e.branch_id
                    JOIN candidates c
                        ON c.election_id = e.id
                    JOIN students s
                        ON s.id = c.student_id
                    WHERE e.id = %s
                      AND c.id = %s
                      AND h.account_id = %s
                      AND b.is_active = TRUE
                    FOR UPDATE OF e, c;
                """, (
                    election_id,
                    candidate_id,
                    session["account_id"]
                ))

                candidate = cur.fetchone()

                if not candidate:
                    return jsonify({
                        "status": "error",
                        "message": "Candidate not found in your department."
                    }), 404

                status, student_id, is_approved, name, usn = candidate

                if status not in ("DRAFT", "SCHEDULED"):
                    return jsonify({
                        "status": "error",
                        "message": "Candidates cannot be approved after voting starts."
                    }), 409

                if is_approved:
                    return jsonify({
                        "status": "ok",
                        "message": "This candidate is already approved."
                    }), 200

                cur.execute("""
                    UPDATE candidates
                    SET is_approved = TRUE,
                        review_status = 'APPROVED',
                        reviewed_at = CURRENT_TIMESTAMP,
                        reviewed_by = %s
                    WHERE id = %s
                      AND election_id = %s
                    RETURNING id;
                """, (session["account_id"], candidate_id, election_id))

                if not cur.fetchone():
                    return jsonify({
                        "status": "error",
                        "message": "Candidate approval failed."
                    }), 409

                write_audit_event(
                    cur,
                    "HOD_CANDIDATE_APPROVED",
                    {
                        "candidate_id": candidate_id,
                        "student_id": student_id,
                        "usn": usn,
                        "approved_by": session["account_id"]
                    },
                    election_id
                )

        return jsonify({
            "status": "ok",
            "message": "Candidate approved successfully.",
            "candidate": {
                "id": candidate_id,
                "name": name,
                "usn": usn,
                "is_approved": True
            }
        }), 200

    except Exception:
        app.logger.exception("HOD candidate approval failed")
        return jsonify({
            "status": "error",
            "message": "Could not approve the candidate."
        }), 503
# ==========================================
# HOD: VIEW ELECTION CANDIDATES
# ==========================================

@app.get("/api/hod/elections/<int:election_id>/candidates")
@limiter.limit("60 per minute")
def get_hod_election_candidates(election_id):

    auth_error = require_hod()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Verify election belongs to the HOD's branch.
                cur.execute("""
                    SELECT
                        e.id,
                        e.title,
                        e.election_type,
                        e.admission_year,
                        e.semester,
                        e.status,
                        b.name
                    FROM elections e
                    JOIN hod_assignments h
                        ON h.branch_id = e.branch_id
                    JOIN branches b
                        ON b.id = e.branch_id
                    WHERE e.id = %s
                      AND h.account_id = %s
                      AND b.is_active = TRUE;
                """, (
                    election_id,
                    session["account_id"]
                ))

                election = cur.fetchone()

                if not election:
                    return jsonify({
                        "status": "error",
                        "message": "Election not found in your department."
                    }), 404

                cur.execute("""
                    SELECT
                        c.id,
                        c.student_id,
                        s.full_name,
                        s.usn,
                        c.manifesto,
                        c.symbol_key,
                        c.is_approved,
                        c.review_status,
                        c.created_at
                    FROM candidates c
                    JOIN students s
                        ON s.id = c.student_id
                    WHERE c.election_id = %s
                    ORDER BY c.created_at ASC, c.id ASC;
                """, (election_id,))

                rows = cur.fetchall()

        candidates = [
            {
                "id": row[0],
                "student_id": row[1],
                "name": row[2],
                "usn": row[3],
                "manifesto": row[4] or "",
                "symbol_key": row[5],
                "symbol": candidate_symbol_payload(row[5]),
                "is_approved": row[6],
                "review_status": row[7],
                "created_at": row[8].isoformat() if row[8] else None
            }
            for row in rows
        ]

        return jsonify({
            "status": "ok",
            "election": {
                "id": election[0],
                "title": election[1],
                "election_type": election[2],
                "admission_year": election[3],
                "semester": election[4],
                "status": election[5],
                "branch": election[6]
            },
            "total_candidates": len(candidates),
            "approved_candidates": sum(
                1 for candidate in candidates
                if candidate["is_approved"]
            ),
            "pending_candidates": sum(
                1 for candidate in candidates
                if candidate["review_status"] == "PENDING"
            ),
            "rejected_candidates": sum(
                1 for candidate in candidates
                if candidate["review_status"] == "REJECTED"
            ),
            "candidates": candidates
        }), 200

    except Exception:
        app.logger.exception("HOD candidate retrieval failed")
        return jsonify({
            "status": "error",
            "message": "Could not retrieve election candidates."
        }), 503    

# ==========================================
# HOD: START CR / FR ELECTION
# ==========================================

@app.post("/api/hod/elections/<int:election_id>/start")
@limiter.limit("10 per minute")
def start_hod_election(election_id):

    auth_error = require_hod()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Verify ownership and lock the election.
                cur.execute("""
                    SELECT
                        e.id,
                        e.title,
                        e.duration_minutes,
                        e.status
                    FROM elections e
                    JOIN hod_assignments h
                        ON h.branch_id = e.branch_id
                    JOIN branches b
                        ON b.id = e.branch_id
                    WHERE e.id = %s
                      AND h.account_id = %s
                      AND b.is_active = TRUE
                    FOR UPDATE OF e;
                """, (
                    election_id,
                    session["account_id"]
                ))

                election = cur.fetchone()

                if not election:
                    return jsonify({
                        "status": "error",
                        "message": "Election not found in your department."
                    }), 404

                election_id_db, title, duration, status = election

                if status != "DRAFT":
                    return jsonify({
                        "status": "error",
                        "message": "Only draft elections can be started."
                    }), 409

                if not duration or not 1 <= duration <= 10080:
                    return jsonify({
                        "status": "error",
                        "message": "Invalid election duration."
                    }), 400

                # Require at least two approved candidates.
                cur.execute("""
                    SELECT COUNT(*)
                    FROM candidates
                    WHERE election_id = %s
                      AND is_approved = TRUE;
                """, (election_id,))

                approved_count = cur.fetchone()[0]

                if approved_count < 2:
                    return jsonify({
                        "status": "error",
                        "message": (
                            "At least two approved candidates "
                            "are required to start the election."
                        )
                    }), 409

                # Start the timer only when the HOD starts voting.
                cur.execute("""
                    WITH start_time AS (
                        SELECT clock_timestamp() AS started_at
                    )
                    UPDATE elections e
                    SET
                        opens_at = start_time.started_at,
                        closes_at = start_time.started_at
                            + (e.duration_minutes * INTERVAL '1 minute'),
                        status = 'OPEN'
                    FROM start_time
                    WHERE e.id = %s
                    RETURNING e.opens_at, e.closes_at;
                """, (election_id,))

                timing = cur.fetchone()
                opens_at, closes_at = timing

                write_audit_event(
                    cur,
                    "HOD_ELECTION_STARTED",
                    {
                        "election_id": election_id,
                        "title": title,
                        "approved_candidates": approved_count,
                        "duration_minutes": duration,
                        "started_by": session["account_id"]
                    },
                    election_id
                )

        return jsonify({
            "status": "ok",
            "message": "Election started successfully.",
            "election": {
                "id": election_id,
                "title": title,
                "status": "OPEN",
                "opens_at": opens_at.isoformat(),
                "closes_at": closes_at.isoformat(),
                "duration_minutes": duration,
                "approved_candidates": approved_count
            }
        }), 200

    except Exception:
        app.logger.exception("HOD election start failed")
        return jsonify({
            "status": "error",
            "message": "Could not start the election."
        }), 503 
# ==========================================
# HOD: CLOSE CR / FR ELECTION
# ==========================================

@app.post("/api/hod/elections/<int:election_id>/close")
@limiter.limit("10 per minute")
def close_hod_election(election_id):

    auth_error = require_hod()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Verify election ownership and lock the record.
                cur.execute("""
                    SELECT e.id, e.title, e.status
                    FROM elections e
                    JOIN hod_assignments h
                        ON h.branch_id = e.branch_id
                    JOIN branches b
                        ON b.id = e.branch_id
                    WHERE e.id = %s
                      AND h.account_id = %s
                      AND b.is_active = TRUE
                    FOR UPDATE OF e;
                """, (
                    election_id,
                    session["account_id"]
                ))

                election = cur.fetchone()

                if not election:
                    return jsonify({
                        "status": "error",
                        "message": "Election not found in your department."
                    }), 404

                election_id_db, title, status = election

                if status == "CLOSED":
                    return jsonify({
                        "status": "ok",
                        "message": "This election is already closed.",
                        "status": "CLOSED"
                    }), 200

                if status != "OPEN":
                    return jsonify({
                        "status": "error",
                        "message": "Only open elections can be closed."
                    }), 409

                cur.execute("""
                    UPDATE elections
                    SET status = 'CLOSED',
                        closes_at = clock_timestamp()
                    WHERE id = %s
                    RETURNING closes_at;
                """, (election_id,))

                closes_at = cur.fetchone()[0]

                write_audit_event(
                    cur,
                    "HOD_ELECTION_CLOSED",
                    {
                        "election_id": election_id,
                        "title": title,
                        "closed_by": session["account_id"],
                        "close_reason": "HOD_MANUAL"
                    },
                    election_id
                )
                write_election_result_commitment(cur, election_id)

        return jsonify({
            "status": "ok",
            "message": "Election closed successfully.",
            "election": {
                "id": election_id,
                "title": title,
                "status": "CLOSED",
                "closes_at": closes_at.isoformat()
            }
        }), 200

    except Exception:
        app.logger.exception("HOD election closure failed")
        return jsonify({
            "status": "error",
            "message": "Could not close the election."
        }), 503   

# ==========================================
# HOD: RESEND STUDENT ACTIVATION INVITATION
# ==========================================

@app.post("/api/hod/students/<int:student_id>/resend-activation")
@limiter.limit("10 per minute")
def resend_student_activation(student_id):

    auth_error = require_hod()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Verify that the student belongs to this HOD's branch.
                # Only accounts without password credentials can be invited.
                cur.execute("""
                    SELECT
                        a.id,
                        a.email,
                        a.full_name,
                        s.usn
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    JOIN hod_assignments h
                        ON h.branch_id = s.branch_id
                    JOIN branches b
                        ON b.id = h.branch_id
                    LEFT JOIN account_credentials ac
                        ON ac.account_id = a.id
                    WHERE s.id = %s
                      AND h.account_id = %s
                      AND b.is_active = TRUE
                      AND a.role = 'STUDENT'
                      AND a.is_active = TRUE
                      AND ac.account_id IS NULL
                    FOR UPDATE OF a;
                """, (
                    student_id,
                    session["account_id"]
                ))

                student = cur.fetchone()

                if not student:
                    return jsonify({
                        "status": "error",
                        "message": (
                            "Student not found, already activated, "
                            "or not assigned to your department."
                        )
                    }), 404

                account_id, email, full_name, usn = student

                # Queue a new delivery. The worker invalidates an older
                # invitation only when it has claimed this new send job.
                activation_job_id = queue_student_activation_email(
                    cur,
                    account_id,
                    reset_attempts=True,
                )

                write_audit_event(
                    cur,
                    "STUDENT_ACTIVATION_INVITATION_RESENT",
                    {
                        "account_id": account_id,
                        "student_id": student_id,
                        "usn": usn,
                        "resent_by": session["account_id"],
                        "activation_email_job_id": activation_job_id,
                    }
                )

        return jsonify({
            "status": "ok",
            "message": "Student activation invitation queued for delivery.",
            "activation_email_queued": True,
        }), 200

    except Exception:
        app.logger.exception(
            "Student activation invitation resend failed."
        )

        return jsonify({
            "status": "error",
            "message": "Could not resend the activation invitation."
        }), 503
        
        
@app.post("/api/hod/students/bulk-resend-activation")
@limiter.limit("10 per minute")
def bulk_resend_student_activation():
    """Queue activation-invitation retries for selected, unactivated students."""
    auth_error = require_hod()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    student_ids = data.get("student_ids")
    if (
        not isinstance(student_ids, list)
        or not student_ids
        or len(student_ids) > 500
        or any(type(student_id) is not int or student_id <= 0 for student_id in student_ids)
        or len(set(student_ids)) != len(student_ids)
    ):
        return jsonify({
            "status": "error",
            "message": "Select between 1 and 500 unique student records.",
        }), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT s.id, s.account_id, s.usn
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    JOIN hod_assignments h ON h.branch_id = s.branch_id
                    JOIN branches b ON b.id = h.branch_id
                    LEFT JOIN account_credentials c ON c.account_id = a.id
                    WHERE s.id = ANY(%s)
                      AND h.account_id = %s
                      AND a.role = 'STUDENT'
                      AND a.is_active = TRUE
                      AND b.is_active = TRUE
                      AND c.account_id IS NULL
                    FOR UPDATE OF s, a;
                """, (student_ids, session["account_id"]))
                eligible_students = cur.fetchall()
                eligible_ids = {row[0] for row in eligible_students}

                queued = []
                for selected_student_id, account_id, usn in eligible_students:
                    job_id = queue_student_activation_email(
                        cur,
                        account_id,
                        reset_attempts=True,
                    )
                    queued.append(selected_student_id)
                    write_audit_event(cur, "STUDENT_ACTIVATION_INVITATION_QUEUED", {
                        "student_id": selected_student_id,
                        "account_id": account_id,
                        "usn": usn,
                        "activation_email_job_id": job_id,
                        "queued_by": session["account_id"],
                    })

        return jsonify({
            "status": "ok",
            "message": f"{len(queued)} activation invitation(s) queued for delivery.",
            "queued_student_ids": queued,
            "not_queued_student_ids": [
                student_id for student_id in student_ids
                if student_id not in eligible_ids
            ],
        }), 200
    except Exception:
        app.logger.exception("Bulk activation invitation queueing failed")
        return jsonify({
            "status": "error",
            "message": "Could not queue activation invitations.",
        }), 503


@app.get("/api/hod/students")
@limiter.limit("60 per minute")
def get_hod_students():
    auth_error = require_hod()
    if auth_error:
        return auth_error

    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 25, type=int)
        search = request.args.get("search", "").strip()
        semester = request.args.get("semester", type=int)
        admission_year = request.args.get("admission_year", type=int)
        academic_year_arg = request.args.get("academic_year")
        academic_year_is_null = academic_year_arg == "null"
        academic_year = None
        if academic_year_arg not in (None, "", "null"):
            try:
                academic_year = int(academic_year_arg)
            except (TypeError, ValueError):
                return jsonify({
                    "status": "error",
                    "message": "Invalid academic year."
                }), 400
        

        if page < 1 or not 1 <= per_page <= 100:
            return jsonify({
                "status": "error",
                "message": "Invalid pagination values."
            }), 400

        if semester is not None and not 1 <= semester <= 12:
            return jsonify({
                "status": "error",
                "message": "Invalid semester."
            }), 400
        if admission_year is not None and not valid_admission_year(admission_year):
            return jsonify({
        "status": "error",
        "message": "Invalid admission year."
    }), 400
        if academic_year is not None and not valid_admission_year(academic_year):
            return jsonify({
                "status": "error",
                "message": "Invalid academic year."
            }), 400

        if len(search) > 150:
            return jsonify({
                "status": "error",
                "message": "Search text is too long."
            }), 400

        account_id = session["account_id"]
        offset = (page - 1) * per_page

        with get_db_connection() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    SELECT b.id, b.name, b.code
                    FROM hod_assignments h
                    JOIN branches b ON b.id = h.branch_id
                    WHERE h.account_id = %s
                      AND b.is_active = TRUE;
                """, (account_id,))

                branch = cur.fetchone()

                if not branch:
                    return jsonify({
                        "status": "error",
                        "message": "No active branch is assigned to this HOD."
                    }), 403

                branch_id, branch_name, branch_code = branch

                filters = [
                    "s.branch_id = %s",
                    "a.role = 'STUDENT'"
                ]

                params = [branch_id]

                if search:
                    filters.append("""
                        (
                            s.full_name ILIKE %s
                            OR s.usn ILIKE %s
                            OR a.email ILIKE %s
                        )
                    """)

                    term = f"%{search}%"
                    params.extend([term, term, term])

                if semester is not None:
                    filters.append("s.semester = %s")
                    params.append(semester)

                if admission_year is not None:
                    filters.append("s.admission_year = %s")
                    params.append(admission_year)    

                if academic_year_is_null:
                    filters.append("s.academic_year IS NULL")
                elif academic_year is not None:
                    filters.append("s.academic_year = %s")
                    params.append(academic_year)

                where_clause = " AND ".join(filters)

                cur.execute(f"""
                    SELECT COUNT(*)
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    WHERE {where_clause};
                """, tuple(params))

                total_students = cur.fetchone()[0]

                cur.execute(f"""
                    SELECT
                        s.id,
                        s.full_name,
                        s.usn,
                        a.email,
                        s.semester,
                        s.admission_year,
                        s.academic_year,
                        s.expected_graduation_year,
                        a.is_active,
                        s.is_cr,
                        s.is_fr,
                        c.account_id IS NOT NULL AS is_activated,
                        CASE
                            WHEN c.account_id IS NOT NULL THEN 'ACTIVATED'
                            ELSE COALESCE(j.status, 'NOT_QUEUED')
                        END AS activation_email_status,
                        j.failure_kind,
                        j.next_attempt_at
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    LEFT JOIN student_activation_email_jobs j
                        ON j.account_id = a.id
                    LEFT JOIN account_credentials c
                        ON c.account_id = a.id
                    WHERE {where_clause}
                    ORDER BY s.id DESC
                    LIMIT %s OFFSET %s;
                """, tuple(params + [per_page, offset]))

                rows = cur.fetchall()

        students = [
            {
                "id": row[0],
                "name": row[1],
                "usn": row[2],
                "email": row[3],
                "semester": row[4],
                "admission_year": row[5],
                "academic_year": row[6],
                "expected_graduation_year": row[7],
                "is_active": row[8],
                "is_cr": row[9],
                "is_fr": row[10],
                "is_activated": row[11],
                "activation_email_status": row[12],
                "activation_email_failure_kind": row[13],
                "activation_email_next_attempt_at": _isoformat(row[14]),
            }
            for row in rows
        ]

        return jsonify({
            "status": "ok",
            "branch": {
                "id": branch_id,
                "name": branch_name,
                "code": branch_code
            },
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_students": total_students,
                "total_pages": (
                    total_students + per_page - 1
                ) // per_page
            },
            "students": students
        }), 200

    except Exception:
        app.logger.exception("HOD student list retrieval failed")
        return jsonify({
            "status": "error",
            "message": "Could not retrieve students."
        }), 503
@app.post("/api/hod/students")
@limiter.limit("20 per minute")


def add_hod_student():
    auth_error = require_hod()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}

    name = data.get("name", "")
    usn = data.get("usn", "")
    email = data.get("email", "")
    semester = data.get("semester")
    admission_year = data.get("admission_year")
    academic_year = data.get("academic_year")

    if not all(isinstance(v, str) for v in (name, usn, email)):
        return jsonify({
            "status": "error",
            "message": "Invalid student details."
        }), 400

    name = name.strip()
    usn = usn.strip().upper()
    email = email.strip().lower()

    if not re.fullmatch(r"[0-9]UB[0-9]{2}[A-Z]{2}[0-9]{3}", usn):
        return jsonify({
            "status": "error",
            "message": "USN must follow the format 4UB23CS026."
        }), 400

    if not name or len(name) > 150:
        return jsonify({
            "status": "error",
            "message": "Enter a valid student name."
        }), 400

    if not valid_email_address(email):
        return jsonify({
            "status": "error",
            "message": "Enter a valid email address."
        }), 400

    try:
        semester = int(semester)
        admission_year = int(admission_year)
        academic_year = int(academic_year)
    except (TypeError, ValueError):
        return jsonify({
            "status": "error",
            "message": "Enter a valid semester, admission year and academic year."
        }), 400

    if not 1 <= semester <= 12:
        return jsonify({
            "status": "error",
            "message": "Semester must be between 1 and 12."
        }), 400

    if not valid_admission_year(admission_year):
        return jsonify({
            "status": "error",
            "message": "Enter a valid admission year."
        }), 400
    if not valid_admission_year(academic_year):
        return jsonify({
            "status": "error",
            "message": "Enter a valid academic year."
        }), 400

    try:
        # Create the student and queue an invitation in one transaction. The
        # delivery worker creates a token only when it is ready to send it.
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    SELECT h.branch_id, b.name
                    FROM hod_assignments h
                    JOIN branches b ON b.id = h.branch_id
                    WHERE h.account_id = %s
                      AND b.is_active = TRUE;
                """, (session["account_id"],))

                branch = cur.fetchone()

                if not branch:
                    return jsonify({
                        "status": "error",
                        "message": "No active branch is assigned to this HOD."
                    }), 403

                branch_id, branch_name = branch

                cur.execute("""
                    SELECT 1
                    FROM accounts
                    WHERE LOWER(email) = %s;
                """, (email,))

                if cur.fetchone():
                    return jsonify({
                        "status": "error",
                        "message": "This email is already registered."
                    }), 409

                cur.execute("""
                    SELECT 1
                    FROM students
                    WHERE UPPER(usn) = %s;
                """, (usn,))

                if cur.fetchone():
                    return jsonify({
                        "status": "error",
                        "message": "This USN is already registered."
                    }), 409

                cur.execute("""
                    INSERT INTO accounts (
                        email,
                        role,
                        full_name
                    )
                    VALUES (%s, 'STUDENT', %s)
                    RETURNING id;
                """, (email, name))

                account_id = cur.fetchone()[0]

                cur.execute("""
                    INSERT INTO students (
                        account_id,
                        usn,
                        full_name,
                        branch_id,
                        semester,
                        admission_year,
                        academic_year
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (
                    account_id,
                    usn,
                    name,
                    branch_id,
                    semester,
                    admission_year,
                    academic_year
                ))

                student_id = cur.fetchone()[0]

                job_id = queue_student_activation_email(cur, account_id)
                write_audit_event(cur, "STUDENT_REGISTERED", {
                    "account_id": account_id,
                    "student_id": student_id,
                    "usn": usn,
                    "branch_id": branch_id,
                    "admission_year": admission_year,
                    "academic_year": academic_year,
                    "semester": semester,
                    "registered_by": session["account_id"],
                    "activation_email_job_id": job_id,
                })

        return jsonify({
            "status": "ok",
            "message": (
                "Student registered successfully. The activation invitation "
                "has been queued for safe delivery."
            ),
            "activation_email_queued": True,
            "student": {
                "id": student_id,
                "name": name,
                "usn": usn,
                "email": email,
                "branch": branch_name,
                "semester": semester,
                "admission_year": admission_year,
                "academic_year": academic_year,
            }
        }), 201

    except Exception:
        app.logger.exception("Student registration failed")

        return jsonify({
            "status": "error",
            "message": "Could not register the student."
        }), 503

# ------------------------------------------
# HOD: BULK STUDENT UPLOAD PREVIEW
# ------------------------------------------

@app.post("/api/hod/students/bulk-upload/preview")
@limiter.limit("10 per minute")
def preview_hod_student_bulk_upload():
    auth_error = require_hod()
    if auth_error:
        return auth_error

    uploaded_file = request.files.get("file")
    admission_year = request.form.get("admission_year")
    academic_year = request.form.get("academic_year")
    semester = request.form.get("semester")

    if not uploaded_file or not uploaded_file.filename:
        return jsonify({
            "status": "error",
            "message": "Please select an Excel or CSV file."
        }), 400

    filename = uploaded_file.filename.lower()

    if not filename.endswith((".csv", ".xlsx")):
        return jsonify({
            "status": "error",
            "message": "Only CSV and XLSX files are supported."
        }), 400

    try:
        admission_year = int(admission_year)
        academic_year = int(academic_year)
        semester = int(semester)
    except (TypeError, ValueError):
        return jsonify({
            "status": "error",
            "message": "Select a valid admission year, academic year and semester."
        }), 400

    if (
        not valid_admission_year(admission_year)
        or not valid_admission_year(academic_year)
        or not 1 <= semester <= 12
    ):
        return jsonify({
            "status": "error",
            "message": "Invalid admission year or semester."
        }), 400

    try:
        file_bytes = uploaded_file.read(5 * 1024 * 1024 + 1)

        if len(file_bytes) > 5 * 1024 * 1024:
            return jsonify({
                "status": "error",
                "message": "File size must not exceed 5 MB."
            }), 413

        if filename.endswith(".csv"):
            content = file_bytes.decode("utf-8-sig")
            rows = list(csv.reader(io.StringIO(content)))
        else:
            workbook = load_workbook(
                io.BytesIO(file_bytes),
                read_only=True,
                data_only=True
            )
            worksheet = workbook.active
            rows = list(worksheet.iter_rows(values_only=True))
            workbook.close()

        if not rows or len(rows) < 2:
            return jsonify({
                "status": "error",
                "message": "The file has no student records."
            }), 400

        headers = [
            str(value or "").strip().lower()
            for value in rows[0]
        ]

        column_names = {
            "name": ["name", "student name", "full name", "student full name"],
            "usn": ["usn", "university seat number"],
            "email": ["email", "email address", "student email"]
        }

        indexes = {}

        for field, alternatives in column_names.items():
            for index, header in enumerate(headers):
                if header in alternatives:
                    indexes[field] = index
                    break

        if len(indexes) != 3:
            return jsonify({
                "status": "error",
                "message": "File headings must contain Name, USN and Email."
            }), 400

        if len(rows) - 1 > 1000:
            return jsonify({
                "status": "error",
                "message": "Maximum 1000 student rows are allowed per file."
            }), 400

        valid_rows = []
        invalid_rows = []
        seen_usns = set()
        seen_emails = set()
        uploaded_student_rows = 0

        for row_number, row in enumerate(rows[1:], start=2):
            if not row or all(value is None or str(value).strip() == "" for value in row):
                continue

            uploaded_student_rows += 1

            def value_for(field):
                index = indexes[field]
                if index >= len(row) or row[index] is None:
                    return ""
                return str(row[index]).strip()

            name = value_for("name")
            usn = value_for("usn").upper()
            email = value_for("email").lower()

            errors = []
            if not re.fullmatch(r"[0-9]UB[0-9]{2}[A-Z]{2}[0-9]{3}", usn):
                errors.append("USN must follow the format 4UB23CS026.")

            if not name or len(name) > 150:
                errors.append("Invalid student name.")

            if not usn or len(usn) > 40:
                errors.append("Invalid USN.")

            if not valid_email_address(email):
                errors.append("Invalid email address.")

            if usn and usn in seen_usns:
                errors.append("Duplicate USN inside this file.")

            if email and email in seen_emails:
                errors.append("Duplicate email inside this file.")

            if usn:
                seen_usns.add(usn)

            if email:
                seen_emails.add(email)

            record = {
                "row": row_number,
                "name": name,
                "usn": usn,
                "email": email
            }

            if errors:
                invalid_rows.append({
                    **record,
                    "errors": errors
                })
            else:
                valid_rows.append(record)

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT b.name
                    FROM hod_assignments h
                    JOIN branches b ON b.id = h.branch_id
                    WHERE h.account_id = %s
                      AND b.is_active = TRUE;
                """, (session["account_id"],))

                branch = cur.fetchone()

                if not branch:
                    return jsonify({
                        "status": "error",
                        "message": "No active branch is assigned to this HOD."
                    }), 403

                usns = [item["usn"] for item in valid_rows]
                emails = [item["email"] for item in valid_rows]

                existing_usns = set()
                existing_emails = set()

                if usns:
                    cur.execute("""
                        SELECT UPPER(usn)
                        FROM students
                        WHERE UPPER(usn) = ANY(%s);
                    """, (usns,))
                    existing_usns = {item[0] for item in cur.fetchall()}

                if emails:
                    cur.execute("""
                        SELECT LOWER(email)
                        FROM accounts
                        WHERE LOWER(email) = ANY(%s);
                    """, (emails,))
                    existing_emails = {item[0] for item in cur.fetchall()}

        final_valid_rows = []

        for record in valid_rows:
            errors = []

            if record["usn"] in existing_usns:
                errors.append("USN is already registered.")

            if record["email"] in existing_emails:
                errors.append("Email is already registered.")

            if errors:
                invalid_rows.append({
                    **record,
                    "errors": errors
                })
            else:
                final_valid_rows.append(record)

        return jsonify({
            "status": "ok",
            "message": (
                f"Validation complete: {len(final_valid_rows)} valid "
                f"and {len(invalid_rows)} invalid row(s). No students added."
            ),
            "branch": branch[0],
            "admission_year": admission_year,
            "academic_year": academic_year,
            "semester": semester,
            "total_uploaded_students": uploaded_student_rows,
            "valid_count": len(final_valid_rows),
            "invalid_count": len(invalid_rows),
            "duplicate_count": sum(
                1 for row in invalid_rows
                if any("duplicate" in error.lower() or "already registered" in error.lower()
                       for error in row["errors"])
            ),
            "valid_rows": final_valid_rows,
            "invalid_rows": invalid_rows
        }), 200

    except Exception:
        app.logger.exception("HOD bulk upload preview failed")
        return jsonify({
            "status": "error",
            "message": "Could not read or validate the uploaded file."
        }), 400    

# ------------------------------------------
# HOD: CONFIRM BULK STUDENT IMPORT
# ------------------------------------------

@app.post("/api/hod/students/bulk-upload/import")
@limiter.limit("5 per minute")

def import_hod_students_bulk():
    auth_error = require_hod()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}

    students = data.get("students")
    admission_year = data.get("admission_year")
    academic_year = data.get("academic_year")
    semester = data.get("semester")

    if not isinstance(students, list) or not students:
        return jsonify({
            "status": "error",
            "message": "There are no valid students to import."
        }), 400

    if len(students) > 1000:
        return jsonify({
            "status": "error",
            "message": "A maximum of 1000 students can be imported at once."
        }), 400

    try:
        admission_year = int(admission_year)
        academic_year = int(academic_year)
        semester = int(semester)
    except (TypeError, ValueError):
        return jsonify({
            "status": "error",
            "message": "Invalid admission year, academic year or semester."
        }), 400

    if (
        not valid_admission_year(admission_year)
        or not valid_admission_year(academic_year)
        or not 1 <= semester <= 12
    ):
        return jsonify({
            "status": "error",
            "message": "Invalid admission year or semester."
        }), 400

    cleaned_students = []
    seen_usns = set()
    seen_emails = set()

    for student in students:
        if not isinstance(student, dict):
            return jsonify({
                "status": "error",
                "message": "Invalid student data."
            }), 400

        name = student.get("name")
        usn = student.get("usn")
        email = student.get("email")

        if not all(
            isinstance(value, str)
            for value in (name, usn, email)
        ):
            return jsonify({
                "status": "error",
                "message": "Invalid student details."
            }), 400

        name = name.strip()
        usn = usn.strip().upper()
        email = email.strip().lower()

        if not re.fullmatch(r"[0-9]UB[0-9]{2}[A-Z]{2}[0-9]{3}", usn):
            return jsonify({
                "status": "error",
                "message": f"Invalid USN: {usn}."
            }), 400

        if not name or len(name) > 150:
            return jsonify({
                "status": "error",
                "message": "A student has an invalid name."
            }), 400

        if not valid_email_address(email):
            return jsonify({
                "status": "error",
                "message": "A student has an invalid email."
            }), 400

        if usn in seen_usns or email in seen_emails:
            return jsonify({
                "status": "error",
                "message": "Duplicate USN or email found in the import."
            }), 409

        seen_usns.add(usn)
        seen_emails.add(email)

        cleaned_students.append({
            "name": name,
            "usn": usn,
            "email": email
        })

    try:
        imported_students = []
        rejected_rows = []

        # Database registration and token creation.
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    SELECT h.branch_id, b.name
                    FROM hod_assignments h
                    JOIN branches b ON b.id = h.branch_id
                    WHERE h.account_id = %s
                      AND b.is_active = TRUE;
                """, (session["account_id"],))

                branch = cur.fetchone()

                if not branch:
                    return jsonify({
                        "status": "error",
                        "message": "No active branch is assigned to this HOD."
                    }), 403

                branch_id, branch_name = branch

                # Re-check every preview-approved row in the transaction. A
                # savepoint gives this import genuine partial success if a
                # record became a duplicate between preview and confirmation.
                # It also keeps one bad row from rolling back the valid rows.
                for index, student in enumerate(cleaned_students):
                    savepoint = f"student_import_{index}"
                    cur.execute(f"SAVEPOINT {savepoint};")
                    try:
                        cur.execute("""
                            SELECT
                                EXISTS (
                                    SELECT 1 FROM students
                                    WHERE UPPER(usn) = %s
                                ),
                                EXISTS (
                                    SELECT 1 FROM accounts
                                    WHERE LOWER(email) = %s
                                );
                        """, (student["usn"], student["email"]))
                        usn_exists, email_exists = cur.fetchone()
                        if usn_exists or email_exists:
                            conflicts = []
                            if usn_exists:
                                conflicts.append("USN is already registered.")
                            if email_exists:
                                conflicts.append("Email is already registered.")
                            rejected_rows.append({
                                "usn": student["usn"],
                                "errors": conflicts,
                            })
                            cur.execute(f"RELEASE SAVEPOINT {savepoint};")
                            continue

                        cur.execute("""
                            INSERT INTO accounts (email, role, full_name)
                            VALUES (%s, 'STUDENT', %s)
                            RETURNING id;
                        """, (student["email"], student["name"]))
                        account_id = cur.fetchone()[0]

                        cur.execute("""
                            INSERT INTO students (
                                account_id, usn, full_name, branch_id,
                                semester, admission_year, academic_year
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            RETURNING id;
                        """, (
                            account_id, student["usn"], student["name"],
                            branch_id, semester, admission_year, academic_year,
                        ))
                        student_id = cur.fetchone()[0]
                        activation_job_id = queue_student_activation_email(cur, account_id)

                        imported_students.append({
                            "id": student_id,
                            "name": student["name"],
                            "usn": student["usn"],
                            "email": student["email"],
                            "activation_email_status": "PENDING",
                        })
                        write_audit_event(cur, "STUDENT_REGISTERED", {
                            "account_id": account_id,
                            "student_id": student_id,
                            "usn": student["usn"],
                            "branch_id": branch_id,
                            "admission_year": admission_year,
                            "academic_year": academic_year,
                            "semester": semester,
                            "registered_by": session["account_id"],
                            "activation_email_job_id": activation_job_id,
                        })
                        cur.execute(f"RELEASE SAVEPOINT {savepoint};")
                    except psycopg.errors.UniqueViolation:
                        # A concurrent registration can still win after the
                        # pre-check. Roll back just this row and continue.
                        cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint};")
                        cur.execute(f"RELEASE SAVEPOINT {savepoint};")
                        rejected_rows.append({
                            "usn": student["usn"],
                            "errors": ["USN or email was registered concurrently."],
                        })

                if imported_students:
                    write_audit_event(cur, "STUDENT_BULK_IMPORT_QUEUED", {
                        "branch_id": branch_id,
                        "admission_year": admission_year,
                        "academic_year": academic_year,
                        "semester": semester,
                        "submitted_students": len(cleaned_students),
                        "registered_students": len(imported_students),
                        "rejected_students": len(rejected_rows),
                        "queued_activation_emails": len(imported_students),
                        "imported_by": session["account_id"],
                    })

        response = {
            "status": "ok",
            "message": (
                f"{len(imported_students)} student(s) registered; "
                f"{len(rejected_rows)} row(s) were not registered. "
                f"{len(imported_students)} activation invitation(s) queued for delivery."
            ),
            "submitted_count": len(cleaned_students),
            "imported_count": len(imported_students),
            "registered_students": len(imported_students),
            "rejected_count": len(rejected_rows),
            "rejected_rows": rejected_rows,
            "activation_emails_queued": len(imported_students),
            "activation_emails_sent": 0,
            "activation_emails_failed": 0,
            "branch": branch_name,
            "admission_year": admission_year,
            "academic_year": academic_year,
            "semester": semester,
            "students": imported_students,
        }
        return jsonify(response), 201 if imported_students else 200

    except Exception:
        app.logger.exception("HOD bulk student import failed")

        return jsonify({
            "status": "error",
            "message": "Import failed. Please check the backend logs."
        }), 503

@app.patch("/api/hod/students/<int:student_id>")
@limiter.limit("20 per minute")
def update_hod_student(student_id):
    """Update safe student profile fields within the HOD's department."""
    auth_error = require_hod()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    allowed_fields = {"name", "semester", "admission_year", "academic_year"}
    if not data or not set(data).issubset(allowed_fields):
        return jsonify({
            "status": "error",
            "message": "Provide name, semester, admission_year, and/or academic_year only.",
        }), 400

    updates = []
    values = []
    if "name" in data:
        name = data["name"]
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 150:
            return jsonify({"status": "error", "message": "Enter a valid student name."}), 400
        updates.extend(["full_name = %s"])
        values.append(name.strip())
    if "semester" in data:
        if type(data["semester"]) is not int or not 1 <= data["semester"] <= 12:
            return jsonify({"status": "error", "message": "Semester must be between 1 and 12."}), 400
        updates.append("semester = %s")
        values.append(data["semester"])
    if "admission_year" in data:
        if not valid_admission_year(data["admission_year"]):
            return jsonify({"status": "error", "message": "Enter a valid admission year."}), 400
        updates.append("admission_year = %s")
        values.append(data["admission_year"])
    if "academic_year" in data:
        if not valid_admission_year(data["academic_year"]):
            return jsonify({"status": "error", "message": "Enter a valid academic year."}), 400
        updates.append("academic_year = %s")
        values.append(data["academic_year"])

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT s.account_id, s.full_name, s.semester, s.admission_year, s.academic_year,
                           s.usn, a.full_name
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    JOIN hod_assignments h ON h.branch_id = s.branch_id
                    JOIN branches b ON b.id = h.branch_id
                    WHERE s.id = %s
                      AND h.account_id = %s
                      AND a.role = 'STUDENT'
                      AND b.is_active = TRUE
                    FOR UPDATE OF s, a;
                """, (student_id, session["account_id"]))
                current = cur.fetchone()
                if not current:
                    return jsonify({"status": "error", "message": "Student not found in your department."}), 404

                if any(field in data for field in ("semester", "admission_year", "academic_year")):
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1
                            FROM voter_eligibility ve
                            JOIN elections e ON e.id = ve.election_id
                            WHERE ve.student_id = %s
                              AND e.status IN ('DRAFT', 'SCHEDULED', 'OPEN')
                        );
                    """, (student_id,))
                    if cur.fetchone()[0]:
                        return jsonify({
                            "status": "error",
                            "message": (
                                "Academic details cannot change while this student "
                                "is eligible for an unfinished election."
                            ),
                        }), 409

                values.append(student_id)
                cur.execute(f"""
                    UPDATE students
                    SET {', '.join(updates)}
                    WHERE id = %s
                    RETURNING id, full_name, usn, semester, admission_year, academic_year, account_id;
                """, tuple(values))
                updated = cur.fetchone()
                if "name" in data:
                    cur.execute("UPDATE accounts SET full_name = %s WHERE id = %s;", (
                        updated[1], updated[6],
                    ))
                write_audit_event(cur, "STUDENT_UPDATED", {
                    "student_id": updated[0],
                    "usn": updated[2],
                    "updated_by": session["account_id"],
                    "before": {
                        "name": current[1],
                        "semester": current[2],
                        "admission_year": current[3], "academic_year": current[4],
                    },
                    "after": {
                        "name": updated[1],
                        "semester": updated[3],
                        "admission_year": updated[4], "academic_year": updated[5],
                    },
                })

        return jsonify({
            "status": "ok",
            "message": "Student updated successfully.",
            "student": {
                "id": updated[0], "name": updated[1], "usn": updated[2],
                "semester": updated[3], "admission_year": updated[4],
                "academic_year": updated[5],
            },
        }), 200
    except Exception:
        app.logger.exception("HOD student update failed")
        return jsonify({"status": "error", "message": "Could not update the student."}), 503


@app.delete("/api/hod/students/<int:student_id>")
@limiter.limit("20 per minute")

def delete_hod_student(student_id):
    auth_error = require_hod()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Verify that this student belongs to this HOD's branch.
                cur.execute("""
                    SELECT s.account_id, a.is_active
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    JOIN hod_assignments h ON h.branch_id = s.branch_id
                    JOIN branches b ON b.id = h.branch_id
                    WHERE s.id = %s
                      AND h.account_id = %s
                      AND b.is_active = TRUE
                      AND a.role = 'STUDENT'
                    FOR UPDATE OF s, a;
                """, (student_id, session["account_id"]))

                student = cur.fetchone()

                if not student:
                    return jsonify({
                        "status": "error",
                        "message": "Student not found in your department."
                    }), 404

                account_id, is_active = student

                if not is_active:
                    return jsonify({
                        "status": "error",
                        "message": "This student is already inactive."
                    }), 409

                # Soft delete: preserve the student's records.
                cur.execute("""
                    UPDATE accounts
                    SET is_active = FALSE
                    WHERE id = %s
                      AND role = 'STUDENT';
                """, (account_id,))
                write_audit_event(cur, "STUDENT_DEACTIVATED", {
                    "student_id": student_id,
                    "account_id": account_id,
                    "deactivated_by": session["account_id"],
                })

        return jsonify({
            "status": "ok",
            "message": "Student account deactivated successfully."
        }), 200

    except Exception:
        app.logger.exception("HOD student deactivation failed")
        return jsonify({
            "status": "error",
            "message": "Could not deactivate this student."
        }), 503  
# ------------------------------------------
# HOD: ACTIVATE / DEACTIVATE STUDENT
# ------------------------------------------

@app.patch("/api/hod/students/<int:student_id>/status")
@limiter.limit("20 per minute")
def update_hod_student_status(student_id):
    auth_error = require_hod()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    next_status = data.get("is_active")

    if not isinstance(next_status, bool):
        return jsonify({
            "status": "error",
            "message": "A valid is_active value is required."
        }), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Verify that the student belongs to this HOD's branch.
                cur.execute("""
                    SELECT s.account_id, a.is_active
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    JOIN hod_assignments h ON h.branch_id = s.branch_id
                    JOIN branches b ON b.id = h.branch_id
                    WHERE s.id = %s
                      AND h.account_id = %s
                      AND b.is_active = TRUE
                      AND a.role = 'STUDENT'
                    FOR UPDATE OF s, a;
                """, (student_id, session["account_id"]))

                student = cur.fetchone()

                if not student:
                    return jsonify({
                        "status": "error",
                        "message": "Student not found in your department."
                    }), 404

                account_id, current_status = student

                if current_status == next_status:
                    return jsonify({
                        "status": "ok",
                        "message": (
                            "Student is already active."
                            if next_status
                            else "Student is already inactive."
                        ),
                        "is_active": current_status
                    }), 200

                cur.execute("""
                    UPDATE accounts
                    SET is_active = %s
                    WHERE id = %s
                      AND role = 'STUDENT';
                """, (next_status, account_id))
                write_audit_event(cur, "STUDENT_STATUS_UPDATED", {
                    "student_id": student_id,
                    "account_id": account_id,
                    "is_active": next_status,
                    "updated_by": session["account_id"],
                })

        return jsonify({
            "status": "ok",
            "message": (
                "Student activated successfully."
                if next_status
                else "Student deactivated successfully."
            ),
            "is_active": next_status
        }), 200

    except Exception:
        app.logger.exception("HOD student status update failed")
        return jsonify({
            "status": "error",
            "message": "Could not update student status."
        }), 503    
    
@app.patch("/api/hod/students/bulk-status")
@limiter.limit("10 per minute")
def update_hod_students_bulk_status():
    auth_error = require_hod()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}

    student_ids = data.get("student_ids")
    next_status = data.get("is_active")

    if not isinstance(student_ids, list) or not student_ids:
        return jsonify({
            "status": "error",
            "message": "Select at least one student."
        }), 400

    if len(student_ids) > 500:
        return jsonify({
            "status": "error",
            "message": "You can update a maximum of 500 students at once."
        }), 400

    if (
        any(type(student_id) is not int or student_id <= 0
            for student_id in student_ids)
        or len(set(student_ids)) != len(student_ids)
    ):
        return jsonify({
            "status": "error",
            "message": "Invalid or duplicate student IDs."
        }), 400

    if not isinstance(next_status, bool):
        return jsonify({
            "status": "error",
            "message": "A valid is_active value is required."
        }), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Verify every selected student belongs to this HOD.
                cur.execute("""
                    SELECT s.id, s.account_id
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    JOIN hod_assignments h ON h.branch_id = s.branch_id
                    JOIN branches b ON b.id = h.branch_id
                    WHERE s.id = ANY(%s)
                      AND h.account_id = %s
                      AND b.is_active = TRUE
                      AND a.role = 'STUDENT'
                    FOR UPDATE OF s, a;
                """, (student_ids, session["account_id"]))

                students = cur.fetchall()

                if len(students) != len(student_ids):
                    return jsonify({
                        "status": "error",
                        "message": (
                            "Some selected students were not found "
                            "in your department. No changes were made."
                        )
                    }), 404

                account_ids = [student[1] for student in students]

                cur.execute("""
                    UPDATE accounts
                    SET is_active = %s
                    WHERE id = ANY(%s)
                      AND role = 'STUDENT';
                """, (next_status, account_ids))
                write_audit_event(cur, "STUDENTS_BULK_STATUS_UPDATED", {
                    "student_ids": sorted(student_ids),
                    "is_active": next_status,
                    "updated_by": session["account_id"],
                })

        return jsonify({
            "status": "ok",
            "message": (
                f"{len(student_ids)} student(s) activated successfully."
                if next_status
                else f"{len(student_ids)} student(s) deactivated successfully."
            ),
            "student_ids": student_ids,
            "is_active": next_status
        }), 200

    except Exception:
        app.logger.exception("HOD bulk student status update failed")
        return jsonify({
            "status": "error",
            "message": "Could not update selected students."
        }), 503   

# ------------------------------------------
# HOD: CLASSES AND SEMESTERS
# ------------------------------------------

@app.get("/api/hod/classes")
@limiter.limit("60 per minute")
def get_hod_classes():
    auth_error = require_hod()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # Verify the HOD's assigned branch.
                cur.execute("""
                    SELECT b.id, b.name
                    FROM hod_assignments h
                    JOIN branches b ON b.id = h.branch_id
                    WHERE h.account_id = %s
                      AND b.is_active = TRUE;
                """, (session["account_id"],))

                branch = cur.fetchone()

                if not branch:
                    return jsonify({
                        "status": "error",
                        "message": "No active branch is assigned to this HOD."
                    }), 403

                branch_id, branch_name = branch

                # Academic year is part of the class cohort; do not merge
                # different cohorts that happen to share an admission year
                # and semester.
                cur.execute("""
                    SELECT
                        s.admission_year,
                        s.academic_year,
                        s.semester,
                        COUNT(s.id) AS total_students,
                        COUNT(*) FILTER (
                            WHERE a.is_active = TRUE
                        ) AS active_students,
                        COUNT(*) FILTER (
                            WHERE a.is_active = FALSE
                        ) AS inactive_students,
                        COUNT(*) FILTER (
                            WHERE s.is_cr = TRUE
                        ) AS cr_count,
                        COUNT(*) FILTER (
                            WHERE s.is_fr = TRUE
                        ) AS fr_count
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    WHERE s.branch_id = %s
                      AND a.role = 'STUDENT'
                    GROUP BY
                        s.admission_year,
                        s.academic_year,
                        s.semester
                    ORDER BY
                        s.admission_year DESC,
                        s.academic_year DESC NULLS LAST,
                        s.semester ASC;
                """, (branch_id,))

                rows = cur.fetchall()

                classes = []

                for row in rows:
                    classes.append({
                        "admission_year": row[0],
                        "academic_year": row[1],
                        "semester": row[2],
                        "total_students": row[3],
                        "active_students": row[4],
                        "inactive_students": row[5],
                        "cr_count": row[6],
                        "fr_count": row[7]
                    })

        return jsonify({
            "status": "ok",
            "branch": branch_name,
            "classes": classes
        }), 200

    except Exception:
        app.logger.exception("HOD classes retrieval failed")
        return jsonify({
            "status": "error",
            "message": "Could not load classes and semesters."
        }), 503                   
# ==========================================
# STUDENT ELECTIONS, ANONYMOUS VOTING AND RESULTS
# ==========================================

def _isoformat(value):
    return value.isoformat() if value else None


def _student_record(cur, account_id):
    cur.execute("""
        SELECT s.id, s.full_name, s.usn, a.email, b.name, b.code,
               s.admission_year, s.academic_year, s.semester, a.is_active
        FROM students s
        JOIN accounts a ON a.id = s.account_id
        JOIN branches b ON b.id = s.branch_id
        WHERE a.id = %s AND a.role = 'STUDENT';
    """, (account_id,))
    return cur.fetchone()


def _election_result_payload(cur, election_id):
    """Build a result without selecting voter identities or ballot links."""
    cur.execute("""
        SELECT e.id, e.title, e.description, e.election_type, e.status, e.opens_at, e.closes_at,
               b.name
        FROM elections e
        LEFT JOIN branches b ON b.id = e.branch_id
        WHERE e.id = %s;
    """, (election_id,))
    election = cur.fetchone()
    if not election:
        return None

    cur.execute("""
        SELECT c.id, s.full_name, s.usn, c.manifesto, c.symbol_key,
               COUNT(ballot.id) AS vote_count
        FROM candidates c
        JOIN students s ON s.id = c.student_id
        LEFT JOIN ballots ballot
          ON ballot.election_id = c.election_id
         AND ballot.candidate_id = c.id
        WHERE c.election_id = %s
          AND c.is_approved = TRUE
          AND c.review_status = 'APPROVED'
        GROUP BY c.id, s.full_name, s.usn, c.manifesto, c.symbol_key
        ORDER BY vote_count DESC, c.id ASC;
    """, (election_id,))
    candidate_rows = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM voter_eligibility WHERE election_id = %s;", (election_id,))
    eligible_voters = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM voter_participation WHERE election_id = %s;", (election_id,))
    participation_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ballots WHERE election_id = %s;", (election_id,))
    ballot_count = cur.fetchone()[0]

    candidates = [
        {
            "id": row[0],
            "name": row[1],
            "usn": row[2],
            "manifesto": row[3] or "",
            "symbol_key": row[4],
            "symbol": candidate_symbol_payload(row[4]),
            "vote_count": row[5],
        }
        for row in candidate_rows
    ]
    top_votes = candidates[0]["vote_count"] if candidates else 0
    winners = [item for item in candidates if candidates and item["vote_count"] == top_votes]
    return {
        "election": {
            "id": election[0],
            "title": election[1],
            "description": election[2] or "",
            "election_type": election[3],
            "status": election[4],
            "opens_at": _isoformat(election[5]),
            "closes_at": _isoformat(election[6]),
            "branch": election[7],
        },
        "candidates": candidates,
        "eligible_voters": eligible_voters,
        "participation_count": participation_count,
        "ballot_count": ballot_count,
        "turnout_percentage": round((participation_count * 100 / eligible_voters), 2) if eligible_voters else 0,
        "winners": winners,
        "is_tie": len(winners) > 1,
        "integrity_check": participation_count == ballot_count,
    }


@app.get("/api/student/dashboard")
@limiter.limit("60 per minute")
def student_dashboard():
    auth_error = require_student()
    if auth_error:
        return auth_error
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                student = _student_record(cur, session["account_id"])
                if not student:
                    return jsonify({"status": "error", "message": "Student profile was not found."}), 404
                student_id = student[0]
                cur.execute("""
                    SELECT
                        COUNT(*) FILTER (WHERE e.status IN ('OPEN', 'CLOSED')),
                        COUNT(*) FILTER (
                            WHERE e.status = 'OPEN'
                              AND e.opens_at <= CURRENT_TIMESTAMP
                              AND e.closes_at > CURRENT_TIMESTAMP
                        ),
                        COUNT(vp.student_id)
                    FROM voter_eligibility ve
                    JOIN elections e ON e.id = ve.election_id
                    LEFT JOIN voter_participation vp
                      ON vp.election_id = ve.election_id AND vp.student_id = ve.student_id
                    WHERE ve.student_id = %s;
                """, (student_id,))
                counts = cur.fetchone()
        return jsonify({
            "status": "ok",
            "profile": {
                "id": student[0], "full_name": student[1], "usn": student[2],
                "email": student[3], "branch_name": student[4], "branch_code": student[5],
                "admission_year": student[6], "academic_year": student[7],
                "semester": student[8], "is_active": student[9],
            },
            "statistics": {
                "eligible_elections": counts[0], "active_elections": counts[1],
                "participated_elections": counts[2],
            },
        }), 200
    except Exception:
        app.logger.exception("Student dashboard retrieval failed")
        return jsonify({"status": "error", "message": "Could not load the student dashboard."}), 503


@app.get("/api/student/elections")
@limiter.limit("60 per minute")
def list_student_elections():
    auth_error = require_student()
    if auth_error:
        return auth_error
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                student = _student_record(cur, session["account_id"])
                if not student:
                    return jsonify({"status": "error", "message": "Student profile was not found."}), 404
                cur.execute("""
                    SELECT e.id, e.title, e.description, e.election_type, e.status, e.opens_at, e.closes_at,
                           b.name, EXISTS(
                               SELECT 1 FROM voter_participation vp
                               WHERE vp.election_id = e.id AND vp.student_id = %s
                           ) AS has_participated
                    FROM voter_eligibility ve
                    JOIN elections e ON e.id = ve.election_id
                    LEFT JOIN branches b ON b.id = e.branch_id
                    WHERE ve.student_id = %s
                      AND e.status IN ('OPEN', 'CLOSED')
                    ORDER BY e.opens_at DESC, e.id DESC;
                """, (student[0], student[0]))
                rows = cur.fetchall()
                election_ids = [row[0] for row in rows]
                candidates_by_election = {election_id: [] for election_id in election_ids}
                if election_ids:
                    # Fetch every approved ballot option in one bounded query;
                    # do not issue one query per election (N+1) for a student
                    # who is eligible for a long election history.
                    cur.execute("""
                        SELECT c.election_id, c.id, s.usn, c.symbol_key
                        FROM candidates c
                        JOIN students s ON s.id = c.student_id
                        WHERE c.election_id = ANY(%s)
                          AND c.is_approved = TRUE
                          AND c.review_status = 'APPROVED'
                        ORDER BY c.election_id, s.usn, c.id;
                    """, (election_ids,))
                    for candidate in cur.fetchall():
                        candidates_by_election[candidate[0]].append({
                            "id": candidate[1],
                            "usn": candidate[2],
                            "symbol_key": candidate[3],
                            "symbol": candidate_symbol_payload(candidate[3]),
                        })
                elections = []
                for row in rows:
                    is_open = row[4] == "OPEN" and row[5] <= __import__("datetime").datetime.now(timezone.utc) < row[6]
                    elections.append({
                        "id": row[0], "title": row[1], "description": row[2] or "", "election_type": row[3],
                        "status": "OPEN" if is_open else "CLOSED",
                        "opens_at": _isoformat(row[5]), "closes_at": _isoformat(row[6]),
                        "branch": row[7], "has_participated": row[8],
                        "candidates": candidates_by_election[row[0]],
                    })
        return jsonify({"status": "ok", "elections": elections}), 200
    except Exception:
        app.logger.exception("Student election retrieval failed")
        return jsonify({"status": "error", "message": "Could not load eligible elections."}), 503


@app.post("/api/student/elections/<int:election_id>/vote")
@limiter.limit("10 per minute")
def cast_student_vote(election_id):
    auth_error = require_student()
    if auth_error:
        return auth_error
    data = request.get_json(silent=True) or {}
    candidate_id = data.get("candidate_id")
    if type(candidate_id) is not int or candidate_id <= 0:
        return jsonify({"status": "error", "message": "Choose a valid candidate."}), 400
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Re-check and lock account/branch state in the same
                # transaction as participation.  The session guard above is
                # deliberately not treated as an authorization snapshot:
                # a concurrent HOD deactivation or branch disable must win
                # before a ballot can be committed.
                cur.execute("""
                    SELECT s.id
                    FROM students s
                    JOIN accounts a ON a.id = s.account_id
                    JOIN branches b ON b.id = s.branch_id
                    WHERE a.id = %s
                      AND a.role = 'STUDENT'
                      AND a.is_active = TRUE
                      AND b.is_active = TRUE
                    FOR SHARE OF s, a, b;
                """, (session["account_id"],))
                student = cur.fetchone()
                if not student:
                    return jsonify({
                        "status": "error",
                        "message": "Your student account is inactive or has no active department.",
                    }), 403
                student_id = student[0]
                # Lock the election so its lifecycle cannot change during ballot submission.
                cur.execute("""
                    SELECT id, status, opens_at, closes_at
                    FROM elections
                    WHERE id = %s
                    FOR UPDATE;
                """, (election_id,))
                election = cur.fetchone()
                if not election:
                    return jsonify({"status": "error", "message": "Election not found."}), 404
                if election[1] != "OPEN" or election[2] > __import__("datetime").datetime.now(timezone.utc) or election[3] <= __import__("datetime").datetime.now(timezone.utc):
                    return jsonify({"status": "error", "message": "Voting is not open for this election."}), 409
                cur.execute("""
                    SELECT 1 FROM voter_eligibility
                    WHERE election_id = %s AND student_id = %s;
                """, (election_id, student_id))
                if not cur.fetchone():
                    return jsonify({"status": "error", "message": "You are not eligible for this election."}), 403
                cur.execute("""
                    SELECT 1 FROM candidates
                    WHERE id = %s AND election_id = %s
                      AND is_approved = TRUE AND review_status = 'APPROVED';
                """, (candidate_id, election_id))
                if not cur.fetchone():
                    return jsonify({"status": "error", "message": "That candidate is not available in this election."}), 400
                # The participation primary key serializes concurrent requests. The ballot table
                # deliberately has no student identifier and is not linked back to this row.
                cur.execute("""
                    INSERT INTO voter_participation (election_id, student_id)
                    VALUES (%s, %s)
                    ON CONFLICT (election_id, student_id) DO NOTHING
                    RETURNING recorded_at;
                """, (election_id, student_id))
                participation = cur.fetchone()
                if not participation:
                    return jsonify({"status": "error", "message": "A vote has already been recorded for this election."}), 409
                cur.execute("""
                    INSERT INTO ballots (election_id, candidate_id)
                    VALUES (%s, %s)
                    RETURNING ballot_reference;
                """, (election_id, candidate_id))
                # Never return the ballot reference: it is not a voter receipt.
                cur.fetchone()
                # The audit event intentionally contains neither a student
                # identifier nor a ballot reference/candidate.  It proves
                # that a complete vote transaction occurred while preserving
                # the required separation of participation and ballot data.
                write_audit_event(cur, "VOTE_RECORDED", {
                    "election_id": election_id,
                    "participation_recorded": True,
                    "ballot_recorded": True,
                }, election_id)
        return jsonify({"status": "ok", "message": "Your vote has been recorded successfully."}), 201
    except Exception:
        app.logger.exception("Anonymous ballot submission failed")
        return jsonify({"status": "error", "message": "Your vote could not be recorded. No confirmation was issued."}), 503


@app.get("/api/student/voting-history")
@limiter.limit("60 per minute")
def student_voting_history():
    auth_error = require_student()
    if auth_error:
        return auth_error
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                student = _student_record(cur, session["account_id"])
                if not student:
                    return jsonify({"status": "error", "message": "Student profile was not found."}), 404
                cur.execute("""
                    SELECT e.id, e.title, e.election_type, e.closes_at, b.name, vp.recorded_at
                    FROM voter_participation vp
                    JOIN elections e ON e.id = vp.election_id
                    LEFT JOIN branches b ON b.id = e.branch_id
                    WHERE vp.student_id = %s
                    ORDER BY vp.recorded_at DESC, e.id DESC;
                """, (student[0],))
                history = [
                    {"election_id": row[0], "title": row[1], "election_type": row[2],
                     "closes_at": _isoformat(row[3]), "branch": row[4],
                     "participated_at": _isoformat(row[5]), "participation_status": "RECORDED"}
                    for row in cur.fetchall()
                ]
        return jsonify({"status": "ok", "history": history}), 200
    except Exception:
        app.logger.exception("Student voting history retrieval failed")
        return jsonify({"status": "error", "message": "Could not load voting history."}), 503


@app.post("/api/hod/elections/<int:election_id>/candidates/<int:candidate_id>/reject")
@limiter.limit("30 per minute")
def reject_hod_election_candidate(election_id, candidate_id):
    auth_error = require_hod()
    if auth_error:
        return auth_error
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.student_id, s.usn, e.status
                    FROM elections e
                    JOIN hod_assignments h ON h.branch_id = e.branch_id
                    JOIN candidates c ON c.election_id = e.id
                    JOIN students s ON s.id = c.student_id
                    WHERE e.id = %s AND c.id = %s AND h.account_id = %s
                    FOR UPDATE OF c, e;
                """, (election_id, candidate_id, session["account_id"]))
                candidate = cur.fetchone()
                if not candidate:
                    return jsonify({"status": "error", "message": "Candidate not found in your department."}), 404
                if candidate[2] not in ("DRAFT", "SCHEDULED"):
                    return jsonify({"status": "error", "message": "Candidates cannot be reviewed after voting starts."}), 409
                cur.execute("""
                    UPDATE candidates
                    SET is_approved = FALSE, review_status = 'REJECTED',
                        reviewed_at = CURRENT_TIMESTAMP, reviewed_by = %s
                    WHERE id = %s AND election_id = %s;
                """, (session["account_id"], candidate_id, election_id))
                write_audit_event(cur, "HOD_CANDIDATE_REJECTED", {
                    "candidate_id": candidate_id, "student_id": candidate[0],
                    "usn": candidate[1], "rejected_by": session["account_id"]
                }, election_id)
        return jsonify({"status": "ok", "message": "Candidate rejected successfully."}), 200
    except Exception:
        app.logger.exception("HOD candidate rejection failed")
        return jsonify({"status": "error", "message": "Could not reject the candidate."}), 503


@app.get("/api/hod/elections/<int:election_id>/results")
@limiter.limit("60 per minute")
def hod_election_results(election_id):
    auth_error = require_hod()
    if auth_error:
        return auth_error
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT e.id, e.status, e.closes_at
                    FROM elections e
                    JOIN hod_assignments h ON h.branch_id = e.branch_id
                    WHERE e.id = %s AND h.account_id = %s
                    FOR UPDATE OF e;
                """, (election_id, session["account_id"]))
                election = cur.fetchone()
                if not election:
                    return jsonify({"status": "error", "message": "Election not found in your department."}), 404
                if election[1] == "OPEN" and election[2] <= __import__("datetime").datetime.now(timezone.utc):
                    cur.execute("UPDATE elections SET status = 'CLOSED' WHERE id = %s;", (election_id,))
                    write_audit_event(cur, "HOD_ELECTION_AUTO_CLOSED", {
                        "election_id": election_id, "close_reason": "TIME_EXPIRED"
                    }, election_id)
                    write_election_result_commitment(cur, election_id)
                    election = (election[0], "CLOSED", election[2])
                if election[1] != "CLOSED":
                    return jsonify({"status": "error", "message": "Results are available only after the election is closed."}), 409
                result = _election_result_payload(cur, election_id)
        return jsonify({"status": "ok", "result": result}), 200
    except Exception:
        app.logger.exception("HOD election results retrieval failed")
        return jsonify({"status": "error", "message": "Could not calculate election results."}), 503


@app.get("/api/hod/results")
@limiter.limit("60 per minute")
def list_hod_election_results():
    auth_error = require_hod()
    if auth_error:
        return auth_error
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT e.id FROM elections e
                    JOIN hod_assignments h ON h.branch_id = e.branch_id
                    WHERE h.account_id = %s AND e.status = 'CLOSED'
                    ORDER BY e.closes_at DESC, e.id DESC;
                """, (session["account_id"],))
                results = [_election_result_payload(cur, row[0]) for row in cur.fetchall()]
        return jsonify({"status": "ok", "results": results}), 200
    except Exception:
        app.logger.exception("HOD results list retrieval failed")
        return jsonify({"status": "error", "message": "Could not load election results."}), 503


# ------------------------------------------
# 7. START FLASK SERVER
# ------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
