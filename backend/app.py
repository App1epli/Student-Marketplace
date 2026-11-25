"""Flask entrypoint shared by local development and Vercel."""
from __future__ import annotations

import argparse
import os
import hashlib
import re
import secrets
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from flask import Flask, Response, g, redirect, render_template, request, send_from_directory, url_for
from flask_wtf.csrf import CSRFProtect

from backend import auth, cart, messaging, bookings
from backend.database import connect, initialize_database, migrate_database, psycopg2
from backend.payments import CheckoutError, complete_purchase, demo_buyer_id
from backend.cards import add_card, get_card
from backend.media import prepare_photos
from backend.session_config import PersistentSessionInterface

ROOT = Path(__file__).resolve().parents[1]
app = Flask(__name__, template_folder=str(ROOT / "frontend/templates"), static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 3 * 1048576 + 100_000
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    app.session_interface = PersistentSessionInterface()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=bool(os.environ.get("VERCEL")))
csrf = CSRFProtect(app)
app.register_blueprint(auth.bp)
app.register_blueprint(messaging.bp)
CONDITIONS = ("New", "Like New", "Good", "Fair")
STATUSES = ("Available", "Sold", "Removed", "All")


@app.context_processor
def inject_cart():
    user = auth.current_student()
    return {"cart_count": cart.get_cart_count(user["student_id"] if user else None)}

PROMOTION_PLANS = {
    1: Decimal("200.00"),
    3: Decimal("500.00"),
    7: Decimal("900.00")
}


