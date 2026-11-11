-- Run this file separately with psql against an approved target. It contains
-- only additive indexes. PostgreSQL forbids CREATE INDEX CONCURRENTLY inside a
-- transaction block; do not wrap this file in BEGIN/COMMIT.
--
-- On a large production database, run during a controlled maintenance window
-- and monitor progress/IO. If an index build fails, resolve the cause and
-- rerun the individual statement; never drop application tables to retry.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_students_branch_academic
    ON students (branch_id, admission_year, semester, id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_voter_eligibility_student_election
    ON voter_eligibility (student_id, election_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candidates_election_review
    ON candidates (election_id, review_status, is_approved, id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ballots_election_candidate
    ON ballots (election_id, candidate_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_elections_branch_type_status
    ON elections (branch_id, election_type, status, id);
