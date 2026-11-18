"""Automated tests for RBAC, Telegram-style Messenger, Moderation reporting, and Admin dashboard.

Exercises:
1. Student role by default.
2. Admin-only access.
3. Student cannot access admin dashboard.
4. Student cannot view another student's conversation.
5. Student cannot submit reports for unrelated conversations.
6. Duplicate active reports are rejected.
7. Admin can review reports and reported messages.
8. Admin actions are logged in the audit trail.
9. Existing messaging remains unchanged.
10. Existing authentication remains unchanged.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend import admin, app as web_module, auth, database, messenger, moderation, rbac
from tests.test_app import csrf_token_for, post_form


class RBACAndModerationUnitTests(unittest.TestCase):
    def setUp(self):
        self.client = web_module.app.test_client()

    def set_session_user(self, student_id: int):
        with self.client.session_transaction() as sess:
            sess["student_id"] = student_id

    # 1. Student role by default
    def test_default_role_is_student(self):
        with patch.object(database, "connect") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None
            mock_conn.return_value.__enter__.return_value.execute.return_value = mock_cursor

            self.assertEqual(rbac.get_user_role(123), "student")
            self.assertFalse(rbac.is_admin(123))

    # 2. Admin-only access
    def test_admin_only_access_granted_when_admin(self):
        self.set_session_user(99)
        with patch.object(auth, "current_student", return_value={"student_id": 99, "full_name": "Admin User"}):
            with patch.object(rbac, "get_user_role", return_value="admin"):
                with patch.object(database, "connect") as mock_db:
                    mock_cursor = MagicMock()
                    mock_cursor.fetchall.return_value = []
                    mock_db.return_value.__enter__.return_value.execute.return_value = mock_cursor

                    response = self.client.get("/admin/dashboard")
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(b"Moderation Dashboard", response.data)

    # 3. Student cannot access admin dashboard
    def test_student_cannot_access_admin_dashboard(self):
        # Case A: Unauthenticated -> redirects to login
        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/login?next=/admin/dashboard"))

        # Case B: Authenticated as normal student -> 403 Forbidden
        self.set_session_user(5)
        with patch.object(auth, "current_student", return_value={"student_id": 5, "full_name": "Normal Student"}):
            with patch.object(rbac, "get_user_role", return_value="student"):
                response = self.client.get("/admin/dashboard")
                self.assertEqual(response.status_code, 403)
                self.assertIn(b"Access denied", response.data)

                response_reports = self.client.get("/admin/reports")
                self.assertEqual(response_reports.status_code, 403)

    # 4. Student cannot view another student's conversation in messenger
    def test_student_cannot_view_another_students_conversation(self):
        self.set_session_user(3)
        # Conversation between student 1 and student 2; current student is 3
        with patch.object(auth, "current_student", return_value={"student_id": 3, "full_name": "Intruder"}):
            with patch.object(database, "connect") as mock_db:
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = {
                    "conversation_id": 10,
                    "product_id": 1,
                    "buyer_id": 1,
                    "seller_id": 2,
                    "product_name": "Test Book",
                    "price": 1000,
                    "buyer_name": "Buyer",
                    "seller_name": "Seller"
                }
                mock_db.return_value.__enter__.return_value.execute.return_value = mock_cursor

                # GET /messenger/10 -> 403
                res = self.client.get("/messenger/10")
                self.assertEqual(res.status_code, 403)

                # GET /messenger/10/updates -> 403
                res_up = self.client.get("/messenger/10/updates")
                self.assertEqual(res_up.status_code, 403)

                # POST /messenger/10/send -> 403
                res_send = post_form(self.client, "/messenger/10/send", {"message_text": "hello"})
                self.assertEqual(res_send.status_code, 403)

    # 5. Student cannot submit reports for unrelated conversations
    def test_student_cannot_submit_report_for_unrelated_conversation(self):
        self.set_session_user(3)
        with patch.object(auth, "current_student", return_value={"student_id": 3, "full_name": "Outsider"}):
            with patch.object(database, "connect") as mock_db:
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = {
                    "conversation_id": 10,
                    "buyer_id": 1,
                    "seller_id": 2,
                    "product_id": 1
                }
                mock_db.return_value.__enter__.return_value.execute.return_value = mock_cursor

                response = post_form(self.client, "/moderation/report", {
                    "conversation_id": "10",
                    "reason": "Scam / Fraud",
                    "explanation": "Trying to report someone else's chat"
                })
                self.assertEqual(response.status_code, 403)

    # 6. Duplicate active reports are rejected
    def test_duplicate_active_reports_rejected(self):
        self.set_session_user(1)
        with patch.object(auth, "current_student", return_value={"student_id": 1, "full_name": "Valid Buyer"}):
            with patch.object(rbac, "is_admin", return_value=False):
                with patch.object(database, "connect") as mock_db, patch.object(web_module, "connect", mock_db):
                    def execute_query(query, params=()):
                        cursor = MagicMock()
                        if "FROM conversations" in query:
                            cursor.fetchone.return_value = {"conversation_id": 10, "buyer_id": 1, "seller_id": 2, "product_id": 1}
                        elif "FROM moderation_reports" in query:
                            cursor.fetchone.return_value = {"report_id": 42, "status": "Pending"}
                        else:
                            cursor.fetchone.return_value = None
                        return cursor

                    conn_mock = MagicMock()
                    conn_mock.execute.side_effect = execute_query
                    mock_db.return_value.__enter__.return_value = conn_mock

                    response = post_form(self.client, "/moderation/report", {
                        "conversation_id": "10",
                        "reason": "Harassment",
                        "explanation": "Second report attempt"
                    })
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(b"Report already submitted", response.data)

    # 7. Admin can review reports and reported messages
    def test_admin_can_review_reports_and_conversation(self):
        self.set_session_user(99)
        with patch.object(auth, "current_student", return_value={"student_id": 99, "full_name": "Admin"}):
            with patch.object(rbac, "get_user_role", return_value="admin"):
                with patch.object(database, "connect") as mock_db:
                    mock_cursor = MagicMock()
                    mock_cursor.fetchone.return_value = {
                        "report_id": 1,
                        "conversation_id": 10,
                        "reason": "Spam",
                        "explanation": "Flooding messages",
                        "status": "Pending",
                        "created_at": "2026-11-19 01:00:00",
                        "updated_at": "2026-11-19 01:00:00",
                        "reporter_name": "Student One",
                        "reporter_email": "student1@example.edu",
                        "buyer_id": 1,
                        "seller_id": 2,
                        "product_id": 1,
                        "product_name": "Calculator",
                        "buyer_name": "Student One",
                        "seller_name": "Student Two"
                    }
                    mock_cursor.fetchall.side_effect = [
                        [{"message_id": 1, "sender_id": 2, "message_text": "Spam spam spam", "sent_at": "2026-11-19 01:01:00", "sender": "Student Two"}],
                        []  # audit history
                    ]
                    mock_db.return_value.__enter__.return_value.execute.return_value = mock_cursor

                    response = self.client.get("/admin/reports/1")
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(b"Report #1", response.data)
                    self.assertIn(b"Spam spam spam", response.data)

    # 8. Admin actions are logged
    def test_admin_actions_are_logged(self):
        self.set_session_user(99)
        with patch.object(auth, "current_student", return_value={"student_id": 99, "full_name": "Admin"}):
            with patch.object(rbac, "get_user_role", return_value="admin"):
                with patch.object(database, "connect") as mock_db:
                    conn_instance = mock_db.return_value.__enter__.return_value
                    mock_cursor = MagicMock()
                    mock_cursor.fetchone.return_value = {"report_id": 1, "conversation_id": 10, "status": "Pending"}
                    conn_instance.execute.return_value = mock_cursor

                    response = post_form(self.client, "/admin/reports/1/status", {
                        "status": "Resolved",
                        "notes": "Seller was warned"
                    })
                    self.assertEqual(response.status_code, 303)

                    # Verify that INSERT INTO moderation_logs was called
                    calls = [call[0][0] for call in conn_instance.execute.call_args_list]
                    has_log_insert = any("INSERT INTO moderation_logs" in query for query in calls)
                    self.assertTrue(has_log_insert, "Moderation action was not logged in moderation_logs")

    # 9. Existing messaging remains unchanged
    def test_existing_messaging_remains_unchanged(self):
        self.set_session_user(1)
        with patch.object(auth, "current_student", return_value={"student_id": 1, "full_name": "Student"}):
            with patch.object(database, "connect") as mock_db:
                mock_cursor = MagicMock()
                mock_cursor.fetchall.return_value = []
                mock_db.return_value.__enter__.return_value.execute.return_value = mock_cursor

                res = self.client.get("/messages")
                self.assertEqual(res.status_code, 200)
                self.assertIn(b"Student messages", res.data)

    # 10. Existing authentication remains unchanged
    def test_existing_auth_remains_unchanged(self):
        with patch.object(database, "connect", side_effect=AssertionError("Unexpected DB access")):
            self.assertEqual(self.client.get("/login").status_code, 200)
            self.assertEqual(self.client.get("/register").status_code, 200)
            self.assertIn(b"Log in", self.client.get("/login").data)
            self.assertIn(b"Create account", self.client.get("/register").data)

    # 11. Navigation Messages link points to new Messenger route
    def test_navigation_messages_link_points_to_messenger(self):
        with patch.object(database, "connect", side_effect=AssertionError("Unexpected DB access")):
            res = self.client.get("/login")
            self.assertEqual(res.status_code, 200)
            html = res.get_data(as_text=True)
            self.assertIn('href="/messenger"', html)
            # Ensure the old /messages is not used as the main navigation link
            self.assertNotIn('href="/messages"', html)

    # 12. Navigation Admin Dashboard link visibility by role
    def test_navigation_admin_dashboard_visibility_by_role(self):
        # Unauthenticated: no Admin Dashboard link
        with patch.object(database, "connect", side_effect=AssertionError("Unexpected DB access")):
            res = self.client.get("/login")
            self.assertEqual(res.status_code, 200)
            self.assertNotIn("Admin Dashboard", res.get_data(as_text=True))

        # Logged in as standard student: no Admin Dashboard link
        self.set_session_user(1)
        with patch.object(auth, "current_student", return_value={"student_id": 1, "full_name": "Student User"}):
            with patch.object(rbac, "is_admin", return_value=False):
                with patch.object(database, "connect") as mock_db, patch.object(web_module, "connect", mock_db):
                    mock_cursor = MagicMock()
                    mock_cursor.fetchall.return_value = []
                    mock_db.return_value.__enter__.return_value.execute.return_value = mock_cursor

                    res = self.client.get("/sales")
                    self.assertEqual(res.status_code, 200)
                    html = res.get_data(as_text=True)
                    self.assertNotIn("Admin Dashboard", html)
                    self.assertIn("Student account", html)

        # Logged in as administrator: Admin Dashboard link is rendered
        self.set_session_user(99)
        with patch.object(auth, "current_student", return_value={"student_id": 99, "full_name": "Admin User"}):
            with patch.object(rbac, "is_admin", return_value=True):
                with patch.object(database, "connect") as mock_db, patch.object(web_module, "connect", mock_db):
                    mock_cursor = MagicMock()
                    mock_cursor.fetchall.return_value = []
                    mock_db.return_value.__enter__.return_value.execute.return_value = mock_cursor

                    res = self.client.get("/sales")
                    self.assertEqual(res.status_code, 200)
                    html = res.get_data(as_text=True)
                    self.assertIn('href="/admin/dashboard"', html)
                    self.assertIn("Admin Dashboard", html)
                    self.assertIn("Administrator", html)

    # 13. Navigation active state highlighting
    def test_navigation_active_highlighting(self):
        # Messenger active highlighting
        self.set_session_user(1)
        with patch.object(auth, "current_student", return_value={"student_id": 1, "full_name": "Student User"}):
            with patch.object(database, "connect") as mock_db:
                mock_cursor = MagicMock()
                mock_cursor.fetchall.return_value = []
                mock_db.return_value.__enter__.return_value.execute.return_value = mock_cursor

                res = self.client.get("/messenger")
                self.assertEqual(res.status_code, 200)
                html = res.get_data(as_text=True)
                self.assertIn('class="active" href="/messenger"', html)

        # Admin active highlighting
        self.set_session_user(99)
        with patch.object(auth, "current_student", return_value={"student_id": 99, "full_name": "Admin User"}):
            with patch.object(rbac, "is_admin", return_value=True):
                with patch.object(rbac, "get_user_role", return_value="admin"):
                    with patch.object(database, "connect") as mock_db:
                        mock_cursor = MagicMock()
                        mock_cursor.fetchall.return_value = []
                        mock_db.return_value.__enter__.return_value.execute.return_value = mock_cursor

                        res = self.client.get("/admin/dashboard")
                        self.assertEqual(res.status_code, 200)
                        html = res.get_data(as_text=True)
                        self.assertIn('class="active" href="/admin/dashboard"', html)

    # 14. Catalog contact seller initiates new Messenger flow
    def test_catalog_contact_seller_initiates_messenger(self):
        with patch.object(auth, "current_student", return_value={"student_id": 2, "full_name": "Buyer Student"}):
            with patch.object(database, "connect") as mock_db, patch.object(web_module, "connect", mock_db):
                def execute_catalog(query, params=()):
                    cursor = MagicMock()
                    if "FROM categories" in query:
                        cursor.fetchall.return_value = [{"category_id": 1, "category_name": "Books and Study"}]
                    elif "FROM products" in query:
                        cursor.fetchall.return_value = [{
                            "product_id": 1,
                            "product_name": "Textbook",
                            "description": "Good condition",
                            "price": 2000,
                            "item_condition": "Good",
                            "status": "Available",
                            "category_name": "Books and Study",
                            "seller": "Seller Student",
                            "seller_id": 1,
                            "rating": None,
                            "review_count": 0,
                            "product_rating": None,
                            "product_rating_count": 0,
                            "my_stars": None,
                            "photo_id": None
                        }]
                    else:
                        cursor.fetchall.return_value = []
                    return cursor

                conn_mock = MagicMock()
                conn_mock.execute.side_effect = execute_catalog
                mock_db.return_value.__enter__.return_value = conn_mock

                res = self.client.get("/")
                self.assertEqual(res.status_code, 200)
                html = res.get_data(as_text=True)
                self.assertIn('action="/messenger/start"', html)


if __name__ == "__main__":
    unittest.main()