def wallet_hash():
    """Opaque guest wallet cookie; no account, signing key or client storage needed."""
    if not hasattr(g, "wallet_token"):
        token = request.cookies.get("demo_wallet", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            token = secrets.token_urlsafe(32)
            g.new_wallet = True
        g.wallet_token = token
    return hashlib.sha256(g.wallet_token.encode()).hexdigest()


@app.template_filter("money")
def money(value):
    return f"{value:,.2f}".replace(",", " ") + " ₸"


@app.after_request
def response_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    if response.mimetype not in ("text/css", "image/jpeg"):
        response.headers["Cache-Control"] = "no-store"
    if getattr(g, "new_wallet", False):
        response.set_cookie("demo_wallet", g.wallet_token, max_age=30 * 24 * 60 * 60,
                            httponly=True, secure=request.is_secure or bool(os.environ.get("VERCEL")), samesite="Lax")
    return response


@app.get("/static/<path:filename>")
def static_asset(filename):
    # Local fallback. Vercel serves build-copied public/static files from its CDN.
    return send_from_directory(ROOT / "frontend/static", filename)


@app.get("/api/health")
def health():
    with connect() as conn:
        conn.execute("SELECT 1 FROM students LIMIT 1")
        applied = {row[0] for row in conn.execute('SELECT version FROM schema_migrations')}
        pending = sorted(file.name for file in (ROOT / 'backend/migrations').glob('*.sql') if file.name not in applied)
        if pending:
            return {'status': 'unavailable', 'database': 'connected', 'schema': 'migration_required'}, 503
    return {"status": "ok", "database": "ok"}


@app.get("/")
def catalog():
    user = auth.current_student()
    mine = request.args.get("scope") == "mine"
    liked = request.args.get("scope") == "liked"
    booked = request.args.get("scope") == "booked"
    if (mine or liked or booked) and not user:
        return redirect(url_for("auth.login", next=url_for('catalog', scope=request.args.get('scope'), status='All')))
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "All" if liked else "Available")
    if status not in STATUSES:
        status = "Available"
    category = request.args.get("category", "")
    try:
        category_id = int(category)
        if not 0 < category_id <= 2147483647:
            raise ValueError
        category = str(category_id)
    except ValueError:
        category = ""
    clauses, args = [], []
    if mine:
        clauses.append("p.seller_id = ?")
        args.append(user["student_id"])
    if liked:
        clauses.append('EXISTS (SELECT 1 FROM liked_products WHERE product_id=p.product_id AND student_id=?)')
        args.append(user['student_id'])
    if booked:
        clauses.append('EXISTS (SELECT 1 FROM product_bookings WHERE product_id=p.product_id AND student_id=? AND expires_at>CURRENT_TIMESTAMP)')
        args.append(user['student_id'])
    if status != "All":
        clauses.append("p.status = ?")
        args.append(status)
    if category:
        clauses.append("p.category_id = ?")
        args.append(int(category))
    if search:
        clauses.append("(p.product_name LIKE ? OR p.description LIKE ? OR c.category_name LIKE ? OR s.full_name LIKE ?)")
        args.extend([f"%{search}%"] * 4)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as conn:
        categories = conn.execute("SELECT category_id, category_name FROM categories WHERE is_active ORDER BY category_name").fetchall()
        people = conn.execute("SELECT student_id, full_name FROM students ORDER BY full_name").fetchall()
        rows = conn.execute("""SELECT p.product_id, p.product_name, p.description, p.price,
            p.item_condition, p.status, c.category_name, s.full_name AS seller, s.student_id AS seller_id,
            (SELECT photo_id FROM product_photos ph WHERE ph.product_id=p.product_id ORDER BY position LIMIT 1) AS photo_id,
            EXISTS (SELECT 1 FROM liked_products WHERE product_id=p.product_id AND student_id=?) AS liked,
            (SELECT student_id FROM product_bookings WHERE product_id=p.product_id AND expires_at>CURRENT_TIMESTAMP) AS booked_by,
            (SELECT expires_at FROM product_bookings WHERE product_id=p.product_id AND expires_at>CURRENT_TIMESTAMP) AS booking_expires,
            (SELECT ROUND(AVG(stars),1) FROM product_ratings WHERE product_id=p.product_id) AS product_rating,
            (SELECT COUNT(*) FROM product_ratings WHERE product_id=p.product_id) AS product_rating_count,
            (SELECT stars FROM product_ratings WHERE product_id=p.product_id AND student_id=?) AS my_stars,
            (SELECT ROUND(AVG(rv.stars),1) FROM seller_reviews rv JOIN purchases pu ON pu.purchase_id=rv.purchase_id
                JOIN products pr ON pr.product_id=pu.product_id WHERE pr.seller_id=s.student_id) AS rating,
            (SELECT COUNT(*) FROM seller_reviews rv JOIN purchases pu ON pu.purchase_id=rv.purchase_id
                JOIN products pr ON pr.product_id=pu.product_id WHERE pr.seller_id=s.student_id) AS review_count
            FROM products p JOIN categories c ON c.category_id=p.category_id
            JOIN students s ON s.student_id=p.seller_id""" + where +
            " ORDER BY CASE p.status WHEN 'Available' THEN 0 ELSE 1 END, p.price, p.product_id", [user["student_id"] if user else None]*2 + args).fetchall()
        counts = {row["status"]: row["n"] for row in conn.execute("SELECT status, COUNT(*) AS n FROM products GROUP BY status")}

        hot_offers = conn.execute(
            """
            SELECT DISTINCT
                p.product_id,
                p.product_name,
                p.price
            FROM products p
            JOIN listing_promotions lp
                ON lp.product_id = p.product_id
            WHERE p.status = 'Available'
              AND lp.starts_at <= CURRENT_TIMESTAMP
              AND lp.expires_at > CURRENT_TIMESTAMP
            ORDER BY p.product_id DESC
            LIMIT 6
            """
        ).fetchall()

    return render_template("catalog.html", title="Marketplace catalog", rows=rows,hot_offers=hot_offers,
                           categories=categories, people=people, counts=counts,
                           search=search, status=status, category=category,
                           conditions=CONDITIONS, statuses=STATUSES,
                           cart_product_ids=cart.get_cart_product_ids(user["student_id"] if user else None),
                           mine=mine, liked=liked, booked=booked, notice=request.args.get("notice", ""))


