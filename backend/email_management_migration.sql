BEGIN;

-- Store one additional email address for each account.
-- The existing accounts.email remains the original account email.
CREATE TABLE IF NOT EXISTS account_email_addresses (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    account_id BIGINT NOT NULL
        REFERENCES accounts(id) ON DELETE CASCADE,

    email VARCHAR(254) NOT NULL,

    is_verified BOOLEAN NOT NULL DEFAULT FALSE,

    verified_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_account_email_addresses_account
        UNIQUE (account_id),

    CONSTRAINT chk_account_email_verified_at
        CHECK (
            (is_verified = FALSE AND verified_at IS NULL)
            OR
            (is_verified = TRUE AND verified_at IS NOT NULL)
        )
);

-- Prevent duplicate secondary email addresses, ignoring case.
CREATE UNIQUE INDEX IF NOT EXISTS
    uq_account_email_addresses_email_lower
ON account_email_addresses (LOWER(email));

-- Associate each OTP challenge with the address being verified.
ALTER TABLE email_otp_challenges
ADD COLUMN IF NOT EXISTS target_email VARCHAR(254);

CREATE INDEX IF NOT EXISTS
    idx_email_otp_account_target_expiry
ON email_otp_challenges (
    account_id,
    target_email,
    expires_at
);

COMMIT;

-- Allow a separate password for the additional email.
ALTER TABLE account_email_addresses
ADD COLUMN IF NOT EXISTS password_hash TEXT;





