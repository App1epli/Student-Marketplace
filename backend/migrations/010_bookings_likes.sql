CREATE TABLE IF NOT EXISTS liked_products (
    student_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, product_id)
);
CREATE TABLE IF NOT EXISTS product_bookings (
    product_id INTEGER PRIMARY KEY REFERENCES products(product_id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP + INTERVAL '24 hours'),
    CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_bookings_student ON product_bookings(student_id, expires_at);