@app.get("/sales")
def sales():
    search = request.args.get("q", "").strip()
    method = request.args.get("method", "").strip()
    status_filter = request.args.get("status", "").strip()
    clauses, args = [], []
    if search and len(search) >= 2:
        for word in search.split():
            term = f"%{word}%"
            clauses.append(
                "(LOWER(p.product_name) LIKE LOWER(?)"
                " OR LOWER(buyer.full_name) LIKE LOWER(?)"
                " OR LOWER(seller.full_name) LIKE LOWER(?)"
                " OR LOWER(COALESCE(pu.payment_reference::text,'')) LIKE LOWER(?))"
            )
            args.extend([term, term, term, term])
    if method:
        clauses.append("pu.payment_method = ?")
        args.append(method)
    if status_filter:
        clauses.append("pu.payment_status = ?")
        args.append(status_filter)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect() as conn:
        total_count = conn.execute("SELECT COUNT(*) FROM purchases").fetchone()[0]
        rows = conn.execute("""SELECT pu.purchase_id, pu.purchase_date, pu.agreed_price,
            pu.payment_method, pu.payment_status, pu.payment_reference, pu.buyer_id, pu.product_id,
            (SELECT stars FROM seller_reviews WHERE purchase_id=pu.purchase_id) AS review_stars,
            buyer.full_name AS buyer, p.product_name, seller.full_name AS seller
            FROM purchases pu JOIN students buyer ON buyer.student_id = pu.buyer_id
            JOIN products p ON p.product_id = pu.product_id
            JOIN students seller ON seller.student_id = p.seller_id""" + where +
            " ORDER BY pu.purchase_date DESC, pu.purchase_id DESC", args).fetchall()
        payment_methods = [r[0] for r in conn.execute(
            "SELECT DISTINCT payment_method FROM purchases ORDER BY payment_method")]
        payment_statuses = [r[0] for r in conn.execute(
            "SELECT DISTINCT payment_status FROM purchases ORDER BY payment_status")]
    return render_template("sales.html", title="Purchase history", rows=rows,
                           search=search, method=method, status_filter=status_filter,
                           payment_methods=payment_methods, payment_statuses=payment_statuses,
                           total_count=total_count)


def checkout_page(product_id, *, error="", status=200, form=None):
    form = form or {}
    wallet_hash()
    with connect() as conn:
        product = conn.execute("""SELECT p.*, s.full_name AS seller, c.category_name
            FROM products p JOIN students s ON s.student_id=p.seller_id
            JOIN categories c ON c.category_id=p.category_id WHERE product_id=?""", (product_id,)).fetchone()
        if not product:
            return not_found(None)
        booking = conn.execute('SELECT student_id, expires_at FROM product_bookings WHERE product_id=? AND expires_at>CURRENT_TIMESTAMP', (product_id,)).fetchone()
        people = conn.execute("SELECT student_id, full_name FROM students WHERE student_id<>? ORDER BY full_name", (product["seller_id"],)).fetchall()
    user = auth.current_student()
    booking_allowed = not booking or (user and user['student_id'] == booking['student_id'])
    if booking and booking_allowed:
        people = [person for person in people if person['student_id'] == booking['student_id']]
    return render_template("checkout.html", title="Checkout", product=product, people=people,
                           reference=form.get("payment_reference") or str(uuid4()),
                           booking_allowed=booking_allowed, booking=booking,
                           buyer_id=form.get("buyer_id", str(user['student_id']) if user and booking else ""), method=form.get("payment_method", "Demo Card"),
                           outcome=form.get("demo_result", "approved"), error=error), status


@app.get("/checkout/<int:product_id>")
def checkout(product_id):
    if not 0 < product_id <= 2147483647:
        return not_found(None)
    return checkout_page(product_id)


@app.post("/checkout/<int:product_id>")
def checkout_submit(product_id):
    if not 0 < product_id <= 2147483647:
        return not_found(None)
    try:
        with connect() as conn:
            reference = complete_purchase(conn, product_id=product_id, buyer_id=demo_buyer_id(request.form),
                authenticated_buyer_id=auth.current_student()['student_id'] if auth.current_student() else None,
                method=request.form.get("payment_method", ""),
                card_id=request.form.get("card_id"), wallet_hash=wallet_hash(),
                reference=request.form.get("payment_reference", ""), outcome=request.form.get("demo_result", "approved"))
    except CheckoutError as exc:
        return checkout_page(product_id, error=str(exc), status=exc.status, form=request.form)
    except psycopg2.IntegrityError:
        return checkout_page(product_id, error="The purchase could not be completed. Please refresh and try again.", status=409, form=request.form)
    return redirect(url_for("receipt", reference=reference), code=303)


