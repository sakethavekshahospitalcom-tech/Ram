import sqlite3
import os
import uuid
import smtplib
import threading
from email.message import EmailMessage
from flask import Flask, render_template, request, redirect
from flask import session, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash

app = Flask(__name__)
socketio = SocketIO(app)
app.secret_key = "change-this-to-any-long-random-text"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def get_db():
    conn = sqlite3.connect("data.db")
    conn.row_factory = sqlite3.Row
    return conn


def add_column(conn, sql):
    try:
        conn.execute(sql)
    except sqlite3.OperationalError:
        pass


def init_db():
    conn = get_db()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS names ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tickets ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "title TEXT NOT NULL, "
        "description TEXT NOT NULL, "
        "priority TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'Open', "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "username TEXT NOT NULL UNIQUE, "
        "password_hash TEXT NOT NULL, "
        "role TEXT NOT NULL DEFAULT 'Staff')"
    )
    add_column(conn, "ALTER TABLE tickets ADD COLUMN image TEXT")
    add_column(conn, "ALTER TABLE tickets ADD COLUMN assigned_to INTEGER")
    add_column(conn, "ALTER TABLE users ADD COLUMN email TEXT")
    conn.commit()
    conn.close()


init_db()


def _send_email(to_list, subject, body):
    sender = os.environ.get("GMAIL_USER")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password or not to_list:
        print("Email skipped: variables not set or no recipients.")
        return
    try:
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = ", ".join(to_list)
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(sender, password)
            server.send_message(msg)
        print("Email sent to:", to_list)
    except Exception as e:
        print("Email failed:", e)


def notify_admins(subject, body):
    conn = get_db()
    rows = conn.execute(
        "SELECT email FROM users "
        "WHERE role = 'Admin' AND email IS NOT NULL AND email != ''"
    ).fetchall()
    conn.close()
    to_list = [r["email"] for r in rows]
    t = threading.Thread(target=_send_email, args=(to_list, subject, body))
    t.daemon = True
    t.start()


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/about")
def about():
    return "This is my about page."


@app.route("/form", methods=["GET", "POST"])
def form():
    name = None
    if request.method == "POST":
        name = request.form["username"]
        conn = get_db()
        conn.execute("INSERT INTO names (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
    return render_template("form.html", name=name)


@app.route("/names")
def names():
    conn = get_db()
    rows = conn.execute("SELECT * FROM names ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("names.html", rows=rows)


@app.route("/chat")
def chat():
    return render_template("chat.html")


@app.route("/tickets/new", methods=["GET", "POST"])
def new_ticket():
    if "user_id" not in session:
        return redirect("/login")
    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        priority = request.form["priority"]

        image_name = None
        file = request.files.get("camera_image")
        if not file or file.filename == "":
            file = request.files.get("gallery_image")
        if file and file.filename != "" and allowed_file(file.filename):
            ext = file.filename.rsplit(".", 1)[1].lower()
            image_name = uuid.uuid4().hex + "." + ext
            file.save(os.path.join(UPLOAD_FOLDER, image_name))

        conn = get_db()
        conn.execute(
            "INSERT INTO tickets (title, description, priority, image) "
            "VALUES (?, ?, ?, ?)",
            (title, description, priority, image_name),
        )
        conn.commit()
        conn.close()
        socketio.emit("tickets_changed")

        who = session.get("username", "unknown")
        body = "A new ticket was raised by " + who + ".\n\n"
        body += "Title: " + title + "\n"
        body += "Priority: " + priority + "\n\n"
        body += "Description:\n" + description + "\n\n"
        body += "Open the tickets page to view and assign it."
        notify_admins("New ticket: " + title, body)

        return render_template("ticket_new.html", saved=True)
    return render_template("ticket_new.html", saved=False)


@app.route("/tickets")
def tickets():
    if "user_id" not in session:
        return redirect("/login")
    conn = get_db()
    if session.get("role") == "Admin":
        rows = conn.execute(
            "SELECT t.*, u.username AS assignee FROM tickets t "
            "LEFT JOIN users u ON t.assigned_to = u.id "
            "ORDER BY t.id DESC"
        ).fetchall()
        staff = conn.execute(
            "SELECT id, username FROM users WHERE role = 'Staff'"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT t.*, u.username AS assignee FROM tickets t "
            "LEFT JOIN users u ON t.assigned_to = u.id "
            "WHERE t.assigned_to = ? ORDER BY t.id DESC",
            (session["user_id"],),
        ).fetchall()
        staff = []
    conn.close()
    return render_template("tickets.html", rows=rows, staff=staff)


@app.route("/tickets/<int:ticket_id>/status", methods=["POST"])
def update_status(ticket_id):
    if session.get("role") != "Admin":
        return "Only Admin can change status.", 403
    new_status = request.form["status"]
    if new_status in ("Open", "In Progress", "Closed"):
        conn = get_db()
        conn.execute(
            "UPDATE tickets SET status = ? WHERE id = ?",
            (new_status, ticket_id),
        )
        conn.commit()
        conn.close()
    socketio.emit("tickets_changed")
    return redirect("/tickets")


@app.route("/tickets/<int:ticket_id>/assign", methods=["POST"])
def assign_ticket(ticket_id):
    if session.get("role") != "Admin":
        return "Only Admin can assign tickets.", 403
    user_id = request.form.get("assigned_to")
    conn = get_db()
    if user_id:
        conn.execute(
            "UPDATE tickets SET assigned_to = ? WHERE id = ?",
            (int(user_id), ticket_id),
        )
    else:
        conn.execute(
            "UPDATE tickets SET assigned_to = NULL WHERE id = ?",
            (ticket_id,),
        )
    conn.commit()
    conn.close()
    socketio.emit("tickets_changed")
    return redirect("/tickets")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect("/tickets")
        error = "Wrong username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    if "user_id" not in session:
        return redirect("/login")
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        email = request.form["email"].strip()
        conn = get_db()
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        role = "Admin" if count == 0 else "Staff"
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, email) "
                "VALUES (?, ?, ?, ?)",
                (username, generate_password_hash(password), role, email),
            )
            conn.commit()
            conn.close()
            return redirect("/login")
        except sqlite3.IntegrityError:
            error = "That username is already taken."
        conn.close()
    return render_template("register.html", error=error)


@socketio.on("send_message")
def handle_message(data):
    emit("new_message", data, broadcast=True)


if __name__ == "__main__":
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)