-- Transactional, additive compatibility migration for the college-wide
-- election categories exposed by the Flask API. It preserves historic rows
-- and never changes a ballot, participation, or eligibility record.
-- The migration runner owns BEGIN/COMMIT and its ledger insert for this file.

ALTER TABLE elections
    ADD COLUMN IF NOT EXISTS position_name VARCHAR(120);

-- Existing installations use PostgreSQL's default name for this schema CHECK.
-- NOT VALID preserves historic data while enforcing the policy for new rows.
ALTER TABLE elections
    DROP CONSTRAINT IF EXISTS elections_election_type_check;

ALTER TABLE elections
    ADD CONSTRAINT elections_election_type_check
    CHECK (election_type IN (
        'CR', 'FR', 'PRESIDENT', 'JOINT_SECRETARY', 'TECHNICAL',
        'VICE_PRESIDENT', 'CULTURAL', 'SPORTS', 'OTHER'
    )) NOT VALID;

ALTER TABLE elections
    DROP CONSTRAINT IF EXISTS elections_position_name_check;

ALTER TABLE elections
    ADD CONSTRAINT elections_position_name_check
    CHECK (
        position_name IS NULL
        OR char_length(btrim(position_name)) BETWEEN 1 AND 120
    ) NOT VALID;
