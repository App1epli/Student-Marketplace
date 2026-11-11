"""A browser-scoped demo wallet; only the published test card is accepted."""
from datetime import datetime, timezone
import re

from backend.payments import CheckoutError, positive_id

TEST_CARD_NUMBER = "4242424242424242"
TEST_CVV = "123"


def current_month():
    now = datetime.now(timezone.utc)
    return now.year, now.month


def validate_demo_card(data):
    """Validate transient test inputs and return only display-safe metadata."""
    number = data.get("number", "")
    name = data.get("holder_name", "")
    expiry = data.get("expiry", "")
    cvv = data.get("cvv", "")
    if not all(isinstance(value, str) for value in (number, name, expiry, cvv)):
        raise CheckoutError("Enter valid demo card details.")
    if not re.fullmatch(r"[0-9 -]{16,23}", number) or re.sub(r"[ -]", "", number) != TEST_CARD_NUMBER:
        raise CheckoutError("Use the test card 4242 4242 4242 4242. Real cards are not accepted.")
    name = " ".join(name.split())
    if not 2 <= len(name) <= 80 or any(not (c.isalpha() or c in " '-.") for c in name):
        raise CheckoutError("Enter a cardholder name using 2–80 letters, spaces, apostrophes or hyphens.")
    match = re.fullmatch(r"(0[1-9]|1[0-2])\s*/\s*([0-9]{2})", expiry.strip())
    if not match:
        raise CheckoutError("Enter the expiry date as MM/YY.")
    month, year = int(match[1]), 2000 + int(match[2])
    if (year, month) < current_month():
        raise CheckoutError("This test card has expired. Enter a current or future expiry date.")
    if cvv != TEST_CVV:
        raise CheckoutError("Use the demo CVV 123.")
    return dict(holder_name=name, last4="4242", expiry_month=month, expiry_year=year)


def public_card(row):
    if not row:
        return None
    return dict(card_id=str(row["card_id"]), holder_name=row["holder_name"], last4=row["last4"],
                expiry=f'{row["expiry_month"]:02}/{row["expiry_year"] % 100:02}',
                expired=(row["expiry_year"], row["expiry_month"]) < current_month())


def get_card(conn, buyer_id, wallet_hash):
    buyer_id = positive_id(buyer_id)
    return public_card(conn.execute("""SELECT card_id, holder_name, last4, expiry_month, expiry_year
        FROM demo_cards WHERE buyer_id=? AND wallet_hash=?""", (buyer_id, wallet_hash)).fetchone())


def add_card(conn, data, wallet_hash):
    from uuid import uuid4
    buyer_id = positive_id(data.get("buyer_id"))
    card = validate_demo_card(data)
    if not conn.execute("SELECT 1 FROM students WHERE student_id=?", (buyer_id,)).fetchone():
        raise CheckoutError("Select a buyer from the list.")
    row = conn.execute("""INSERT INTO demo_cards
        (card_id, wallet_hash, buyer_id, holder_name, last4, expiry_month, expiry_year)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (wallet_hash, buyer_id) DO UPDATE SET
            holder_name=EXCLUDED.holder_name, expiry_month=EXCLUDED.expiry_month,
            expiry_year=EXCLUDED.expiry_year
        RETURNING card_id, holder_name, last4, expiry_month, expiry_year""",
        (str(uuid4()), wallet_hash, buyer_id, card["holder_name"], card["last4"], card["expiry_month"], card["expiry_year"])).fetchone()
    return public_card(row)
