BEGIN;

-- This migration is additive. Existing student and election rows retain a
-- NULL academic_year until an authorized administrator supplies verified data.
-- Do not infer or overwrite academic-year information from a USN.
ALTER TABLE students
    ADD COLUMN IF NOT EXISTS academic_year SMALLINT;

ALTER TABLE elections
    ADD COLUMN IF NOT EXISTS academic_year SMALLINT;

ALTER TABLE students
    ADD CONSTRAINT students_academic_year_check
    CHECK (academic_year IS NULL OR academic_year BETWEEN 2000 AND 2100)
    NOT VALID;

ALTER TABLE elections
    ADD CONSTRAINT elections_academic_year_check
    CHECK (academic_year IS NULL OR academic_year BETWEEN 2000 AND 2100)
    NOT VALID;

CREATE INDEX IF NOT EXISTS idx_students_branch_academic_eligibility
    ON students (branch_id, admission_year, academic_year, semester, id);

CREATE INDEX IF NOT EXISTS idx_elections_branch_cohort_status
    ON elections (branch_id, admission_year, academic_year, semester, status, id);

COMMIT;
