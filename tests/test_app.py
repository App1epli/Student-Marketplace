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

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only")

from backend import database

web = importlib.import_module("backend.app")


def csrf_token_for(client, path="/register"):
    """Fetch a fresh CSRF token bound to this client's session (no DB needed)."""
    html = client.get(path).get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if not match:
        raise AssertionError(f"No CSRF token found on {path}")
    return match.group(1)


def post_form(client, path, data=None, **kwargs):
    payload = dict(data or {})
    payload.setdefault("csrf_token", csrf_token_for(client))
    return client.post(path, data=payload, **kwargs)


def post_json(client, path, payload, **kwargs):
    headers = dict(kwargs.pop("headers", {}) or {})
    headers["X-CSRFToken"] = csrf_token_for(client)
    return client.post(path, json=payload, headers=headers, **kwargs)


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
                    response = post_form(self.client, "/listing", dict(
                        seller_id="1", category_id="1", product_name="Test", description="Test",
                        price=price, item_condition="Good"))
                    self.assertEqual(response.status_code, 400)

    def test_auth_pages_render_without_database(self):
        with patch.object(web, "connect", side_effect=AssertionError("Unexpected DB access")):
            self.assertEqual(self.client.get("/login").status_code, 200)
            self.assertEqual(self.client.get("/register").status_code, 200)

    def test_csrf_required_for_state_changing_requests(self):
        with patch.object(web, "connect", side_effect=AssertionError("Unexpected DB access")):
            # Missing token: rejected before any view or database access.
            self.assertEqual(self.client.post("/listing", data={"product_name": "x"}).status_code, 400)
            self.assertEqual(self.client.post("/api/demo-card", json={"buyer_id": "1"}).status_code, 400)
            self.assertEqual(self.client.post("/api/demo-card/remove", json={"buyer_id": "1"}).status_code, 400)
            self.assertEqual(self.client.post("/messages/send", data={"message_text": "hi"}).status_code, 400)
            self.assertEqual(self.client.post("/logout").status_code, 400)
            # JSON endpoints accept the token via the X-CSRFToken header instead.
            response = self.client.post("/api/demo-card", json={"buyer_id": "1"},
                                        headers={"X-CSRFToken": csrf_token_for(self.client)})
            self.assertNotEqual(response.status_code, 400)

    def test_request_size_limit(self):
        self.assertEqual(self.client.post("/listing", data={"description": "x" * 21_000}).status_code, 413)

    def test_checkout_id_bounds_and_money(self):
        with patch.object(web, "connect", side_effect=AssertionError("Unexpected DB access")):
            self.assertEqual(self.client.get("/checkout/99999999999999999999999").status_code, 404)
        from decimal import Decimal
        self.assertEqual(web.money(Decimal("1234.50")), "1 234.50 ₸")

    def test_demo_card_validation(self):
        from backend.cards import validate_demo_card
        from backend.payments import CheckoutError
        valid = dict(number="4242 4242 4242 4242", holder_name="Alex Student", expiry="12/29", cvv="123")
        with patch("backend.cards.current_month", return_value=(2026, 11)):
            safe = validate_demo_card(valid)
            self.assertEqual(safe["last4"], "4242")
            self.assertNotIn("number", safe)
            self.assertNotIn("cvv", safe)
            for changes in (dict(number="4111111111111111"), dict(cvv="000"), dict(expiry="10/26"),
                            dict(expiry="13/29"), dict(holder_name=""), dict(number=4242)):
                with self.subTest(changes=changes), self.assertRaises(CheckoutError):
                    validate_demo_card({**valid, **changes})
            self.assertEqual(validate_demo_card({**valid, "expiry": "11/26"})["expiry_month"], 11)


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

    def create_listing(self, name="Integration item", seller_id=1):
        response = post_form(self.client, "/listing", dict(seller_id=str(seller_id), category_id="1",
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
        own_form = self.checkout_form(product_id, buyer=1)
        own = post_form(self.client, f"/checkout/{product_id}", own_form)
        self.assertEqual(own.status_code, 400)
        self.assertIn(b"own listing", own.data)
        form = self.checkout_form(product_id, buyer=2)
        response = post_form(self.client, f"/checkout/{product_id}", form)
        self.assertEqual(response.status_code, 303)
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM products WHERE product_id=?", (product_id,)).fetchone()[0], "Sold")
        self.assertEqual(self.client.get("/sales").status_code, 200)
        self.assertIn(b"Integration item", self.client.get("/sales").data)

    def test_concurrent_purchase_has_one_winner(self):
        product_id = self.create_listing("Concurrent item")
        forms = [self.checkout_form(product_id, buyer=buyer) for buyer in (2, 3)]
        cookie = self.client.get_cookie("demo_wallet").value

        def buy(form):
            with web.app.test_client() as client:
                client.set_cookie("demo_wallet", cookie)
                return post_form(client, f"/checkout/{product_id}", form).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(buy, forms))
        self.assertEqual(sorted(results), [303, 409])
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0], 1)

    def add_card(self, client=None, buyer=2, **changes):
        client = client or self.client
        from datetime import datetime, timezone
        expiry = f"12/{(datetime.now(timezone.utc).year + 2) % 100:02}"
        return post_json(client, "/api/demo-card", {"buyer_id": str(buyer), "number": "4242 4242 4242 4242",
            "holder_name": "Alex Student", "expiry": expiry, "cvv": "123", **changes})

    def checkout_form(self, product_id, method="Demo Card", outcome="approved", buyer=2):
        response = self.client.get(f"/checkout/{product_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No real money is charged", response.data)
        token = re.search(rb'name="payment_reference" value="([^"]+)"', response.data).group(1).decode()
        saved = self.add_card(buyer=buyer)
        self.assertEqual(saved.status_code, 201)
        return dict(payment_reference=token, buyer_id=str(buyer), payment_method=method, demo_result=outcome, card_id=saved.json["card"]["card_id"])

    def test_demo_payment_receipt_and_replay(self):
        product_id = self.create_listing("Payment item")
        form = self.checkout_form(product_id)
        # Neither a tampered price nor a browser-provided status is trusted.
        form.update(price="0.01", payment_status="Pending", agreed_price="0.01")
        response = post_form(self.client, f"/checkout/{product_id}", form)
        self.assertEqual(response.status_code, 303)
        receipt = self.client.get(response.location)
        self.assertEqual(receipt.status_code, 200)
        self.assertIn(b"Demo payment successful", receipt.data)
        self.assertIn(b"1 234.50", receipt.data)
        self.assertEqual(post_form(self.client, f"/checkout/{product_id}", form).location, response.location)
        with database.connect() as conn:
            row = conn.execute("SELECT * FROM purchases WHERE product_id=?", (product_id,)).fetchone()
            self.assertEqual(row["payment_status"], "Demo paid")
            self.assertEqual(str(row["agreed_price"]), "1234.50")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0], 1)
        self.assertIn(b"View receipt", self.client.get("/sales").data)

    def test_demo_decline_then_retry(self):
        product_id = self.create_listing("Declined item")
        form = self.checkout_form(product_id, outcome="declined")
        response = post_form(self.client, f"/checkout/{product_id}", form)
        self.assertEqual(response.status_code, 402)
        self.assertIn(b"Demo payment declined", response.data)
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM products WHERE product_id=?", (product_id,)).fetchone()[0], "Available")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0], 0)
        form["demo_result"] = "approved"
        self.assertEqual(post_form(self.client, f"/checkout/{product_id}", form).status_code, 303)

    def test_cash_and_transfer_cannot_bypass_card_checkout(self):
        product_id = self.create_listing()
        form = self.checkout_form(product_id)
        for method in ("Bank Transfer", "Cash"):
            self.assertEqual(post_form(self.client, f"/checkout/{product_id}", {**form, "payment_method": method}).status_code, 400)
            response = post_form(self.client, "/purchase", dict(product_id=product_id, buyer_id=2, payment_method=method))
            self.assertEqual(response.status_code, 303)
            self.assertTrue(response.location.endswith(f"/checkout/{product_id}"))
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0], 0)

    def test_checkout_cancel_does_not_purchase(self):
        product_id = self.create_listing("Cancelled item")
        response = self.client.get(f"/checkout/{product_id}")
        self.assertIn(b"Cancel checkout", response.data)
        self.client.get("/?notice=Checkout+cancelled.+No+purchase+was+created.")
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM products WHERE product_id=?", (product_id,)).fetchone()[0], "Available")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0], 0)

    def test_no_card_cannot_purchase_even_with_forged_form(self):
        product_id = self.create_listing()
        response = self.client.get(f"/checkout/{product_id}")
        self.assertIn(b"+ Add card", response.data)
        self.assertRegex(response.get_data(as_text=True), r'id="pay-button"[^>]*disabled')
        form = dict(buyer_id="2", payment_method="Demo Card", payment_reference=str(uuid.uuid4()))
        for card_id in ("", str(uuid.uuid4())):
            response = post_form(self.client, f"/checkout/{product_id}", {**form, "card_id": card_id})
            self.assertEqual(response.status_code, 400)
        with database.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0], 0)

    def test_wallet_scope_removal_and_expiry(self):
        product_id = self.create_listing()
        form = self.checkout_form(product_id)
        another_browser = web.app.test_client()
        self.assertIsNone(another_browser.get("/api/demo-card?buyer_id=2").json["card"])
        self.assertIsNotNone(self.client.get("/api/demo-card?buyer_id=2").json["card"])
        self.assertIsNone(self.client.get("/api/demo-card?buyer_id=3").json["card"])
        self.assertEqual(post_form(another_browser, f"/checkout/{product_id}", form).status_code, 400)
        self.assertEqual(post_form(self.client, f"/checkout/{product_id}", {**form, "buyer_id": "3"}).status_code, 400)
        post_json(another_browser, "/api/demo-card/remove", {"buyer_id": "2"})
        self.assertIsNotNone(self.client.get("/api/demo-card?buyer_id=2").json["card"])
        with database.connect() as conn:
            conn.execute("UPDATE demo_cards SET expiry_year=2020 WHERE card_id=?", (form["card_id"],))
        self.assertTrue(self.client.get("/api/demo-card?buyer_id=2").json["card"]["expired"])
        self.assertEqual(post_form(self.client, f"/checkout/{product_id}", form).status_code, 400)
        replacement = self.add_card().json["card"]
        self.assertFalse(replacement["expired"])
        post_json(self.client, "/api/demo-card/remove", {"buyer_id": "2"})
        self.assertIsNone(self.client.get("/api/demo-card?buyer_id=2").json["card"])
        self.assertEqual(post_form(self.client, f"/checkout/{product_id}", form).status_code, 400)

    def test_card_storage_contains_no_number_or_cvv(self):
        response = self.add_card()
        self.assertEqual(response.status_code, 201)
        self.assertNotIn(b"4242424242424242", response.data)
        self.assertNotIn(b'"cvv"', response.data)
        self.assertNotIn(b'"number"', response.data)
        cookie = self.client.get_cookie("demo_wallet")
        self.assertTrue(cookie.http_only)
        self.assertEqual(cookie.same_site, "Lax")
        self.assertEqual(self.add_card(number="4111111111111111").status_code, 400)
        self.assertEqual(self.add_card(cvv="999").status_code, 400)
        with database.connect() as conn:
            row = conn.execute("SELECT * FROM demo_cards WHERE card_id=?", (response.json["card"]["card_id"],)).fetchone()
            self.assertNotIn("number", row.keys())
            self.assertNotIn("cvv", row.keys())
            self.assertNotIn(cookie.value, str(dict(row)))
            self.assertEqual(row["last4"], "4242")

    def test_checkout_rejects_invalid_input_and_self_purchase(self):
        product_id = self.create_listing()
        form = self.checkout_form(product_id)
        for changes in (dict(buyer_id="1"), dict(buyer_id="2147483647"), dict(payment_reference="invalid"),
                        dict(payment_method="Bitcoin"), dict(demo_result="paid")):
            with self.subTest(changes=changes):
                self.assertEqual(post_form(self.client, f"/checkout/{product_id}", {**form, **changes}).status_code, 400)
        self.assertEqual(self.client.get(f"/payments/{uuid.uuid4()}").status_code, 404)

    def test_concurrent_checkout_and_token_reuse(self):
        product_id = self.create_listing("Concurrent checkout")
        form = self.checkout_form(product_id)

        cookie = self.client.get_cookie("demo_wallet").value

        def submit(_):
            with web.app.test_client() as client:
                client.set_cookie("demo_wallet", cookie)
                response = post_form(client, f"/checkout/{product_id}", form)
                return response.status_code, response.location

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], 303)
        other_id = self.create_listing("Different checkout")
        self.assertEqual(post_form(self.client, f"/checkout/{other_id}", form).status_code, 409)
        # A competing buyer with a different reference cannot buy the sold item.
        other_card = self.add_card(buyer=3).json["card"]["card_id"]
        other_form = {**form, "buyer_id": "3", "card_id": other_card, "payment_reference": str(uuid.uuid4())}
        self.assertEqual(post_form(self.client, f"/checkout/{product_id}", other_form).status_code, 409)

    def register(self, client=None, **overrides):
        client = client or self.client
        suffix = uuid.uuid4().hex[:8]
        email = overrides.pop("email", None) or f"student-{suffix}@example.edu"
        data = dict(full_name="Test Student", student_number=f"2026{suffix}",
                    email=email, study_program="Computer Science",
                    study_year="2", password="password123", confirm_password="password123")
        data.update(overrides)
        self.last_email = data["email"]
        return post_form(client, "/register", data)

    def login(self, client=None, email=None, password="password123"):
        client = client or self.client
        return post_form(client, "/login", dict(email=email or self.last_email, password=password))

    def student_id_for(self, email):
        with database.connect() as conn:
            return conn.execute("SELECT student_id FROM student_credentials WHERE email=?",
                                (email,)).fetchone()["student_id"]

    def test_register_login_logout_flow(self):
        response = self.register()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)
        email = self.last_email
        self.assertEqual(self.client.get("/messages").status_code, 302)  # anonymous: redirected to login
        response = self.login(email=email)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/messages").status_code, 200)
        self.assertIn(b"Messages", self.client.get("/").data)
        response = post_form(self.client, "/logout")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/messages").status_code, 302)

    def test_register_rejects_existing_student_email(self):
        # Seeded student emails cannot be claimed without ownership verification.
        response = self.register(email="dana.omar@example.edu", student_number="2099999")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"already linked to a student record", response.data)
        with database.connect() as conn:
            self.assertIsNone(conn.execute(
                "SELECT 1 FROM student_credentials WHERE email='dana.omar@example.edu'").fetchone())
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM students WHERE email='dana.omar@example.edu'").fetchone()[0], 1)

    def test_register_validation_and_duplicate(self):
        self.assertEqual(self.register(password="short", confirm_password="short").status_code, 400)
        self.assertEqual(self.register(password="password123", confirm_password="different1").status_code, 400)
        self.assertEqual(self.register(email="not-an-email").status_code, 400)
        self.assertEqual(self.register(study_year="9").status_code, 400)
        first = self.register()
        self.assertEqual(first.status_code, 302)
        # Same email again is rejected.
        self.assertEqual(self.register(email=self.last_email, student_number="2088888").status_code, 400)

    def test_login_failures(self):
        self.register()
        email = self.last_email
        self.assertEqual(self.login(email=email, password="wrong-password").status_code, 401)
        self.assertEqual(self.login(email="nobody@example.edu").status_code, 401)
        self.assertEqual(self.client.get("/messages").status_code, 302)

    def test_messaging_requires_authentication(self):
        product_id = self.create_listing("Message me")
        self.assertEqual(self.client.get("/messages").status_code, 302)
        self.assertTrue(self.client.get("/messages").location.endswith("/login?next=/messages"))
        response = post_form(self.client, "/messages/start", {"product_id": str(product_id)})
        self.assertEqual(response.status_code, 302)  # CSRF passes; login_required redirects to /login
        self.assertIn("/login", response.location)

    def test_messaging_flow_and_authorization(self):
        buyer = web.app.test_client()
        self.assertEqual(self.register(client=buyer).status_code, 302)
        buyer_email = self.last_email
        self.assertEqual(self.login(client=buyer, email=buyer_email).status_code, 302)
        buyer_id = self.student_id_for(buyer_email)
        product_id = self.create_listing("Chat about this", seller_id=1)
        # Start a conversation as the registered buyer about a seeded seller's item.
        response = post_form(buyer, "/messages/start", {"product_id": str(product_id)})
        self.assertEqual(response.status_code, 303)
        chat_url = response.location
        self.assertIn("/messages/", chat_url)
        conversation_id = int(chat_url.rstrip("/").split("/")[-1].split("?")[0])
        self.assertEqual(buyer.get(chat_url).status_code, 200)
        # Inbox lists the conversation.
        self.assertIn(b"Chat about this", buyer.get("/messages").data)
        # Send a message.
        response = post_form(buyer, "/messages/send",
                             {"conversation_id": str(conversation_id), "message_text": "Is this still available?"})
        self.assertEqual(response.status_code, 303)
        updates = buyer.get(f"/messages/{conversation_id}/updates").get_json()
        self.assertEqual(len(updates["messages"]), 1)
        self.assertEqual(updates["messages"][0]["text"], "Is this still available?")
        self.assertEqual(updates["messages"][0]["sender_id"], buyer_id)
        # A different registered student is not a participant.
        other = web.app.test_client()
        self.register(client=other, student_number="2077777")
        other_email = self.last_email
        self.assertEqual(self.login(client=other, email=other_email).status_code, 302)
        self.assertEqual(other.get(f"/messages/{conversation_id}").status_code, 403)
        self.assertEqual(other.get(f"/messages/{conversation_id}/updates").status_code, 403)
        self.assertEqual(post_form(other, "/messages/send",
                                   {"conversation_id": str(conversation_id), "message_text": "intruder"}).status_code, 403)
        # The buyer cannot message their own listing.
        own_id = self.create_listing("My own item", seller_id=buyer_id)
        self.assertEqual(post_form(buyer, "/messages/start", {"product_id": str(own_id)}).status_code, 400)
        # Unknown conversation is a 404.
        self.assertEqual(buyer.get("/messages/999999").status_code, 404)

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
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0],
                             len(list((database.BASE_DIR / "backend/migrations").glob("*.sql"))))
        finally:
            # The temporary schema, data, and migration are all rolled back.
            conn.rollback()
            conn.close()


if __name__ == "__main__":
    unittest.main()
