"""Run with python -m unittest discover -s tests -v.

Set TEST_DATABASE_URL to exercise PostgreSQL in an isolated, temporary schema.
"""
import importlib
import os
import unittest
import uuid
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


if __name__ == "__main__":
    unittest.main()
