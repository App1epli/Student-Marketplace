"""Student accounts: email + password credentials linked to student records.

Registration always creates a NEW students row. An email that already belongs
to a student record cannot be claimed without a separate ownership check, so
such registrations are rejected and must be provisioned by an administrator.
"""
from __future__ import annotations

import re
from functools import wraps

from flask import Blueprint, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from backend import database

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STUDENT_COLUMNS = "student_id, student_number, full_name, email, study_program, study_year"


def current_student():
    """The logged-in student row, or None. Cached per request; DB errors mean logged out."""
    if "student_id" not in session:
        return None
    if not hasattr(g, "student"):
        try:
            with database.connect() as conn:
                g.student = conn.execute(
                    f"SELECT {STUDENT_COLUMNS} FROM students WHERE student_id=?",
                    (session["student_id"],)).fetchone()
        except Exception:
            g.student = None
    return g.student


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_student() is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@bp.app_context_processor
def inject_current_user():
    return {"current_user": current_student()}


def registration_error(message, form):
    return render_template("register.html", title="Create account", form=form,
                           error=message, years=range(1, 5)), 400


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", title="Create account", form={},
                               error="", years=range(1, 5))
    form = request.form
    full_name = form.get("full_name", "").strip()
    student_number = form.get("student_number", "").strip()
    email = form.get("email", "").strip().lower()
    study_program = form.get("study_program", "").strip()
    study_year = form.get("study_year", "")
    password = form.get("password", "")
    confirm = form.get("confirm_password", "")

    if not (2 <= len(full_name) <= 120):
        return registration_error("Enter your full name.", form)
    if not (1 <= len(student_number) <= 30):
        return registration_error("Enter your student number.", form)
    if not (3 <= len(email) <= 254 and EMAIL_RE.match(email)):
        return registration_error("Enter a valid email address.", form)
    if not (2 <= len(study_program) <= 120):
        return registration_error("Enter your study program.", form)
    try:
        year = int(study_year)
        if not 1 <= year <= 4:
            raise ValueError
    except ValueError:
        return registration_error("Choose your study year.", form)
    if len(password) < 8:
        return registration_error("Password must be at least 8 characters.", form)
    if password != confirm:
        return registration_error("Passwords do not match.", form)

    try:
        with database.connect() as conn:
            # An email already tied to a student record cannot be claimed here:
            # ownership is not verified, so registration is refused instead.
            if conn.execute("SELECT 1 FROM students WHERE email=?", (email,)).fetchone():
                return registration_error(
                    "This email is already linked to a student record. "
                    "Ask an administrator to attach a login to it.", form)
            if conn.execute("SELECT 1 FROM student_credentials WHERE email=?", (email,)).fetchone():
                return registration_error("An account with this email already exists. Log in instead.", form)
            row = conn.execute(
                """INSERT INTO students (student_number, full_name, email, study_program, study_year)
                   VALUES (?, ?, ?, ?, ?) RETURNING student_id""",
                (student_number, full_name, email, study_program, year)).fetchone()
            conn.execute(
                "INSERT INTO student_credentials (student_id, email, password_hash) VALUES (?, ?, ?)",
                (row["student_id"], email, generate_password_hash(password)))
    except database.psycopg2.IntegrityError:
        return registration_error(
            "Registration failed: the student number or email may already be in use.", form)
    except database.psycopg2.Error:
        return registration_error("The database is unavailable. Please try again later.", form)
    return redirect(url_for("auth.login", notice="Account created. Log in to continue."))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if current_student() is not None:
            return redirect(url_for("catalog"))
        return render_template("login.html", title="Log in", error="",
                               notice=request.args.get("notice", ""))
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    credential = None
    try:
        with database.connect() as conn:
            credential = conn.execute(
                "SELECT student_id, password_hash FROM student_credentials WHERE email=?",
                (email,)).fetchone()
    except database.psycopg2.Error:
        return render_template("login.html", title="Log in",
                               error="The database is unavailable. Please try again later.",
                               notice=""), 503
    student = None
    if credential and check_password_hash(credential["password_hash"], password):
        student = credential["student_id"]
    if student is None:
        return render_template("login.html", title="Log in",
                               error="Invalid email or password.", notice=""), 401
    session.clear()
    session["student_id"] = student
    target = request.args.get("next", "")
    if not target.startswith("/") or target.startswith("//"):
        target = url_for("catalog")
    return redirect(target)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("catalog"))
