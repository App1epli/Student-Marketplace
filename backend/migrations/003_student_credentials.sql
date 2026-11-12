-- Student login credentials, linked to existing student records.
-- Additive only: no existing tables or rows are modified.
CREATE TABLE IF NOT EXISTS student_credentials (
    student_id INTEGER PRIMARY KEY REFERENCES students(student_id) ON UPDATE CASCADE ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE CHECK (email = lower(trim(email)) AND strpos(email, '@') > 1),
    password_hash TEXT NOT NULL CHECK (length(password_hash) > 0),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_student_credentials_email ON student_credentials(email);
