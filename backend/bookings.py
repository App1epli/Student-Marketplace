"""Booking operations share the product row lock used by checkout."""
from backend.payments import CheckoutError, positive_id


def reserve(conn, product_id, student_id):
    product_id, student_id = positive_id(product_id), positive_id(student_id)
    product = conn.execute('SELECT seller_id, status FROM products WHERE product_id=? FOR UPDATE', (product_id,)).fetchone()
    if not product:
        raise CheckoutError('This item was not found.', 404)
    if product['seller_id'] == student_id:
        raise CheckoutError('You cannot book your own item.')
    if product['status'] != 'Available':
        raise CheckoutError('This item is no longer available.', 409)
    active = conn.execute('SELECT student_id FROM product_bookings WHERE product_id=? AND expires_at>CURRENT_TIMESTAMP', (product_id,)).fetchone()
    if active:
        if active['student_id'] != student_id:
            raise CheckoutError('Another student has already booked this item.', 409)
        return
    conn.execute('''INSERT INTO product_bookings (product_id, student_id) VALUES (?, ?)
        ON CONFLICT (product_id) DO UPDATE SET student_id=EXCLUDED.student_id,
        created_at=CURRENT_TIMESTAMP, expires_at=CURRENT_TIMESTAMP + INTERVAL '24 hours' ''', (product_id, student_id))


def cancel(conn, product_id, student_id):
    product_id, student_id = positive_id(product_id), positive_id(student_id)
    product = conn.execute('SELECT seller_id FROM products WHERE product_id=? FOR UPDATE', (product_id,)).fetchone()
    if not product:
        raise CheckoutError('This item was not found.', 404)
    booking = conn.execute('SELECT student_id FROM product_bookings WHERE product_id=?', (product_id,)).fetchone()
    if not booking:
        return
    if student_id not in (booking['student_id'], product['seller_id']):
        raise CheckoutError('Only the buyer or seller can cancel this booking.', 403)
    conn.execute('DELETE FROM product_bookings WHERE product_id=?', (product_id,))
