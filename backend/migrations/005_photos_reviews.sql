CREATE TABLE IF NOT EXISTS product_photos (
    photo_id UUID PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    image_data BYTEA NOT NULL CHECK (octet_length(image_data) <= 1048576),
    position INTEGER NOT NULL CHECK (position BETWEEN 0 AND 2),
    UNIQUE(product_id, position)
);
CREATE INDEX IF NOT EXISTS idx_product_photos_product ON product_photos(product_id);
CREATE TABLE IF NOT EXISTS seller_reviews (
    purchase_id INTEGER PRIMARY KEY REFERENCES purchases(purchase_id) ON DELETE CASCADE,
    stars INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5),
    comment TEXT NOT NULL DEFAULT '' CHECK (length(comment) <= 500),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
