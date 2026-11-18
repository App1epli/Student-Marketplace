"""Telegram-style two-column messenger subsystem for student communications.

Provides an enhanced, responsive chat experience with left conversation list
and right message pane, sender/receiver speech bubbles, and live updates.
Reuses existing 'conversations' and 'messages' tables without altering the legacy
/messages routes.
"""
from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, request, url_for

from backend import auth, database
from backend.moderation import REPORT_REASONS

bp = Blueprint("messenger", __name__, url_prefix="/messenger")


@bp.errorhandler(403)
def forbidden(error):
    return render_template(
        "error.html",
        title="Access denied",
        message="You are not an authorized participant in this conversation."
    ), 403


def get_user_conversations(conn, student_id: int):
    """Retrieve all conversations for the student with latest message preview."""
    return conn.execute(
        """SELECT c.conversation_id, p.product_name, p.product_id,
                  buyer.student_id AS buyer_id, buyer.full_name AS buyer_name,
                  seller.student_id AS seller_id, seller.full_name AS seller_name,
                  (SELECT m.message_text FROM messages m WHERE m.conversation_id = c.conversation_id
                   ORDER BY m.message_id DESC LIMIT 1) AS last_message,
                  (SELECT to_char(m.sent_at, 'HH24:MI') FROM messages m WHERE m.conversation_id = c.conversation_id
                   ORDER BY m.message_id DESC LIMIT 1) AS last_message_time,
                  (SELECT m.sender_id FROM messages m WHERE m.conversation_id = c.conversation_id
                   ORDER BY m.message_id DESC LIMIT 1) AS last_sender_id
           FROM conversations c
           JOIN products p ON p.product_id = c.product_id
           JOIN students buyer ON buyer.student_id = c.buyer_id
           JOIN students seller ON seller.student_id = c.seller_id
           WHERE c.buyer_id = ? OR c.seller_id = ?
           ORDER BY c.conversation_id DESC""",
        (student_id, student_id)
    ).fetchall()


def conversation_for(conn, conversation_id: int, student_id: int):
    """Fetch conversation details and ensure student is an authorized participant."""
    conversation = conn.execute(
        """SELECT c.*, p.product_name, p.price,
                  buyer.full_name AS buyer_name, buyer.student_id AS buyer_id,
                  seller.full_name AS seller_name, seller.student_id AS seller_id
           FROM conversations c
           JOIN products p ON p.product_id = c.product_id
           JOIN students buyer ON buyer.student_id = c.buyer_id
           JOIN students seller ON seller.student_id = c.seller_id
           WHERE c.conversation_id = ?""",
        (conversation_id,)
    ).fetchone()
    if conversation is None:
        abort(404)
    if student_id not in (conversation["buyer_id"], conversation["seller_id"]):
        abort(403)
    return conversation


@bp.get("")
@auth.login_required
def index():
    """Messenger home: lists conversations in the left sidebar."""
    user = auth.current_student()
    with database.connect() as conn:
        conversations = get_user_conversations(conn, user["student_id"])

    # If user has conversations, show the messenger with the list
    return render_template(
        "messenger.html",
        title="Messenger",
        user=user,
        conversations=conversations,
        selected_conversation=None
    )


@bp.get("/<int:conversation_id>")
@auth.login_required
def chat(conversation_id: int):
    """View active chat in two-column messenger layout."""
    user = auth.current_student()
    with database.connect() as conn:
        conversation = conversation_for(conn, conversation_id, user["student_id"])
        conversations = get_user_conversations(conn, user["student_id"])
        rows = conn.execute(
            """SELECT m.message_id, m.sender_id, m.message_text,
                      to_char(m.sent_at, 'HH24:MI') AS sent_time,
                      to_char(m.sent_at, 'YYYY-MM-DD HH24:MI:SS') AS sent_at,
                      s.full_name AS sender
               FROM messages m
               JOIN students s ON s.student_id = m.sender_id
               WHERE m.conversation_id = ?
               ORDER BY m.message_id ASC LIMIT 500""",
            (conversation_id,)
        ).fetchall()

        # Check for active report by this student on this conversation
        active_report = None
        try:
            active_report = conn.execute(
                """SELECT report_id, status, reason
                   FROM moderation_reports
                   WHERE conversation_id = ? AND reporter_id = ?
                     AND status IN ('Pending', 'Under Review')""",
                (conversation_id, user["student_id"])
            ).fetchone()
        except Exception:
            pass

    return render_template(
        "messenger_chat.html",
        title=f"Chat: {conversation['product_name']}",
        user=user,
        conversations=conversations,
        conversation=conversation,
        rows=rows,
        report_reasons=REPORT_REASONS,
        active_report=active_report
    )


