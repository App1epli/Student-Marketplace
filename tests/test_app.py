"""Run with python -m unittest discover -s tests -v.

Set TEST_DATABASE_URL to exercise PostgreSQL in an isolated, temporary schema.
"""
import importlib
import os
import unittest
import uuid
import re
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from psycopg2 import sql

from backend import database

web = importlib.import_module("backend.app")


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()

    def test_entrypoint(self):
        from app import app
        self.assertIs(app, web.app)

    def test_static_and_not_found_need_no_database(self):
        with patch.object(web, "connect", side_effect=AssertionError("Unexpected DB access")):
            response = self.client.get("/static/styles.css")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b".catalog", response.data)
            response.close()
            self.assertEqual(self.client.get("/missing").status_code, 404)
            self.assertEqual(self.client.get("/static/../../.env").status_code, 404)

    def test_database_failure_does_not_leak_secrets(self):
        with patch.object(web, "connect", side_effect=RuntimeError("secret-password")):
            for path in ("/", "/sales", "/api/health"):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(b"secret-password", response.data)

    def test_invalid_listing_does_not_access_database(self):
        with patch.object(web, "connect", side_effect=AssertionError("Unexpected DB access")):
            for price in ("NaN", "Infinity", "-1", "0", "100000000", "text"):
                with self.subTest(price=price):
                    response = self.client.post("/listing", data=dict(
                        seller_id="1", category_id="1", product_name="Test", description="Test",
                        price=price, item_condition="Good"))
                    self.assertEqual(response.status_code, 400)

    def test_request_size_limit(self):
        self.assertEqual(self.client.post("/listing", data={"description": "x" * 21_000}).status_code, 413)

    def test_checkout_id_bounds_and_money(self):
        with patch.object(web, "connect", side_effect=AssertionError("Unexpected DB access")):
            self.assertEqual(self.client.get("/checkout/99999999999999999999999").status_code, 404)
        from decimal import Decimal
        self.assertEqual(web.money(Decimal("1234.50")), "1 234.50 ₸")


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL is not set")
class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["TEST_DATABASE_URL"]
        cls.schema = "test_marketplace_" + uuid.uuid4().hex
        cls.original_connect = database.connect
        with cls.original_connect(cls.url) as conn:
            conn.raw.cursor().execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))
        cls.addClassCleanup(cls.drop_schema)

        def isolated_connect(url=None):
            conn = cls.original_connect(cls.url)
            conn.raw.cursor().execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema)))
            return conn

        cls.db_patch = patch.object(database, "connect", side_effect=isolated_connect)
        cls.web_patch = patch.object(web, "connect", side_effect=isolated_connect)
        cls.db_patch.start()
        cls.addClassCleanup(cls.db_patch.stop)
        cls.web_patch.start()
        cls.addClassCleanup(cls.web_patch.stop)
        database.initialize_database()

    @classmethod
    def drop_schema(cls):
        with cls.original_connect(cls.url) as conn:
            conn.raw.cursor().execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema)))

    def setUp(self):
        self.client = web.app.test_client()

    def create_listing(self, name="Integration item"):
        response = self.client.post("/listing", data=dict(seller_id="1", category_id="1",
            product_name=name, description="Test description", price="1234.50", item_condition="Good"))
        self.assertEqual(response.status_code, 303)
        with database.connect() as conn:
            return conn.execute("SELECT MAX(product_id) FROM products").fetchone()[0]

    def test_catalog_filters_and_html_escaping(self):
        self.create_listing("<script>alert(1)</script>")
        response = self.client.get("/?q=%3Cscript%3E&category=1&status=Available")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"&lt;script&gt;", response.data)
        self.assertNotIn(b"<script>alert", response.data)
        self.assertNotIn(b"Scientific Calculator</h3>", response.data)
        self.assertEqual(self.client.get("/?category=999999999999999999999999").status_code, 200)
        self.assertEqual(self.client.get("/api/health").json["database"], "ok")

    def test_initializer_is_repeatable(self):
        with database.connect() as conn:
            before = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        database.initialize_database()
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM products").fetchone()[0], before)

    def test_purchase_and_self_purchase(self):
        product_id = self.create_listing()
        own = self.client.post("/purchase", data=dict(product_id=product_id, buyer_id=1, payment_method="Cash"))
        self.assertIn("own", own.location)
        response = self.client.post("/purchase", data=dict(product_id=product_id, buyer_id=2, payment_method="Cash"))
        self.assertEqual(response.status_code, 303)
        self.assertIn("successfully", response.location)
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM products WHERE product_id=?", (product_id,)).fetchone()[0], "Sold")
        self.assertEqual(self.client.get("/sales").status_code, 200)
        self.assertIn(b"Integration item", self.client.get("/sales").data)

    def test_concurrent_purchase_has_one_winner(self):
        product_id = self.create_listing("Concurrent item")

        def buy(buyer_id):
            with web.app.test_client() as client:
                return client.post("/purchase", data=dict(product_id=product_id, buyer_id=buyer_id, payment_method="Cash")).location

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(buy, (2, 3)))
        self.assertEqual(sum("successfully" in result for result in results), 1)
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0], 1)

    def checkout_form(self, product_id, method="Demo Card", outcome="approved", buyer=2):
        response = self.client.get(f"/checkout/{product_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No real money is charged", response.data)
        token = re.search(rb'name="payment_reference" value="([^"]+)"', response.data).group(1).decode()
        return dict(payment_reference=token, buyer_id=str(buyer), payment_method=method, demo_result=outcome)

    def test_demo_payment_receipt_and_replay(self):
        product_id = self.create_listing("Payment item")
        form = self.checkout_form(product_id)
        # Neither a tampered price nor a browser-provided status is trusted.
        form.update(price="0.01", payment_status="Pending", agreed_price="0.01")
        response = self.client.post(f"/checkout/{product_id}", data=form)
        self.assertEqual(response.status_code, 303)
        receipt = self.client.get(response.location)
        self.assertEqual(receipt.status_code, 200)
        self.assertIn(b"Demo payment successful", receipt.data)
        self.assertIn(b"1 234.50", receipt.data)
        self.assertEqual(self.client.post(f"/checkout/{product_id}", data=form).location, response.location)
        with database.connect() as conn:
            row = conn.execute("SELECT * FROM purchases WHERE product_id=?", (product_id,)).fetchone()
            self.assertEqual(row["payment_status"], "Demo paid")
            self.assertEqual(str(row["agreed_price"]), "1234.50")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0], 1)
        self.assertIn(b"View receipt", self.client.get("/sales").data)

    def test_demo_decline_then_retry(self):
        product_id = self.create_listing("Declined item")
        form = self.checkout_form(product_id, outcome="declined")
        response = self.client.post(f"/checkout/{product_id}", data=form)
        self.assertEqual(response.status_code, 402)
        self.assertIn(b"Demo payment declined", response.data)
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM products WHERE product_id=?", (product_id,)).fetchone()[0], "Available")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0], 0)
        form["demo_result"] = "approved"
        self.assertEqual(self.client.post(f"/checkout/{product_id}", data=form).status_code, 303)

    def test_bank_transfer_and_cash_statuses(self):
        for method, status in (("Bank Transfer", "Demo paid"), ("Cash", "Pending")):
            with self.subTest(method=method):
                product_id = self.create_listing(f"{method} item")
                form = self.checkout_form(product_id, method=method)
                response = self.client.post(f"/checkout/{product_id}", data=form)
                self.assertEqual(response.status_code, 303)
                with database.connect() as conn:
                    self.assertEqual(conn.execute("SELECT payment_status FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0], status)
                self.assertIn(status.encode(), self.client.get(response.location).data)

    def test_checkout_cancel_does_not_purchase(self):
        product_id = self.create_listing("Cancelled item")
        response = self.client.get(f"/checkout/{product_id}")
        self.assertIn(b"Cancel checkout", response.data)
        self.client.get("/?notice=Checkout+cancelled.+No+purchase+was+created.")
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM products WHERE product_id=?", (product_id,)).fetchone()[0], "Available")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0], 0)

    def test_checkout_rejects_invalid_input_and_self_purchase(self):
        product_id = self.create_listing()
        form = self.checkout_form(product_id)
        for changes in (dict(buyer_id="1"), dict(buyer_id="2147483647"), dict(payment_reference="invalid"),
                        dict(payment_method="Bitcoin"), dict(demo_result="paid")):
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post(f"/checkout/{product_id}", data={**form, **changes}).status_code, 400)
        self.assertEqual(self.client.get(f"/payments/{uuid.uuid4()}").status_code, 404)

    def test_concurrent_checkout_and_token_reuse(self):
        product_id = self.create_listing("Concurrent checkout")
        form = self.checkout_form(product_id)

        def submit(_):
            with web.app.test_client() as client:
                response = client.post(f"/checkout/{product_id}", data=form)
                return response.status_code, response.location

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], 303)
        other_id = self.create_listing("Different checkout")
        self.assertEqual(self.client.post(f"/checkout/{other_id}", data=form).status_code, 409)
        # A competing buyer with a different reference cannot buy the sold item.
        other_form = {**form, "buyer_id": "3", "payment_reference": str(uuid.uuid4())}
        self.assertEqual(self.client.post(f"/checkout/{product_id}", data=other_form).status_code, 409)

    def test_migration_preserves_legacy_purchases(self):
        schema = "test_legacy_" + uuid.uuid4().hex
        conn = type(self).original_connect(self.url)
        try:
            conn.raw.cursor().execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            conn.raw.cursor().execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            conn.executescript(database.POSTGRES_SCHEMA)
            conn.executemany("INSERT INTO students (student_number, full_name, email, study_program, study_year) VALUES (?, ?, ?, ?, ?)", database.STUDENTS)
            conn.executemany("INSERT INTO categories (category_name, description) VALUES (?, ?)", database.CATEGORIES)
            conn.executemany("INSERT INTO products (seller_id, category_id, product_name, description, price, item_condition, status) VALUES (?, ?, ?, ?, ?, ?, ?)", database.PRODUCTS)
            conn.execute("INSERT INTO purchases (buyer_id, product_id, agreed_price, payment_method) VALUES (4, 5, 3800, 'Cash')")
            database.apply_migrations(conn)
            database.apply_migrations(conn)
            row = conn.execute("SELECT * FROM purchases").fetchone()
            self.assertEqual(row["payment_status"], "Not recorded")
            self.assertIsNone(row["payment_reference"])
            self.assertEqual(str(row["agreed_price"]), "3800.00")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 1)
        finally:
            # The temporary schema, data, and migration are all rolled back.
            conn.rollback()
            conn.close()


if __name__ == "__main__":
    unittest.main()
