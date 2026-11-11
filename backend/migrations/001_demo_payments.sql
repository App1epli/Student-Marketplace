-- Additive upgrade for existing databases. Old purchases retain an explicit
-- unknown payment status; no old transaction is retroactively marked paid.
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'Not recorded';
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS payment_reference UUID;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_payment_method_check;
ALTER TABLE purchases ADD CONSTRAINT purchases_payment_method_check
    CHECK (payment_method IN ('Cash', 'Bank Transfer', 'Demo Card'));
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_payment_status_check;
ALTER TABLE purchases ADD CONSTRAINT purchases_payment_status_check
    CHECK (payment_status IN ('Not recorded', 'Pending', 'Demo paid'));
CREATE UNIQUE INDEX IF NOT EXISTS idx_purchases_payment_reference ON purchases(payment_reference);
