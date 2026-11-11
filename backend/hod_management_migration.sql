BEGIN;

-- Make the HOD management update safe to apply to an existing UBDTCE database.
ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS full_name VARCHAR(150);

-- A department can have one HOD, and an HOD can belong to one department.
CREATE TABLE IF NOT EXISTS hod_assignments (
    account_id BIGINT PRIMARY KEY
        REFERENCES accounts(id) ON DELETE CASCADE,
    branch_id BIGINT NOT NULL UNIQUE
        REFERENCES branches(id) ON DELETE CASCADE
);

-- Existing project installations may predate this credentials table.
CREATE TABLE IF NOT EXISTS account_credentials (
    account_id BIGINT PRIMARY KEY
        REFERENCES accounts(id) ON DELETE CASCADE,
    password_hash TEXT NOT NULL,
    password_changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One-time invitation tokens used only for the HOD's initial password setup.
CREATE TABLE IF NOT EXISTS hod_setup_tokens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    branch_id BIGINT NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    target_email VARCHAR(254) NOT NULL,
    token_hash BYTEA NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (octet_length(token_hash) = 32)
);

CREATE INDEX IF NOT EXISTS idx_hod_setup_account_expiry
    ON hod_setup_tokens (account_id, expires_at);

CREATE INDEX IF NOT EXISTS idx_hod_setup_target_email
    ON hod_setup_tokens (LOWER(target_email), expires_at);

COMMIT;
