"""Administrative dashboard and moderation interface.

Provides authorized administrators with audit-logged oversight of reported
conversations and moderation workflows. Unrestricted access to private chats
is strictly prohibited; message review is confined exclusively to explicitly
reported conversations and is fully audit-logged.
"""
from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, request, url_for

from backend import auth, database
from backend.moderation import REPORT_STATUSES, log_moderation_action
from backend.rbac import admin_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("/dashboard")
@admin_required
def dashboard():
    """Admin overview showing platform statistics and recent audit activities."""
    user = auth.current_student()
    with database.connect() as conn:
        # Report counts by status
        counts = {"Pending": 0, "Under Review": 0, "Resolved": 0, "Dismissed": 0, "Total": 0}
        rows = conn.execute(
            """SELECT status, COUNT(*) AS count
               FROM moderation_reports
               GROUP BY status"""
        ).fetchall()
        for r in rows:
            counts[r["status"]] = r["count"]
            counts["Total"] += r["count"]

        # Recent 5 reports
        recent_reports = conn.execute(
            """SELECT r.report_id, r.conversation_id, r.reason, r.status,
                      to_char(r.created_at, 'YYYY-MM-DD HH24:MI') AS created_at,
                      reporter.full_name AS reporter_name,
                      p.product_name
               FROM moderation_reports r
               JOIN students reporter ON reporter.student_id = r.reporter_id
               JOIN conversations c ON c.conversation_id = r.conversation_id
               JOIN products p ON p.product_id = c.product_id
               ORDER BY r.report_id DESC LIMIT 5"""
        ).fetchall()

        # Recent 10 moderation log entries
        logs = conn.execute(
            """SELECT l.log_id, l.action, l.target_type, l.target_id, l.details,
                      to_char(l.created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
                      s.full_name AS admin_name
               FROM moderation_logs l
               JOIN students s ON s.student_id = l.admin_id
               ORDER BY l.log_id DESC LIMIT 10"""
        ).fetchall()

    return render_template(
        "admin_dashboard.html",
        title="Admin Dashboard",
        user=user,
        counts=counts,
        recent_reports=recent_reports,
        logs=logs
    )


@bp.get("/reports")
@admin_required
def reports():
    """List submitted moderation reports with status filtering."""
    user = auth.current_student()
    status_filter = request.args.get("status", "All").strip()

    query = """
        SELECT r.report_id, r.conversation_id, r.reason, r.explanation, r.status,
               to_char(r.created_at, 'YYYY-MM-DD HH24:MI') AS created_at,
               reporter.full_name AS reporter_name,
               p.product_name,
               buyer.full_name AS buyer_name,
               seller.full_name AS seller_name
        FROM moderation_reports r
        JOIN students reporter ON reporter.student_id = r.reporter_id
        JOIN conversations c ON c.conversation_id = r.conversation_id
        JOIN products p ON p.product_id = c.product_id
        JOIN students buyer ON buyer.student_id = c.buyer_id
        JOIN students seller ON seller.student_id = c.seller_id
    """
    params = []
    if status_filter in REPORT_STATUSES:
        query += " WHERE r.status = ?"
        params.append(status_filter)

    query += " ORDER BY r.report_id DESC LIMIT 100"

    with database.connect() as conn:
        report_list = conn.execute(query, tuple(params)).fetchall()

    return render_template(
        "admin_reports.html",
        title="Moderation Reports",
        user=user,
        reports=report_list,
        current_status=status_filter,
        statuses=REPORT_STATUSES,
        selected_report=None,
        messages=[]
    )


@bp.get("/reports/<int:report_id>")
@admin_required
def report_detail(report_id: int):
    """View details of a reported conversation. Access is strictly audited."""
    user = auth.current_student()
    with database.connect() as conn:
        report = conn.execute(
            """SELECT r.report_id, r.conversation_id, r.reason, r.explanation, r.status,
                      to_char(r.created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
                      to_char(r.updated_at, 'YYYY-MM-DD HH24:MI:SS') AS updated_at,
                      reporter.full_name AS reporter_name,
                      reporter.email AS reporter_email,
                      c.buyer_id, c.seller_id,
                      p.product_id, p.product_name,
                      buyer.full_name AS buyer_name,
                      seller.full_name AS seller_name
               FROM moderation_reports r
               JOIN students reporter ON reporter.student_id = r.reporter_id
               JOIN conversations c ON c.conversation_id = r.conversation_id
               JOIN products p ON p.product_id = c.product_id
               JOIN students buyer ON buyer.student_id = c.buyer_id
               JOIN students seller ON seller.student_id = c.seller_id
               WHERE r.report_id = ?""",
            (report_id,)
        ).fetchone()

        if not report:
            abort(404)

        # Audit log the access to this reported conversation
        log_moderation_action(
            conn,
            admin_id=user["student_id"],
            action="VIEW_REPORTED_CONVERSATION",
            target_type="report",
            target_id=report_id,
            details=f"Admin viewed reported conversation {report['conversation_id']} (Report #{report_id})"
        )

        # Read-only retrieval of the messages belonging strictly to this conversation
        messages = conn.execute(
            """SELECT m.message_id, m.sender_id, m.message_text,
                      to_char(m.sent_at, 'YYYY-MM-DD HH24:MI:SS') AS sent_at,
                      s.full_name AS sender
               FROM messages m
               JOIN students s ON s.student_id = m.sender_id
               WHERE m.conversation_id = ?
               ORDER BY m.message_id ASC LIMIT 500""",
            (report["conversation_id"],)
        ).fetchall()

        # Audit history for this report
        audit_history = conn.execute(
            """SELECT l.log_id, l.action, l.details,
                      to_char(l.created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
                      s.full_name AS admin_name
               FROM moderation_logs l
               JOIN students s ON s.student_id = l.admin_id
               WHERE l.target_type = 'report' AND l.target_id = ?
               ORDER BY l.log_id DESC""",
            (report_id,)
        ).fetchall()

    return render_template(
        "admin_reports.html",
        title=f"Report #{report_id}",
        user=user,
        reports=[],
        current_status="All",
        statuses=REPORT_STATUSES,
        selected_report=report,
        messages=messages,
        audit_history=audit_history
    )


@bp.post("/reports/<int:report_id>/status")
@admin_required
def update_status(report_id: int):
    """Update report review status. Action is strictly recorded in the audit log."""
    user = auth.current_student()
    new_status = request.form.get("status", "").strip()
    notes = request.form.get("notes", "").strip()

    if new_status not in REPORT_STATUSES:
        return render_template(
            "error.html",
            title="Invalid Status",
            message=f"Status must be one of: {', '.join(REPORT_STATUSES)}"
        ), 400

    with database.connect() as conn:
        report = conn.execute(
            "SELECT report_id, conversation_id, status FROM moderation_reports WHERE report_id = ?",
            (report_id,)
        ).fetchone()

        if not report:
            abort(404)

        old_status = report["status"]
        conn.execute(
            """UPDATE moderation_reports
               SET status = ?, updated_at = CURRENT_TIMESTAMP
               WHERE report_id = ?""",
            (new_status, report_id)
        )

        log_moderation_action(
            conn,
            admin_id=user["student_id"],
            action="UPDATE_REPORT_STATUS",
            target_type="report",
            target_id=report_id,
            details=f"Status updated from '{old_status}' to '{new_status}'. Notes: {notes or 'None'}"
        )

    return redirect(
        url_for("admin.report_detail", report_id=report_id, notice=f"Status updated to {new_status}"),
        code=303
    )
