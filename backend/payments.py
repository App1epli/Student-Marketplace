"""Classroom payment simulator. No payment provider or card data is used."""
from uuid import UUID

PAYMENT_METHODS = ("Demo Card", "Bank Transfer", "Cash")


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


def complete_purchase(conn, *, product_id, buyer_id, method, reference, outcome="approved"):
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
        raise CheckoutError("Choose a supported payment method and demo result.")

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
    if method != "Cash" and outcome == "declined":
        raise CheckoutError("Demo payment declined. No money was charged and the item is still available. Choose Approved to try again.", 402)

    status = "Pending" if method == "Cash" else "Demo paid"
    conn.execute("""INSERT INTO purchases
        (buyer_id, product_id, agreed_price, payment_method, payment_status, payment_reference)
        VALUES (?, ?, ?, ?, ?, ?)""", (buyer_id, product_id, product["price"], method, status, reference))
    changed = conn.execute("UPDATE products SET status='Sold' WHERE product_id=? AND status='Available'", (product_id,)).rowcount
    if changed != 1:
        raise CheckoutError("This listing is no longer available.", 409)
    return reference
