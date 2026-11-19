
ALTER TABLE purchases
ADD COLUMN platform_fee NUMERIC(10,2)
NOT NULL DEFAULT 0
CHECK (platform_fee >= 0);

ALTER TABLE purchases
ADD COLUMN seller_payout NUMERIC(10,2);

ALTER TABLE purchases
ADD COLUMN commission_rate NUMERIC(5,4)
NOT NULL DEFAULT 0;

UPDATE purchases
SET seller_payout = agreed_price
WHERE seller_payout IS NULL;

ALTER TABLE purchases
ALTER COLUMN seller_payout SET NOT NULL;

ALTER TABLE purchases
ADD CONSTRAINT seller_payout_nonnegative
CHECK (seller_payout >= 0);

ALTER TABLE purchases
ADD CONSTRAINT seller_amounts_consistent
CHECK (seller_payout + platform_fee = agreed_price);