@app.get("/api/demo-card")
def demo_card():
    try:
        with connect() as conn:
            return {"card": get_card(conn, request.args.get("buyer_id"), wallet_hash())}
    except CheckoutError as exc:
        return {"error": str(exc)}, exc.status


@app.post("/api/demo-card")
def demo_card_add():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Send demo card details as JSON."}, 400
    try:
        with connect() as conn:
            card = add_card(conn, data, wallet_hash())
        return {"card": card}, 201
    except CheckoutError as exc:
        return {"error": str(exc)}, exc.status


@app.post("/api/demo-card/remove")
def demo_card_remove():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Select a demo buyer."}, 400
    try:
        buyer_id = demo_buyer_id(data)
        with connect() as conn:
            conn.execute("DELETE FROM demo_cards WHERE buyer_id=? AND wallet_hash=?", (buyer_id, wallet_hash()))
        return {"card": None}
    except CheckoutError as exc:
        return {"error": str(exc)}, exc.status


@app.get("/payments/<uuid:reference>")
def receipt(reference):
    with connect() as conn:
        purchase = conn.execute("""SELECT pu.*, p.product_name, buyer.full_name AS buyer,
            seller.full_name AS seller FROM purchases pu
            JOIN products p ON p.product_id=pu.product_id
            JOIN students buyer ON buyer.student_id=pu.buyer_id
            JOIN students seller ON seller.student_id=p.seller_id
            WHERE pu.payment_reference=?""", (str(reference),)).fetchone()
    if not purchase:
        return not_found(None)
    return render_template("receipt.html", title="Demo receipt", purchase=purchase)


@app.post("/listing")
@auth.login_required
def listing():
    form = request.form
    try:
        name, description = form.get("product_name", "").strip(), form.get("description", "").strip()
        user = auth.current_student()
        seller_id = user["student_id"]
        category_id = int(form["category_id"])
        photos = prepare_photos(request.files.getlist("photos"))
        price = Decimal(form["price"]).quantize(Decimal("0.01"))
        condition = form.get("item_condition", "")
        if (not name or len(name) > 120 or not description or not price.is_finite()
                or not 0 < price <= Decimal("99999999.99") or condition not in CONDITIONS
                or not 0 < category_id <= 2147483647):
            raise ValueError
        with connect() as conn:
            product = conn.execute("""INSERT INTO products
                (seller_id, category_id, product_name, description, price, item_condition)
                VALUES (?, ?, ?, ?, ?, ?) RETURNING product_id""", (seller_id, category_id, name, description, price, condition)).fetchone()
            for position, photo in enumerate(photos):
                conn.execute("INSERT INTO product_photos (photo_id, product_id, image_data, position) VALUES (?, ?, ?, ?)",
                             (str(uuid4()), product["product_id"], psycopg2.Binary(photo), position))
    except (KeyError, ValueError, InvalidOperation, psycopg2.IntegrityError):
        return render_template("error.html", title="Invalid listing",
                               message="Check required fields, price and photos (up to 3 JPG/PNG/WebP files, 1 MB each)."), 400
    return redirect(url_for("catalog", notice="Listing published"), code=303)


@app.get("/photos/<uuid:photo_id>")
def product_photo(photo_id):
    with connect() as conn:
        row = conn.execute("SELECT image_data FROM product_photos WHERE photo_id=?", (str(photo_id),)).fetchone()
    if not row:
        return not_found(None)
    response = Response(bytes(row[0]), mimetype="image/jpeg")
    response.headers["Cache-Control"] = "public, max-age=86400, immutable"
    return response


