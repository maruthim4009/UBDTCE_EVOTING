BEGIN;

-- This migration is additive. It does not delete or rewrite student, ballot,
-- or election records. Apply it once, after the earlier additive migrations,
-- before deploying the corresponding application version.

ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS symbol_key VARCHAR(32);

ALTER TABLE candidates
    DROP CONSTRAINT IF EXISTS candidates_symbol_key_check;

ALTER TABLE candidates
    ADD CONSTRAINT candidates_symbol_key_check
    CHECK (
        symbol_key IS NULL OR symbol_key IN (
            'book', 'compass', 'gear', 'lamp', 'leaf',
            'pen', 'shield', 'star', 'torch', 'tree'
        )
    ) NOT VALID;

-- Existing candidates deliberately remain NULL: silently assigning a symbol
-- would change an existing election's published presentation. New candidates
-- are validated by the API and must be unique per election.
CREATE UNIQUE INDEX IF NOT EXISTS uq_candidates_election_symbol_key
    ON candidates (election_id, symbol_key)
    WHERE symbol_key IS NOT NULL;

ALTER TABLE audit_events
    ADD COLUMN IF NOT EXISTS hash_version SMALLINT NOT NULL DEFAULT 1;

ALTER TABLE audit_events
    DROP CONSTRAINT IF EXISTS audit_events_hash_version_check;

ALTER TABLE audit_events
    ADD CONSTRAINT audit_events_hash_version_check
    CHECK (hash_version IN (1, 2)) NOT VALID;

ALTER TABLE student_activation_email_jobs
    ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS failure_kind VARCHAR(24);

ALTER TABLE student_activation_email_jobs
    DROP CONSTRAINT IF EXISTS student_activation_email_jobs_failure_kind_check;

ALTER TABLE student_activation_email_jobs
    ADD CONSTRAINT student_activation_email_jobs_failure_kind_check
    CHECK (failure_kind IS NULL OR failure_kind IN (
        'TEMPORARY', 'TEMPORARY_EXHAUSTED', 'PERMANENT'
    )) NOT VALID;

CREATE INDEX IF NOT EXISTS idx_student_activation_email_jobs_ready
    ON student_activation_email_jobs (status, next_attempt_at, created_at)
    WHERE status = 'PENDING';

COMMIT;
