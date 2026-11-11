"""Flask entrypoint shared by local development and Vercel."""
from __future__ import annotations

import argparse
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import Flask, redirect, render_template, request, send_from_directory, url_for

from backend.database import connect, initialize_database, psycopg2

ROOT = Path(__file__).resolve().parents[1]
app = Flask(__name__, template_folder=str(ROOT / "frontend/templates"), static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 20_000
CONDITIONS = ("New", "Like New", "Good", "Fair")
STATUSES = ("Available", "Sold", "Removed", "All")


@app.template_filter("money")
def money(value):
    return f"{value:,.0f}".replace(",", " ") + " ₸"


@app.after_request
def response_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    if response.mimetype != "text/css":
        response.headers["Cache-Control"] = "no-store"
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
            pu.payment_method, buyer.full_name AS buyer, p.product_name, seller.full_name AS seller
            FROM purchases pu JOIN students buyer ON buyer.student_id = pu.buyer_id
            JOIN products p ON p.product_id = pu.product_id
            JOIN students seller ON seller.student_id = p.seller_id
            ORDER BY pu.purchase_date DESC, pu.purchase_id DESC""").fetchall()
    return render_template("sales.html", title="Purchase history", rows=rows)


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
    try:
        buyer_id, product_id = int(request.form["buyer_id"]), int(request.form["product_id"])
        payment = request.form.get("payment_method", "")
        if (payment not in ("Cash", "Bank Transfer") or not 0 < buyer_id <= 2147483647
                or not 0 < product_id <= 2147483647):
            raise ValueError("Select a valid buyer, listing, and payment method.")
        with connect() as conn:
            product = conn.execute("SELECT * FROM products WHERE product_id=? FOR UPDATE", (product_id,)).fetchone()
            if not product or product["status"] != "Available":
                raise ValueError("This listing is no longer available.")
            if product["seller_id"] == buyer_id:
                raise ValueError("You cannot buy your own listing.")
            if not conn.execute("SELECT 1 FROM students WHERE student_id=?", (buyer_id,)).fetchone():
                raise ValueError("Select a buyer from the list.")
            conn.execute("INSERT INTO purchases (buyer_id, product_id, agreed_price, payment_method) VALUES (?, ?, ?, ?)",
                         (buyer_id, product_id, product["price"], payment))
            changed = conn.execute("UPDATE products SET status='Sold' WHERE product_id=? AND status='Available'", (product_id,)).rowcount
            if changed != 1:
                raise ValueError("This listing is no longer available.")
    except (KeyError, ValueError) as exc:
        message = str(exc) if isinstance(exc, ValueError) and str(exc) else "Select a valid buyer and listing."
        return redirect(url_for("catalog", notice=message), code=303)
    except psycopg2.IntegrityError:
        return redirect(url_for("catalog", notice="The purchase could not be completed. Please refresh the catalog."), code=303)
    return redirect(url_for("catalog", notice="Purchase completed successfully"), code=303)


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
    return render_template("error.html", title="Database unavailable",
                           message="The database is unavailable. Check DATABASE_URL and run the database initialization command."), 503


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-db", action="store_true", help="Create tables and load demo records, then exit")
    args = parser.parse_args()
    if args.init_db:
        initialize_database()
        print("Database ready: PostgreSQL. Tables and demo records initialized.")
        return
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