@bp.get("/<int:conversation_id>/updates")
@auth.login_required
def updates(conversation_id: int):
    """Live polling endpoint for message updates (JSON)."""
    user = auth.current_student()
    with database.connect() as conn:
        conversation_for(conn, conversation_id, user["student_id"])
        rows = conn.execute(
            """SELECT m.message_id, m.sender_id, m.message_text,
                      to_char(m.sent_at, 'HH24:MI') AS sent_time,
                      to_char(m.sent_at, 'YYYY-MM-DD HH24:MI:SS') AS sent_at,
                      s.full_name AS sender
               FROM messages m
               JOIN students s ON s.student_id = m.sender_id
               WHERE m.conversation_id = ?
               ORDER BY m.message_id ASC LIMIT 500""",
            (conversation_id,)
        ).fetchall()

    return {
        "messages": [
            {
                "id": r["message_id"],
                "sender_id": r["sender_id"],
                "sender": r["sender"],
                "text": r["message_text"],
                "sent_time": r["sent_time"],
                "sent_at": r["sent_at"]
            }
            for r in rows
        ]
    }


@bp.post("/<int:conversation_id>/send")
@bp.post("/send")
@auth.login_required
def send(conversation_id: int | None = None):
    """Send a message within an existing conversation."""
    user = auth.current_student()
    cid = conversation_id or request.form.get("conversation_id")
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        return render_template(
            "error.html",
            title="Invalid conversation",
            message="This conversation could not be found."
        ), 400

    message = request.form.get("message_text", "").strip()
    if not 1 <= len(message) <= 2000:
        return render_template(
            "error.html",
            title="Message not sent",
            message="Messages must be between 1 and 2,000 characters."
        ), 400

    with database.connect() as conn:
        conversation_for(conn, cid, user["student_id"])
        conn.execute(
            "INSERT INTO messages (conversation_id, sender_id, message_text) VALUES (?, ?, ?)",
            (cid, user["student_id"], message)
        )

    if request.headers.get("Accept") == "application/json" or request.is_json:
        return {"status": "ok"}

    return redirect(url_for("messenger.chat", conversation_id=cid), code=303)


@bp.post("/start")
@auth.login_required
def start():
    """Start or open a conversation from a product listing, landing in /messenger."""
    user = auth.current_student()
    try:
        product_id = int(request.form.get("product_id", ""))
        if not 0 < product_id <= 2147483647:
            raise ValueError
    except ValueError:
        return render_template("error.html", title="Invalid item", message="Choose an item from the catalog."), 400

    with database.connect() as conn:
        product = conn.execute("SELECT seller_id, status FROM products WHERE product_id=?", (product_id,)).fetchone()
        if not product:
            abort(404)
        if product["seller_id"] == user["student_id"]:
            return render_template("error.html", title="Cannot message yourself", message="You cannot start a conversation about your own listing."), 400
        if product["status"] == "Removed":
            return render_template("error.html", title="Listing removed", message="This listing is no longer available."), 400

        result = conn.execute(
            """INSERT INTO conversations (product_id, buyer_id, seller_id)
               VALUES (?, ?, ?) ON CONFLICT (product_id, buyer_id)
               DO UPDATE SET seller_id = EXCLUDED.seller_id
               RETURNING conversation_id""",
            (product_id, user["student_id"], product["seller_id"])
        ).fetchone()

    return redirect(url_for("messenger.chat", conversation_id=result["conversation_id"]), code=303)
