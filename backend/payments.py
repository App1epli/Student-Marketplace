"""Classroom payment simulator. A saved test card is required; no money moves."""
from uuid import UUID

PAYMENT_METHODS = ("Demo Card",)


class CheckoutError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def positive_id(value):
    try:
        number = int(value)
        if not 0 < number <= 2147483647:
            raise ValueError
        return number
    except (ValueError, TypeError):
        raise CheckoutError("Select a valid buyer and item.") from None


def demo_buyer_id(form):
    """Integration point: replace form selection with the authenticated student ID."""
    return positive_id(form.get("buyer_id"))


def complete_purchase(conn, *, product_id, buyer_id, method, reference, card_id=None, wallet_hash=None, outcome="approved"):
    """Create a demo purchase atomically; a replay returns the original receipt.

    The caller owns the transaction. Amounts and availability always come from
    PostgreSQL. Declined attempts raise before any purchase or stock change.
    """
    product_id, buyer_id = positive_id(product_id), positive_id(buyer_id)
    try:
        reference = str(UUID(str(reference)))
    except (ValueError, TypeError, AttributeError):
        raise CheckoutError("This checkout link is invalid. Open checkout again.") from None
    if method not in PAYMENT_METHODS or outcome not in ("approved", "declined"):
        raise CheckoutError("Add a demo card to buy this item.")
    try:
        card_id = str(UUID(str(card_id)))
    except (ValueError, TypeError, AttributeError):
        raise CheckoutError("Add a card before buying this item.") from None

    from backend.cards import current_month
    # A guessed card ID, another student's card, and another browser's card
    # must never unlock checkout. Lock also serializes card removal/replacement.
    card = conn.execute("""SELECT * FROM demo_cards
        WHERE card_id=? AND buyer_id=? AND wallet_hash=? FOR UPDATE""",
        (card_id, buyer_id, wallet_hash)).fetchone()
    if not card:
        raise CheckoutError("Add a card for this buyer in this browser before buying.")
    if (card["expiry_year"], card["expiry_month"]) < current_month():
        raise CheckoutError("Your saved test card has expired. Add a new card.")

    # Serialize reuse of a reference, including requests for different items.
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(?, 0))", (reference,))
    existing = conn.execute("SELECT * FROM purchases WHERE payment_reference=?", (reference,)).fetchone()
    if existing:
        if (existing["product_id"], existing["buyer_id"], existing["payment_method"]) != (product_id, buyer_id, method):
            raise CheckoutError("This checkout was already used. Open a new checkout.", 409)
        return reference

    product = conn.execute("SELECT * FROM products WHERE product_id=? FOR UPDATE", (product_id,)).fetchone()
    if not product or product["status"] != "Available":
        raise CheckoutError("This listing is no longer available. Choose another item.", 409)
    if product["seller_id"] == buyer_id:
        raise CheckoutError("You cannot buy your own listing.")
    if not conn.execute("SELECT 1 FROM students WHERE student_id=?", (buyer_id,)).fetchone():
        raise CheckoutError("Select a buyer from the list.")
    if outcome == "declined":
        raise CheckoutError("Demo payment declined. No money was charged and the item is still available. Choose Approved to try again.", 402)

    conn.execute("""INSERT INTO purchases
        (buyer_id, product_id, agreed_price, payment_method, payment_status, payment_reference, card_last4)
        VALUES (?, ?, ?, ?, ?, ?, ?)""", (buyer_id, product_id, product["price"], method, "Demo paid", reference, card["last4"]))
    changed = conn.execute("UPDATE products SET status='Sold' WHERE product_id=? AND status='Available'", (product_id,)).rowcount
    if changed != 1:
        raise CheckoutError("This listing is no longer available.", 409)
    return reference
