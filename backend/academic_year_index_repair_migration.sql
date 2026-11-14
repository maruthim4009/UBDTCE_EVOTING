-- The historical performance-index migration used this index name before
-- academic_year became a cohort dimension. Keep that existing index intact
-- and add a correctly shaped one for HOD cohort filtering. This file is
-- non-transactional because it builds the index concurrently.
--
-- It does not alter or rewrite any student data.
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    idx_students_branch_admission_academic_semester
    ON students (branch_id, admission_year, academic_year, semester, id);
