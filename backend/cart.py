"""Shopping cart storage and helpers.

Supports authenticated students (PostgreSQL cart_items table with foreign keys)
and guest sessions (Flask session cookie).
"""
from __future__ import annotations

from flask import session
from backend import database


def get_cart_count(student_id: int | None) -> int:
    """Return count of items in cart."""
    if student_id:
        try:
            with database.connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM cart_items WHERE student_id = ?",
                    (student_id,)
                ).fetchone()
                return int(row[0]) if row else 0
        except Exception:
            return 0
    guest_cart = session.get("guest_cart", [])
    return len(guest_cart)


def get_cart_product_ids(student_id: int | None) -> set[int]:
    """Return set of product_ids currently in user's cart."""
    if student_id:
        try:
            with database.connect() as conn:
                rows = conn.execute(
                    "SELECT product_id FROM cart_items WHERE student_id = ?",
                    (student_id,)
                ).fetchall()
                return {int(r["product_id"]) for r in rows}
        except Exception:
            return set()
    return set(session.get("guest_cart", []))


def add_to_cart(product_id: int, student_id: int | None) -> bool:
    """Add a product to cart. Returns True if added, False if already in cart."""
    if student_id:
        with database.connect() as conn:
            # Check if already in cart
            existing = conn.execute(
                "SELECT 1 FROM cart_items WHERE student_id = ? AND product_id = ?",
                (student_id, product_id)
            ).fetchone()
            if existing:
                return False
            conn.execute(
                """INSERT INTO cart_items (student_id, product_id)
                   VALUES (?, ?)
                   ON CONFLICT (student_id, product_id) DO NOTHING""",
                (student_id, product_id)
            )
            return True
    else:
        cart = list(session.get("guest_cart", []))
        if product_id not in cart:
            cart.append(product_id)
            session["guest_cart"] = cart
            session.modified = True
            return True
        return False


def remove_from_cart(product_id: int, student_id: int | None) -> None:
    """Remove a product from cart."""
    if student_id:
        with database.connect() as conn:
            conn.execute(
                "DELETE FROM cart_items WHERE student_id = ? AND product_id = ?",
                (student_id, product_id)
            )
    else:
        cart = [pid for pid in session.get("guest_cart", []) if pid != product_id]
        session["guest_cart"] = cart
        session.modified = True


def get_cart_details(student_id: int | None) -> tuple[list[dict], float]:
    """
    Return list of full product dicts in cart and total price.
    Also automatically cleans up any products that have been deleted or sold.
    """
    product_ids = get_cart_product_ids(student_id)
    if not product_ids:
        return [], 0.0

    with database.connect() as conn:
        placeholders = ", ".join(["?"] * len(product_ids))
        query = f"""
            SELECT p.product_id, p.product_name, p.description, p.price,
                   p.item_condition, p.status, p.seller_id,
                   s.full_name AS seller, c.category_name,
                   (SELECT photo_id FROM product_photos
                    WHERE product_id = p.product_id
                    ORDER BY position ASC, photo_id ASC LIMIT 1) AS photo_id
            FROM products p
            JOIN students s ON s.student_id = p.seller_id
            JOIN categories c ON c.category_id = p.category_id
            WHERE p.product_id IN ({placeholders})
            ORDER BY p.product_name ASC
        """
        rows = conn.execute(query, tuple(product_ids)).fetchall()

    items = [dict(r) for r in rows]
    total_price = sum(float(item["price"]) for item in items if item["status"] == "Available")
    return items, total_price


def sync_guest_cart(student_id: int) -> None:
    """Merge guest cart items into database when student logs in."""
    guest_cart = session.pop("guest_cart", [])
    if not guest_cart or not student_id:
        return
    with database.connect() as conn:
        for product_id in guest_cart:
            conn.execute(
                """INSERT INTO cart_items (student_id, product_id)
                   VALUES (?, ?)
                   ON CONFLICT (student_id, product_id) DO NOTHING""",
                (student_id, product_id)
            )
