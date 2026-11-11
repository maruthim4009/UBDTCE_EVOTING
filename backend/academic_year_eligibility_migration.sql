BEGIN;

-- This migration is additive. Existing student and election rows retain a
-- NULL academic_year until an authorized administrator supplies verified data.
-- Do not infer or overwrite academic-year information from a USN.
ALTER TABLE students
    ADD COLUMN IF NOT EXISTS academic_year SMALLINT;

ALTER TABLE elections
    ADD COLUMN IF NOT EXISTS academic_year SMALLINT;

-- PostgreSQL does not support ADD CONSTRAINT IF NOT EXISTS. Guard the named
-- constraints explicitly so a tracked re-run is predictable and a database
-- initialized from the current schema is not rejected as a duplicate.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'students'::regclass
          AND conname = 'students_academic_year_check'
    ) THEN
        ALTER TABLE students
            ADD CONSTRAINT students_academic_year_check
            CHECK (academic_year IS NULL OR academic_year BETWEEN 2000 AND 2100)
            NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'elections'::regclass
          AND conname = 'elections_academic_year_check'
    ) THEN
        ALTER TABLE elections
            ADD CONSTRAINT elections_academic_year_check
            CHECK (academic_year IS NULL OR academic_year BETWEEN 2000 AND 2100)
            NOT VALID;
    END IF;
END $$;

-- This is the canonical cohort lookup index. Older dry runs used the longer
-- *_eligibility name, so recognize it instead of creating duplicate b-trees.
DO $$
BEGIN
    IF to_regclass('idx_students_branch_academic') IS NULL
       AND to_regclass('idx_students_branch_academic_eligibility') IS NULL THEN
        CREATE INDEX idx_students_branch_academic
            ON students (branch_id, admission_year, academic_year, semester, id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_elections_branch_cohort_status
    ON elections (branch_id, admission_year, academic_year, semester, status, id);

COMMIT;
