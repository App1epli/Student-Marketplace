"""Conversation reporting and student moderation subsystem.

Allows conversation participants to report suspicious or abusive activity.
Enforces participant verification and prevents duplicate active reports.
"""
from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, request, url_for

from backend import auth, database

bp = Blueprint("moderation", __name__, url_prefix="/moderation")

REPORT_REASONS = (
    "Scam / Fraud",
    "Harassment",
    "Spam",
    "Suspicious Activity",
    "Other",
)

REPORT_STATUSES = (
    "Pending",
    "Under Review",
    "Resolved",
    "Dismissed",
)


def log_moderation_action(conn, admin_id: int, action: str, target_type: str, target_id: int, details: str = ""):
    """Record an administrative or moderation action in the audit log."""
    conn.execute(
        """INSERT INTO moderation_logs (admin_id, action, target_type, target_id, details)
           VALUES (?, ?, ?, ?, ?)""",
        (admin_id, action, target_type, target_id, details or "")
    )


def verify_conversation_participant(conn, conversation_id: int, student_id: int):
    """Ensure the conversation exists and student is an active participant."""
    conversation = conn.execute(
        """SELECT conversation_id, buyer_id, seller_id, product_id
           FROM conversations
           WHERE conversation_id = ?""",
        (conversation_id,)
    ).fetchone()
    if conversation is None:
        abort(404)
    if student_id not in (conversation["buyer_id"], conversation["seller_id"]):
        abort(403)
    return conversation


@bp.post("/report")
@auth.login_required
def submit_report():
    """Submit a report for an existing conversation by a participant."""
    user = auth.current_student()
    try:
        conversation_id = int(request.form.get("conversation_id", ""))
    except (TypeError, ValueError):
        return render_template(
            "error.html",
            title="Invalid conversation",
            message="The requested conversation was not found."
        ), 400

    reason = request.form.get("reason", "").strip()
    if reason not in REPORT_REASONS:
        return render_template(
            "error.html",
            title="Invalid report reason",
            message="Please choose a valid reason from the provided list."
        ), 400

    explanation = request.form.get("explanation", "").strip()
    if len(explanation) > 1000:
        return render_template(
            "error.html",
            title="Explanation too long",
            message="Explanation must be 1,000 characters or fewer."
        ), 400

    with database.connect() as conn:
        verify_conversation_participant(conn, conversation_id, user["student_id"])

        # Check for existing active report (Pending or Under Review)
        existing = conn.execute(
            """SELECT report_id, status FROM moderation_reports
               WHERE conversation_id = ? AND reporter_id = ?
                 AND status IN ('Pending', 'Under Review')""",
            (conversation_id, user["student_id"])
        ).fetchone()

        if existing:
            return render_template(
                "error.html",
                title="Report already submitted",
                message=f"You already have an active report for this conversation (status: {existing['status']})."
            ), 400

        try:
            conn.execute(
                """INSERT INTO moderation_reports
                   (conversation_id, reporter_id, reason, explanation, status)
                   VALUES (?, ?, ?, ?, 'Pending')
                   ON CONFLICT (conversation_id, reporter_id)
                   DO UPDATE SET reason = EXCLUDED.reason,
                                 explanation = EXCLUDED.explanation,
                                 status = 'Pending',
                                 updated_at = CURRENT_TIMESTAMP""",
                (conversation_id, user["student_id"], reason, explanation)
            )
        except Exception:
            # Fallback direct insert if conflict handling table definition varies
            conn.execute(
                """INSERT INTO moderation_reports
                   (conversation_id, reporter_id, reason, explanation, status)
                   VALUES (?, ?, ?, ?, 'Pending')""",
                (conversation_id, user["student_id"], reason, explanation)
            )

    return redirect(
        url_for("messenger.chat", conversation_id=conversation_id, notice="Report submitted. Our moderation team will review this conversation."),
        code=303
    )
