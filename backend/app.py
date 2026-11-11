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

from flask import Flask, g, redirect, render_template, request, send_from_directory, url_for

from backend.database import connect, initialize_database, migrate_database, psycopg2
from backend.payments import CheckoutError, complete_purchase, demo_buyer_id
from backend.cards import add_card, get_card

ROOT = Path(__file__).resolve().parents[1]
app = Flask(__name__, template_folder=str(ROOT / "frontend/templates"), static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 20_000
CONDITIONS = ("New", "Like New", "Good", "Fair")
STATUSES = ("Available", "Sold", "Removed", "All")


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
    if response.mimetype != "text/css":
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
    return {"status": "ok", "database": "ok"}


@app.get("/")
def catalog():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "Available")
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
            p.item_condition, p.status, c.category_name, s.full_name AS seller, s.student_id AS seller_id
            FROM products p JOIN categories c ON c.category_id=p.category_id
            JOIN students s ON s.student_id=p.seller_id""" + where +
            " ORDER BY CASE p.status WHEN 'Available' THEN 0 ELSE 1 END, p.price, p.product_id", args).fetchall()
        counts = {row["status"]: row["n"] for row in conn.execute("SELECT status, COUNT(*) AS n FROM products GROUP BY status")}
    return render_template("catalog.html", title="Marketplace catalog", rows=rows,
                           categories=categories, people=people, counts=counts,
                           search=search, status=status, category=category,
                           conditions=CONDITIONS, statuses=STATUSES,
                           notice=request.args.get("notice", ""))


@app.get("/sales")
def sales():
    with connect() as conn:
        rows = conn.execute("""SELECT pu.purchase_id, pu.purchase_date, pu.agreed_price,
            pu.payment_method, pu.payment_status, pu.payment_reference,
            buyer.full_name AS buyer, p.product_name, seller.full_name AS seller
            FROM purchases pu JOIN students buyer ON buyer.student_id = pu.buyer_id
            JOIN products p ON p.product_id = pu.product_id
            JOIN students seller ON seller.student_id = p.seller_id
            ORDER BY pu.purchase_date DESC, pu.purchase_id DESC""").fetchall()
    return render_template("sales.html", title="Purchase history", rows=rows)


def checkout_page(product_id, *, error="", status=200, form=None):
    form = form or {}
    wallet_hash()
    with connect() as conn:
        product = conn.execute("""SELECT p.*, s.full_name AS seller, c.category_name
            FROM products p JOIN students s ON s.student_id=p.seller_id
            JOIN categories c ON c.category_id=p.category_id WHERE product_id=?""", (product_id,)).fetchone()
        if not product:
            return not_found(None)
        people = conn.execute("SELECT student_id, full_name FROM students WHERE student_id<>? ORDER BY full_name", (product["seller_id"],)).fetchall()
    return render_template("checkout.html", title="Checkout", product=product, people=people,
                           reference=form.get("payment_reference") or str(uuid4()),
                           buyer_id=form.get("buyer_id", ""), method=form.get("payment_method", "Demo Card"),
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
def listing():
    form = request.form
    try:
        name, description = form.get("product_name", "").strip(), form.get("description", "").strip()
        seller_id, category_id = int(form["seller_id"]), int(form["category_id"])
        price = Decimal(form["price"]).quantize(Decimal("0.01"))
        condition = form.get("item_condition", "")
        if (not name or len(name) > 120 or not description or not price.is_finite()
                or not 0 < price <= Decimal("99999999.99") or condition not in CONDITIONS
                or not 0 < seller_id <= 2147483647 or not 0 < category_id <= 2147483647):
            raise ValueError
        with connect() as conn:
            conn.execute("""INSERT INTO products
                (seller_id, category_id, product_name, description, price, item_condition)
                VALUES (?, ?, ?, ?, ?, ?)""", (seller_id, category_id, name, description, price, condition))
    except (KeyError, ValueError, InvalidOperation, psycopg2.IntegrityError):
        return render_template("error.html", title="Invalid listing",
                               message="Check the required fields and enter a valid price above zero."), 400
    return redirect(url_for("catalog", notice="Listing published"), code=303)


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
    app.logger.error("Database request failed (%s)", type(error).__name__)
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
