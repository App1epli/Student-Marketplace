"""Authenticated student-to-student messaging about listings.

Adapted from the original demo messaging.py into a Flask blueprint. Every
route requires a logged-in student who is a participant in the conversation.
"""
from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, request, url_for

from backend import database
from backend.auth import current_student, login_required

bp = Blueprint("messaging", __name__, url_prefix="/messages")


@bp.errorhandler(403)
def forbidden(error):
    return render_template("error.html", title="Access denied",
                           message="You are not a participant in this conversation."), 403


def conversation_for(conn, conversation_id, student_id):
    conversation = conn.execute("""SELECT c.*, p.product_name,
            buyer.full_name AS buyer_name, seller.full_name AS seller_name
            FROM conversations c
            JOIN products p ON p.product_id = c.product_id
            JOIN students buyer ON buyer.student_id = c.buyer_id
            JOIN students seller ON seller.student_id = c.seller_id
            WHERE c.conversation_id = ?""", (conversation_id,)).fetchone()
    if conversation is None:
        abort(404)
    if student_id not in (conversation["buyer_id"], conversation["seller_id"]):
        abort(403)
    return conversation


@bp.get("")
@login_required
def inbox():
    user = current_student()
    with database.connect() as conn:
        rows = conn.execute("""SELECT c.conversation_id, p.product_name,
                buyer.full_name AS buyer_name, seller.full_name AS seller_name,
                (SELECT m.message_text FROM messages m WHERE m.conversation_id = c.conversation_id
                 ORDER BY m.message_id DESC LIMIT 1) AS last_message
            FROM conversations c
            JOIN products p ON p.product_id = c.product_id
            JOIN students buyer ON buyer.student_id = c.buyer_id
            JOIN students seller ON seller.student_id = c.seller_id
            WHERE c.buyer_id = ? OR c.seller_id = ?
            ORDER BY c.conversation_id DESC""", (user["student_id"], user["student_id"])).fetchall()
    return render_template("messages.html", title="Messages", rows=rows, user=user)


@bp.get("/<int:conversation_id>")
@login_required
def chat(conversation_id):
    user = current_student()
    with database.connect() as conn:
        conversation = conversation_for(conn, conversation_id, user["student_id"])
        rows = conn.execute("""SELECT m.message_id, m.sender_id, m.message_text,
                to_char(m.sent_at, 'YYYY-MM-DD HH24:MI:SS') AS sent_at,
                s.full_name AS sender
            FROM messages m JOIN students s ON s.student_id = m.sender_id
            WHERE m.conversation_id = ? ORDER BY m.message_id ASC LIMIT 500""",
            (conversation_id,)).fetchall()
    return render_template("chat.html", title="Chat", conversation=conversation,
                           rows=rows, user=user)


@bp.get("/<int:conversation_id>/updates")
@login_required
def updates(conversation_id):
    user = current_student()
    with database.connect() as conn:
        conversation_for(conn, conversation_id, user["student_id"])
        rows = conn.execute("""SELECT m.message_id, m.sender_id, m.message_text,
                to_char(m.sent_at, 'YYYY-MM-DD HH24:MI:SS') AS sent_at,
                s.full_name AS sender
            FROM messages m JOIN students s ON s.student_id = m.sender_id
            WHERE m.conversation_id = ? ORDER BY m.message_id ASC LIMIT 500""",
            (conversation_id,)).fetchall()
    return {"messages": [
        {"id": r["message_id"], "sender_id": r["sender_id"], "sender": r["sender"],
         "text": r["message_text"], "sent_at": r["sent_at"]} for r in rows]}


@bp.post("/start")
@login_required
def start():
    user = current_student()
    try:
        product_id = int(request.form.get("product_id", ""))
        if not 0 < product_id <= 2147483647:
            raise ValueError
    except ValueError:
        return render_template("error.html", title="Invalid item",
                               message="Choose an item from the catalog."), 400
    with database.connect() as conn:
        product = conn.execute("SELECT seller_id, status FROM products WHERE product_id=?",
                               (product_id,)).fetchone()
        if not product:
            abort(404)
        if product["seller_id"] == user["student_id"]:
            return render_template("error.html", title="Cannot message yourself",
                                   message="You cannot start a conversation about your own listing."), 400
        if product["status"] == "Removed":
            return render_template("error.html", title="Listing removed",
                                   message="This listing is no longer available."), 400
        result = conn.execute("""INSERT INTO conversations (product_id, buyer_id, seller_id)
            VALUES (?, ?, ?) ON CONFLICT (product_id, buyer_id)
            DO UPDATE SET seller_id = EXCLUDED.seller_id
            RETURNING conversation_id""",
            (product_id, user["student_id"], product["seller_id"])).fetchone()
    return redirect(url_for("messaging.chat", conversation_id=result["conversation_id"]), code=303)


@bp.post("/send")
@login_required
def send():
    user = current_student()
    try:
        conversation_id = int(request.form.get("conversation_id", ""))
    except ValueError:
        return render_template("error.html", title="Invalid conversation",
                               message="This conversation could not be found."), 400
    message = request.form.get("message_text", "").strip()
    if not 1 <= len(message) <= 2000:
        return render_template("error.html", title="Message not sent",
                               message="Messages must be between 1 and 2000 characters."), 400
    with database.connect() as conn:
        conversation_for(conn, conversation_id, user["student_id"])
        conn.execute("INSERT INTO messages (conversation_id, sender_id, message_text) VALUES (?, ?, ?)",
                     (conversation_id, user["student_id"], message))
    return redirect(url_for("messaging.chat", conversation_id=conversation_id), code=303)
