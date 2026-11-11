BEGIN;

-- This migration is additive and safe for existing databases. It deliberately
-- never drops data, tables, or constraints.
ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS full_name VARCHAR(150);

ALTER TABLE students
    ADD COLUMN IF NOT EXISTS admission_year SMALLINT,
    ADD COLUMN IF NOT EXISTS expected_graduation_year SMALLINT;

ALTER TABLE elections
    ADD COLUMN IF NOT EXISTS admission_year SMALLINT,
    ADD COLUMN IF NOT EXISTS duration_minutes INTEGER,
    ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';

ALTER TABLE password_reset_tokens
    ADD COLUMN IF NOT EXISTS target_email VARCHAR(254);

CREATE TABLE IF NOT EXISTS student_activation_tokens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    token_hash BYTEA NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (octet_length(token_hash) = 32)
);

CREATE INDEX IF NOT EXISTS idx_student_activation_account
    ON student_activation_tokens (account_id, expires_at);

ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS review_status VARCHAR(12) NOT NULL DEFAULT 'PENDING',
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reviewed_by BIGINT REFERENCES accounts(id);

UPDATE candidates
SET review_status = CASE WHEN is_approved THEN 'APPROVED' ELSE 'PENDING' END
WHERE review_status IS NULL
   OR (is_approved = TRUE AND review_status <> 'APPROVED');

ALTER TABLE candidates
    DROP CONSTRAINT IF EXISTS candidates_review_status_check;

ALTER TABLE candidates
    ADD CONSTRAINT candidates_review_status_check
    CHECK (review_status IN ('PENDING', 'APPROVED', 'REJECTED'));

ALTER TABLE elections
    DROP CONSTRAINT IF EXISTS elections_class_admission_year_check;

ALTER TABLE elections
    ADD CONSTRAINT elections_class_admission_year_check
    CHECK (
        election_type NOT IN ('CR', 'FR')
        OR (admission_year BETWEEN 2000 AND 2100)
    ) NOT VALID;

ALTER TABLE elections
    DROP CONSTRAINT IF EXISTS elections_duration_check;

ALTER TABLE elections
    ADD CONSTRAINT elections_duration_check
    CHECK (
        (election_type IN ('CR', 'FR')
            AND duration_minutes BETWEEN 1 AND 10080)
        OR
        (election_type NOT IN ('CR', 'FR')
            AND (duration_minutes IS NULL OR duration_minutes BETWEEN 1 AND 10080))
    ) NOT VALID;

CREATE INDEX IF NOT EXISTS idx_participation_election
    ON voter_participation (election_id, recorded_at);

-- Durable, retryable activation-email outbox. It intentionally contains no
-- raw activation secret: a worker creates the secret at send time and only a
-- SHA-256 hash is retained in student_activation_tokens.
CREATE TABLE IF NOT EXISTS student_activation_email_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL UNIQUE
        REFERENCES accounts(id) ON DELETE CASCADE,
    status VARCHAR(12) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'PROCESSING', 'SENT', 'FAILED')),
    attempts SMALLINT NOT NULL DEFAULT 0
        CHECK (attempts BETWEEN 0 AND 100),
    last_attempt_at TIMESTAMPTZ,
    locked_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    last_error VARCHAR(250),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_student_activation_email_jobs_pending
    ON student_activation_email_jobs (status, created_at);

COMMIT;
