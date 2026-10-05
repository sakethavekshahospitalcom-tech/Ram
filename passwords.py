import sqlite3
from flask import Blueprint, render_template, request
from flask import redirect, session
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash

bp = Blueprint("passwords", __name__)

MOBILE_TAGS = (
    '<meta name="viewport" '
    'content="width=device-width, initial-scale=1">'
    "<style>"
    "html { -webkit-text-size-adjust: 100%; }"
    "img { max-width: 100%; }"
    "@media (max-width: 700px) {"
    "  body { padding: 15px 8px 40px 8px !important; }"
    "  h1 { font-size: 24px !important; }"
    "  p { font-size: 15px !important; }"
    "  body > form { width: 100% !important;"
    "    padding: 18px 14px !important; }"
    "  input, textarea, select { max-width: 100%; }"
    "  .topbar, .topbar .right, .topright {"
    "    justify-content: center !important; }"
    "  .btn-link { padding: 8px 12px !important;"
    "    font-size: 14px !important; }"
    "  table { font-size: 13px; }"
    "  th, td { padding: 8px 10px !important; }"
    "}"
    "</style>"
)


@bp.after_app_request
def add_mobile_support(response):
    if response.mimetype != "text/html":
        return response
    if response.direct_passthrough:
        return response
    html = response.get_data(as_text=True)
    if "<head>" in html and 'name="viewport"' not in html:
        html = html.replace("<head>", "<head>" + MOBILE_TAGS, 1)
        response.set_data(html)
    return response


def get_db():
    conn = sqlite3.connect("data.db")
    conn.row_factory = sqlite3.Row
    return conn


@bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    if "user_id" not in session:
        return redirect("/login")
    message = None
    error = None
    if request.method == "POST":
        old = request.form["old_password"]
        new = request.form["new_password"]
        again = request.form["confirm_password"]
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (session["user_id"],)
        ).fetchone()
        if not user or not check_password_hash(
            user["password_hash"], old
        ):
            error = "Current password is wrong."
        elif len(new) < 8:
            error = "New password must be at least 8 characters."
        elif new != again:
            error = "New passwords do not match."
        else:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new), session["user_id"]),
            )
            conn.commit()
            message = "Password changed successfully."
        conn.close()
    return render_template(
        "change_password.html", message=message, error=error
    )


@bp.route("/admin/passwords", methods=["GET", "POST"])
def admin_passwords():
    if session.get("role") != "Admin":
        return "Only Admin can open this page.", 403
    message = None
    error = None
    conn = get_db()
    if request.method == "POST":
        user_id = request.form["user_id"]
        temp = request.form["temp_password"]
        if len(temp) < 8:
            error = "Temporary password must be at least 8 characters."
        else:
            row = conn.execute(
                "SELECT username FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(temp), user_id),
                )
                conn.commit()
                message = "Password reset for " + row["username"] + "."
            else:
                error = "Department not found."
    users = conn.execute(
        "SELECT id, username FROM users ORDER BY username"
    ).fetchall()
    conn.close()
    return render_template(
        "admin_passwords.html",
        users=users, message=message, error=error,
    )