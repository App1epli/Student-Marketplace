"""Role-Based Access Control (RBAC) for Student Marketplace.

Roles:
- student: Default role for all marketplace users.
- admin: Privileged role for platform moderation and report handling.

Server-enforced: roles are queried strictly from PostgreSQL via user_roles.
"""
from __future__ import annotations

from functools import wraps
from flask import abort, redirect, render_template, request, session, url_for

from backend import auth, database

ROLE_STUDENT = "student"
ROLE_ADMIN = "admin"
VALID_ROLES = (ROLE_STUDENT, ROLE_ADMIN)


def get_user_role(student_id: int | None) -> str:
    """Return the assigned role for a student ID, defaulting to 'student'."""
    if not student_id:
        return ROLE_STUDENT
    try:
        with database.connect() as conn:
            row = conn.execute(
                "SELECT role FROM user_roles WHERE student_id = ?",
                (int(student_id),)
            ).fetchone()
            if row and row["role"] in VALID_ROLES:
                return row["role"]
    except Exception:
        # If user_roles does not exist or database fails, fail safe to standard student
        pass
    return ROLE_STUDENT


def is_admin(student_id: int | None) -> bool:
    """Check if the given student has admin privileges."""
    return get_user_role(student_id) == ROLE_ADMIN


def current_user_role() -> str:
    """Get the role of the currently logged-in student."""
    user = auth.current_student()
    if not user:
        return ROLE_STUDENT
    return get_user_role(user["student_id"])


def role_required(*allowed_roles):
    """Decorator requiring the logged-in user to have one of the specified roles."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = auth.current_student()
            if user is None:
                return redirect(url_for("auth.login", next=request.path))
            user_role = get_user_role(user["student_id"])
            if user_role not in allowed_roles:
                return render_template(
                    "error.html",
                    title="Access denied",
                    message="You do not have permission to access this resource."
                ), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


def admin_required(view):
    """Decorator requiring the logged-in user to have the 'admin' role."""
    return role_required(ROLE_ADMIN)(view)
