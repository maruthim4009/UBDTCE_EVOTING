
BEGIN;

-- Enable SHA-256 hashing for audit events.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. College branches
CREATE TABLE branches (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE,
    code VARCHAR(20) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Accounts for Principal, HODs and students
CREATE TABLE accounts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE,
    role VARCHAR(20) NOT NULL
        CHECK (role IN ('PRINCIPAL', 'HOD', 'STUDENT')),
    full_name VARCHAR(150),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- A HOD can be assigned to a specific branch.
CREATE TABLE hod_assignments (
    account_id BIGINT PRIMARY KEY REFERENCES accounts(id),
    branch_id BIGINT NOT NULL REFERENCES branches(id),
    UNIQUE (branch_id)
);

-- 3. Student details uploaded by the HOD
CREATE TABLE students (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL UNIQUE REFERENCES accounts(id),
    usn VARCHAR(40) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL,
    branch_id BIGINT NOT NULL REFERENCES branches(id),
    semester SMALLINT NOT NULL CHECK (semester BETWEEN 1 AND 12),
    admission_year SMALLINT CHECK (admission_year BETWEEN 2000 AND 2100),
    academic_year SMALLINT CHECK (academic_year BETWEEN 2000 AND 2100),
    expected_graduation_year SMALLINT
        CHECK (expected_graduation_year BETWEEN 2000 AND 2120),
    is_cr BOOLEAN NOT NULL DEFAULT FALSE,
    is_fr BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. Email OTP challenges; store only a hash of the OTP.
CREATE TABLE email_otp_challenges (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts(id),
    otp_hash BYTEA NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts SMALLINT NOT NULL DEFAULT 0
        CHECK (attempts BETWEEN 0 AND 10),
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_otp_account_expiry
    ON email_otp_challenges (account_id, expires_at);

-- 5. Elections
CREATE TABLE elections (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    election_type VARCHAR(30) NOT NULL
        CHECK (election_type IN (
            'CR', 'FR', 'PRESIDENT', 'TECHNICAL',
            'VICE_PRESIDENT', 'CULTURAL', 'SPORTS', 'OTHER'
        )),
    branch_id BIGINT REFERENCES branches(id),
    admission_year SMALLINT CHECK (admission_year BETWEEN 2000 AND 2100),
    academic_year SMALLINT CHECK (academic_year BETWEEN 2000 AND 2100),
    semester SMALLINT CHECK (semester BETWEEN 1 AND 12),
    duration_minutes INTEGER CHECK (duration_minutes BETWEEN 1 AND 10080),
    opens_at TIMESTAMPTZ NOT NULL,
    closes_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN (
            'DRAFT', 'SCHEDULED', 'OPEN', 'CLOSED', 'CANCELLED'
        )),
    created_by BIGINT NOT NULL REFERENCES accounts(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (closes_at > opens_at),
    CHECK (
        (election_type IN ('CR', 'FR')
            AND branch_id IS NOT NULL
            AND semester IS NOT NULL)
        OR election_type NOT IN ('CR', 'FR')
    ),
    CHECK (
        election_type NOT IN ('CR', 'FR')
        OR (admission_year IS NOT NULL AND duration_minutes IS NOT NULL)
    )
);

-- 6. Branches explicitly selected for college-wide elections
CREATE TABLE election_eligible_branches (
    election_id BIGINT NOT NULL
        REFERENCES elections(id) ON DELETE CASCADE,
    branch_id BIGINT NOT NULL REFERENCES branches(id),
    PRIMARY KEY (election_id, branch_id)
);

-- 7. Explicit voter eligibility for each election.
-- The backend populates this from approved eligibility rules.
CREATE TABLE voter_eligibility (
    election_id BIGINT NOT NULL
        REFERENCES elections(id) ON DELETE CASCADE,
    student_id BIGINT NOT NULL REFERENCES students(id),
    PRIMARY KEY (election_id, student_id)
);

-- 8. Candidates
CREATE TABLE candidates (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    election_id BIGINT NOT NULL
        REFERENCES elections(id) ON DELETE CASCADE,
    student_id BIGINT NOT NULL REFERENCES students(id),
    manifesto TEXT,
    symbol_key VARCHAR(32)
        CHECK (symbol_key IS NULL OR symbol_key IN (
            'book', 'compass', 'gear', 'lamp', 'leaf',
            'pen', 'shield', 'star', 'torch', 'tree'
        )),
    is_approved BOOLEAN NOT NULL DEFAULT FALSE,
    review_status VARCHAR(12) NOT NULL DEFAULT 'PENDING'
        CHECK (review_status IN ('PENDING', 'APPROVED', 'REJECTED')),
    reviewed_at TIMESTAMPTZ,
    reviewed_by BIGINT REFERENCES accounts(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (election_id, student_id),
    UNIQUE (id, election_id)
);

-- 9. Anonymous ballot box.
-- IMPORTANT: No student ID or USN is stored in this table.
CREATE TABLE ballots (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ballot_reference UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    election_id BIGINT NOT NULL REFERENCES elections(id),
    candidate_id BIGINT NOT NULL,
    cast_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (candidate_id, election_id)
        REFERENCES candidates(id, election_id),
    UNIQUE (id, election_id)
);

-- 10. Participation ledger.
-- This table prevents a student voting twice in one election.
-- It deliberately does not reference an individual ballot.
CREATE TABLE voter_participation (
    election_id BIGINT NOT NULL REFERENCES elections(id),
    student_id BIGINT NOT NULL REFERENCES students(id),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (election_id, student_id)
);

-- 11. Hash-linked audit log.
CREATE TABLE audit_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    election_id BIGINT REFERENCES elections(id),
    event_type VARCHAR(60) NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    previous_hash BYTEA,
    event_hash BYTEA NOT NULL,
    hash_version SMALLINT NOT NULL DEFAULT 2
        CHECK (hash_version IN (1, 2)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (octet_length(event_hash) = 32),
    CHECK (
        previous_hash IS NULL OR octet_length(previous_hash) = 32
    )
);

-- Activation links are opaque, one-time secrets. Only their SHA-256 hashes
-- are retained; the raw value exists only while an email is being composed.
CREATE TABLE IF NOT EXISTS student_activation_tokens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    token_hash BYTEA NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (octet_length(token_hash) = 32)
);

CREATE INDEX idx_students_branch_semester
    ON students (branch_id, semester);

CREATE INDEX idx_students_branch_academic
    ON students (branch_id, admission_year, academic_year, semester, id);

CREATE INDEX idx_elections_status_opening
    ON elections (status, opens_at, closes_at);

CREATE INDEX idx_candidates_election
    ON candidates (election_id);

CREATE INDEX idx_candidates_election_review
    ON candidates (election_id, review_status, is_approved, id);

CREATE UNIQUE INDEX uq_candidates_election_symbol_key
    ON candidates (election_id, symbol_key)
    WHERE symbol_key IS NOT NULL;

CREATE INDEX idx_ballots_election
    ON ballots (election_id);

CREATE INDEX idx_ballots_election_candidate
    ON ballots (election_id, candidate_id);

CREATE INDEX idx_voter_eligibility_student_election
    ON voter_eligibility (student_id, election_id);

CREATE INDEX idx_elections_branch_type_status
    ON elections (branch_id, election_type, status, id);

CREATE INDEX idx_audit_election
    ON audit_events (election_id, id);

CREATE INDEX idx_student_activation_account
    ON student_activation_tokens (account_id, expires_at);

-- Durable outbox for student invitations. Raw activation tokens are never
-- persisted here; the delivery worker creates a one-time token only when it
-- claims a job and stores only that token's hash in student_activation_tokens.
CREATE TABLE student_activation_email_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL UNIQUE
        REFERENCES accounts(id) ON DELETE CASCADE,
    status VARCHAR(12) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'PROCESSING', 'SENT', 'FAILED', 'CANCELLED')),
    attempts SMALLINT NOT NULL DEFAULT 0
        CHECK (attempts BETWEEN 0 AND 100),
    last_attempt_at TIMESTAMPTZ,
    locked_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ,
    failure_kind VARCHAR(24)
        CHECK (failure_kind IS NULL OR failure_kind IN (
            'TEMPORARY', 'TEMPORARY_EXHAUSTED', 'PERMANENT'
        )),
    last_error VARCHAR(250),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_student_activation_email_jobs_pending
    ON student_activation_email_jobs (status, created_at);

-- 12. Initial branch list
INSERT INTO branches (name, code) VALUES
    ('Computer Science and Engineering', 'CSE'),
    ('Electronics and Communication Engineering', 'ECE'),
    ('Electrical and Electronics Engineering', 'EEE'),
    ('Mechanical Engineering', 'MECH'),
    ('Civil Engineering', 'CIVIL'),
    ('Robotics', 'ROBOTICS'),
    ('Information Processing', 'IP'),
    ('Master of Computer Applications', 'MCA');

    
-- Secure password credentials for Principal and HOD accounts
CREATE TABLE IF NOT EXISTS account_credentials (
    account_id BIGINT PRIMARY KEY
        REFERENCES accounts(id) ON DELETE CASCADE,
    password_hash TEXT NOT NULL,
    password_changed_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);
-- Secure, one-time password-reset tokens
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL
        REFERENCES accounts(id) ON DELETE CASCADE,
    token_hash BYTEA NOT NULL UNIQUE,
    target_email VARCHAR(254),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_password_reset_account
    ON password_reset_tokens (account_id, expires_at);

COMMIT;