@app.get("/items/<int:product_id>")
def item_detail(product_id):
    if product_id > 2147483647:
        return not_found(None)
    with connect() as conn:
        product = conn.execute("""SELECT p.*, s.full_name AS seller, c.category_name FROM products p
            JOIN students s ON s.student_id=p.seller_id JOIN categories c ON c.category_id=p.category_id
            WHERE p.product_id=?""", (product_id,)).fetchone()
        if not product:
            return not_found(None)
        photos = conn.execute("SELECT photo_id FROM product_photos WHERE product_id=? ORDER BY position", (product_id,)).fetchall()
        reviews = conn.execute("""SELECT rv.stars, rv.comment, buyer.full_name AS buyer FROM seller_reviews rv
            JOIN purchases pu ON pu.purchase_id=rv.purchase_id JOIN products p ON p.product_id=pu.product_id
            JOIN students buyer ON buyer.student_id=pu.buyer_id WHERE p.seller_id=?
            ORDER BY rv.created_at DESC LIMIT 50""", (product["seller_id"],)).fetchall()
        rating = conn.execute("""SELECT ROUND(AVG(rv.stars),1), COUNT(*) FROM seller_reviews rv
            JOIN purchases pu ON pu.purchase_id=rv.purchase_id JOIN products p ON p.product_id=pu.product_id
            WHERE p.seller_id=?""", (product["seller_id"],)).fetchone()
        product_rating = conn.execute("SELECT ROUND(AVG(stars),1), COUNT(*) FROM product_ratings WHERE product_id=?", (product_id,)).fetchone()
        user = auth.current_student()
        my_rating = conn.execute("SELECT stars FROM product_ratings WHERE product_id=? AND student_id=?",
                                 (product_id, user["student_id"] if user else None)).fetchone()
        product = dict(product)
        product['liked'] = bool(conn.execute('SELECT 1 FROM liked_products WHERE product_id=? AND student_id=?', (product_id, user['student_id'] if user else None)).fetchone())
        booking = conn.execute('SELECT student_id, expires_at FROM product_bookings WHERE product_id=? AND expires_at>CURRENT_TIMESTAMP', (product_id,)).fetchone()
        product['booked_by'] = booking['student_id'] if booking else None
        product['booking_expires'] = booking['expires_at'] if booking else None
    return render_template("item.html", title=product["product_name"], product=product, photos=photos, reviews=reviews,
                           rating=rating, product_rating=product_rating, my_stars=my_rating[0] if my_rating else None,
                           is_in_cart=product_id in cart.get_cart_product_ids(user["student_id"] if user else None),
                           notice=request.args.get("notice", ""))


@app.post("/items/<int:product_id>/rating")
@auth.login_required
def rate_product(product_id):
    if not 0 < product_id <= 2147483647:
        return not_found(None)
    try:
        stars = int(request.form.get("stars", ""))
        if not 1 <= stars <= 5:
            raise ValueError
    except ValueError:
        return render_template("error.html", title="Invalid rating", message="Choose between 1 and 5 stars."), 400
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM products WHERE product_id=?", (product_id,)).fetchone():
            return not_found(None)
        conn.execute("""INSERT INTO product_ratings (product_id, student_id, stars) VALUES (?, ?, ?)
            ON CONFLICT (product_id, student_id) DO UPDATE SET stars=EXCLUDED.stars, updated_at=CURRENT_TIMESTAMP""",
            (product_id, auth.current_student()["student_id"], stars))
    if request.form.get("return_view") == "catalog":
        return redirect(url_for("catalog", status="All", notice="Your product rating was saved") + f"#item-{product_id}", code=303)
    return redirect(url_for("item_detail", product_id=product_id, notice="Your product rating was saved"), code=303)


@app.post("/listing/<int:product_id>/<action>")
@auth.login_required
def listing_availability(product_id, action):
    if not 0 < product_id <= 2147483647 or action not in ("cancel", "restore"):
        return not_found(None)
    with connect() as conn:
        product = conn.execute("SELECT seller_id, status FROM products WHERE product_id=? FOR UPDATE", (product_id,)).fetchone()
        if not product:
            return not_found(None)
        if product["seller_id"] != auth.current_student()["student_id"]:
            return render_template("error.html", title="Access denied", message="Only the seller can change this listing."), 403
        if product["status"] == "Sold" or conn.execute("SELECT 1 FROM purchases WHERE product_id=?", (product_id,)).fetchone():
            return render_template("error.html", title="Sale already completed", message="This item has already been purchased. Its completed order cannot be cancelled from the listing."), 409
        status = "Removed" if action == "cancel" else "Available"
        conn.execute("UPDATE products SET status=? WHERE product_id=?", (status, product_id))
        if action == 'cancel':
            conn.execute('DELETE FROM product_bookings WHERE product_id=?', (product_id,))
    notice = "Listing withdrawn. It can no longer be purchased." if action == "cancel" else "Your item is available for sale again."
    return redirect(url_for("catalog", scope="mine", status="All", notice=notice), code=303)


