-- Store only masked demo-card metadata. PAN and CVV are never persisted.
CREATE TABLE IF NOT EXISTS demo_cards (
    card_id UUID PRIMARY KEY,
    wallet_hash TEXT NOT NULL CHECK (wallet_hash ~ '^[0-9a-f]{64}$'),
    buyer_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    holder_name TEXT NOT NULL CHECK (length(trim(holder_name)) BETWEEN 2 AND 80),
    last4 TEXT NOT NULL CHECK (last4 = '4242'),
    expiry_month INTEGER NOT NULL CHECK (expiry_month BETWEEN 1 AND 12),
    expiry_year INTEGER NOT NULL CHECK (expiry_year BETWEEN 2000 AND 2099),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (wallet_hash, buyer_id)
);
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS card_last4 TEXT CHECK (card_last4 = '4242');