@app.post("/reviews/<int:purchase_id>")
@auth.login_required
def review_purchase(purchase_id):
    if purchase_id > 2147483647:
        return not_found(None)
    try:
        stars = int(request.form.get("stars", ""))
        comment = request.form.get("comment", "").strip()
        if not 1 <= stars <= 5 or len(comment) > 500:
            raise ValueError
        with connect() as conn:
            purchase = conn.execute("SELECT buyer_id FROM purchases WHERE purchase_id=?", (purchase_id,)).fetchone()
            if not purchase or purchase["buyer_id"] != auth.current_student()["student_id"]:
                return render_template("error.html", title="Review unavailable", message="Only the buyer can review this purchase."), 403
            conn.execute("""INSERT INTO seller_reviews (purchase_id, stars, comment) VALUES (?, ?, ?)
                ON CONFLICT (purchase_id) DO UPDATE SET stars=EXCLUDED.stars, comment=EXCLUDED.comment""", (purchase_id, stars, comment))
    except ValueError:
        return render_template("error.html", title="Invalid review", message="Choose 1–5 stars and keep your review under 500 characters."), 400
    return redirect(url_for("sales", notice="Review saved"), code=303)


@app.get("/cart")
def cart_view():
    user = auth.current_student()
    items, total_price = cart.get_cart_details(user["student_id"] if user else None)
    return render_template("cart.html", title="Cart", items=items, total_price=total_price,
                           notice=request.args.get("notice", ""))


@app.post("/cart/toggle/<int:product_id>")
def cart_toggle(product_id):
    user = auth.current_student()
    student_id = user["student_id"] if user else None
    if product_id in cart.get_cart_product_ids(student_id):
        cart.remove_from_cart(product_id, student_id)
    else:
        cart.add_to_cart(product_id, student_id)
    return redirect(request.referrer or url_for("catalog"))


@app.get('/liked')
@auth.login_required
def liked_view():
    return redirect(url_for('catalog', scope='liked', status='All'))


@app.get('/bookings')
@auth.login_required
def bookings_view():
    return redirect(url_for('catalog', scope='booked'))


@app.post('/items/<int:product_id>/like')
@auth.login_required
def like_product(product_id):
    if not 0 < product_id <= 2147483647:
        return not_found(None)
    desired = request.form.get('liked')
    if desired not in ('0','1'):
        return render_template('error.html', title='Invalid request', message='Choose whether to save the item.'), 400
    with connect() as conn:
        if not conn.execute('SELECT 1 FROM products WHERE product_id=?', (product_id,)).fetchone():
            return not_found(None)
        user_id = auth.current_student()['student_id']
        if desired == '1':
            conn.execute('INSERT INTO liked_products (student_id, product_id) VALUES (?, ?) ON CONFLICT DO NOTHING', (user_id, product_id))
        else:
            conn.execute('DELETE FROM liked_products WHERE student_id=? AND product_id=?', (user_id, product_id))
    if request.form.get('return_view') == 'liked':
        return redirect(url_for('liked_view'), code=303)
    return redirect(url_for('item_detail', product_id=product_id, notice='Saved to Liked' if desired == '1' else 'Removed from Liked'), code=303)


@app.post('/items/<int:product_id>/booking/<action>')
@auth.login_required
def booking_action(product_id, action):
    if action not in ('reserve', 'cancel'):
        return not_found(None)
    try:
        with connect() as conn:
            operation = bookings.reserve if action == 'reserve' else bookings.cancel
            operation(conn, product_id, auth.current_student()['student_id'])
    except CheckoutError as exc:
        return render_template('error.html', title='Booking unavailable', message=str(exc)), exc.status
    notice = 'Reserved for you for 24 hours. No payment has been taken.' if action == 'reserve' else 'Booking cancelled. The item is available again.'
    return redirect(url_for('item_detail', product_id=product_id, notice=notice), code=303)


@app.post("/cart/remove/<int:product_id>")
def cart_remove(product_id):
    user = auth.current_student()
    cart.remove_from_cart(product_id, user["student_id"] if user else None)
    return redirect(url_for("cart_view", notice="Item removed from cart"))


@app.errorhandler(413)
def too_large(error):
    return render_template("error.html", title="Upload too large", message="Upload up to 3 photos, no larger than 1 MB each."), 413


@app.get("/listings/<int:product_id>/promote")
@auth.login_required
def promote_listing(product_id):
    user = auth.current_student()

    with connect() as conn:
        product = conn.execute(
            """
            SELECT product_id, product_name, price
            FROM products
            WHERE product_id = ?
              AND seller_id = ?
              AND status = 'Available'
            """,
            (product_id, user["student_id"])
        ).fetchone()

    if product is None:
        return render_template(
            "error.html",
            title="Not found",
            message="This listing cannot be promoted."
        ), 404

    return render_template(
        "promote_listing.html",
        title="Promote Listing",
        product=product,
        plans=PROMOTION_PLANS
    )


@app.post("/listings/<int:product_id>/promote")
@auth.login_required
def confirm_promotion(product_id):
    user = auth.current_student()

    try:
        days = int(request.form["duration_days"])
    except (KeyError, ValueError):
        return "Invalid promotion plan", 400

    if days not in PROMOTION_PLANS:
        return "Invalid promotion plan", 400

    with connect() as conn:
        product = conn.execute(
            """
            SELECT product_id
            FROM products
            WHERE product_id = ?
              AND seller_id = ?
              AND status = 'Available'
            FOR UPDATE
            """,
            (product_id, user["student_id"])
        ).fetchone()

        if product is None:
            return "Listing not available", 404

        active = conn.execute(
            """
            SELECT 1
            FROM listing_promotions
            WHERE product_id = ?
              AND expires_at > CURRENT_TIMESTAMP
            LIMIT 1
            """,
            (product_id,)
        ).fetchone()

        if active:
            return "This listing is already promoted", 409

        conn.execute(
            """
            INSERT INTO listing_promotions (
                product_id,
                student_id,
                duration_days,
                demo_price,
                expires_at
            )
            VALUES (
                ?, ?, ?, ?,
                CURRENT_TIMESTAMP + (? * INTERVAL '1 day')
            )
            """,
            (
                product_id,
                user["student_id"],
                days,
                PROMOTION_PLANS[days],
                days
            )
        )

    return redirect(
        url_for("my_listings", notice="Promotion activated"),
        code=303
    )


@app.get("/my-listings")
@auth.login_required
def my_listings():
    user = auth.current_student()

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT p.product_id, p.product_name,
                   p.description, p.price,
                   p.item_condition, p.status,
                   c.category_name
            FROM products p
            JOIN categories c
                ON c.category_id = p.category_id
            WHERE p.seller_id = ?
            ORDER BY p.product_id DESC
            """,
            (user["student_id"],)
        ).fetchall()

    return render_template(
        "my_listings.html",
        title="My Listings",
        rows=rows,
        notice=request.args.get("notice", "")
    )

@app.get("/listings/<int:product_id>/edit")
@auth.login_required
def edit_listing(product_id):
    user = auth.current_student()

    with connect() as conn:
        product = conn.execute(
            """
            SELECT *
            FROM products
            WHERE product_id = ?
              AND seller_id = ?
              AND status = 'Available'
            """,
            (product_id, user["student_id"])
        ).fetchone()

        categories = conn.execute(
            """
            SELECT category_id, category_name
            FROM categories
            WHERE is_active = TRUE
            ORDER BY category_name
            """
        ).fetchall()

    if product is None:
        return render_template(
            "error.html",
            title="Listing not found",
            message="You cannot edit this listing."
        ), 404

    return render_template(
        "edit_listing.html",
        title="Edit Listing",
        product=product,
        categories=categories,
        conditions=CONDITIONS
    )


@app.post("/listings/<int:product_id>/edit")
@auth.login_required
def update_listing(product_id):
    user = auth.current_student()
    form = request.form

    try:
        name = form.get("product_name", "").strip()
        description = form.get("description", "").strip()
        category_id = int(form["category_id"])
        price = Decimal(form["price"])

        if not price.is_finite():
            raise ValueError

        price = price.quantize(Decimal("0.01"))
        condition = form.get("item_condition", "")

        if (
            not name
            or len(name) > 120
            or not description
            or not 0 < price <= Decimal("99999999.99")
            or condition not in CONDITIONS
            or not 0 < category_id <= 2147483647
        ):
            raise ValueError

        with connect() as conn:
            result = conn.execute(
                """
                UPDATE products
                SET product_name = ?,
                    description = ?,
                    category_id = ?,
                    price = ?,
                    item_condition = ?
                WHERE product_id = ?
                  AND seller_id = ?
                  AND status = 'Available'
                """,
                (
                    name, description, category_id,
                    price, condition, product_id,
                    user["student_id"]
                )
            )

            if result.rowcount == 0:
                return render_template(
                    "error.html",
                    title="Not found",
                    message="You cannot edit this listing."
                ), 404

    except (
        KeyError, ValueError, InvalidOperation,
        psycopg2.IntegrityError
    ):
        return render_template(
            "error.html",
            title="Invalid listing",
            message="Please check your item information."
        ), 400

    return redirect(
        url_for("my_listings", notice="Listing updated"),
        code=303
    )


@app.post("/listings/<int:product_id>/delete")
@auth.login_required
def delete_listing(product_id):
    user = auth.current_student()

    with connect() as conn:
        result = conn.execute(
            """
            UPDATE products
            SET status = 'Removed'
            WHERE product_id = ?
              AND seller_id = ?
              AND status = 'Available'
            """,
            (product_id, user["student_id"])
        )

        if result.rowcount == 1:
            conn.execute('DELETE FROM product_bookings WHERE product_id=?', (product_id,))
        if result.rowcount == 0:
            return render_template(
                "error.html",
                title="Listing not found",
                message="You cannot remove this listing."
            ), 404

    return redirect(
        url_for("my_listings", notice="Listing removed"),
        code=303
    )


@app.post("/purchase")
def purchase():
    """Old forms must go through the card-required checkout too."""
    try:
        product_id = int(request.form.get("product_id", ""))
        if not 0 < product_id <= 2147483647:
            raise ValueError
    except ValueError:
        return render_template("error.html", title="Invalid item", message="Choose an item from the catalog."), 400
    return redirect(url_for("checkout", product_id=product_id), code=303)


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", title="Page not found", message="Return to the catalog to keep browsing."), 404


@app.errorhandler(RuntimeError)
@app.errorhandler(psycopg2.Error)
def database_unavailable(error):
    # Do not expose connection strings, SQL, hostnames, or credentials in responses/logs.
    cause = error.__cause__ or error
    app.logger.error("Database request failed (%s, SQLSTATE=%s)", type(cause).__name__, getattr(cause, 'pgcode', None))
    if request.path == "/api/health":
        return {"status": "unavailable", "database": "unavailable"}, 503
    if request.path.startswith("/api/"):
        return {"error": "The database is unavailable. Please try again later."}, 503
    return render_template("error.html", title="Database unavailable",
                           message="The database is unavailable. Check DATABASE_URL and run the database initialization command."), 503


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-db", action="store_true", help="Create tables and load demo records, then exit")
    parser.add_argument("--migrate-db", action="store_true", help="Upgrade the database schema without seeding records")
    args = parser.parse_args()
    if args.migrate_db:
        migrate_database()
        print("Database schema upgraded. Existing marketplace records preserved.")
        return
    if args.init_db:
        initialize_database()
        print("Database ready: PostgreSQL. Tables and demo records initialized.")
        return
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
