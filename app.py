import sqlite3
import os
import uuid
from flask import Flask, render_template, request, redirect, session, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
socketio = SocketIO(app)
app.secret_key = "change-this-to-any-long-random-text"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB max
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_db():
    conn = sqlite3.connect("data.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS names (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'Staff'
        )
    """)
    try:
        conn.execute("ALTER TABLE tickets ADD COLUMN image TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


init_db()


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
            "INSERT INTO tickets (title, description, priority, image) VALUES (?, ?, ?, ?)",
            (title, description, priority, image_name),
        )
        conn.commit()
        conn.close()
        socketio.emit("tickets_changed")
        return render_template("ticket_new.html", saved=True)
    return render_template("ticket_new.html", saved=False)


@app.route("/tickets")
def tickets():
    if "user_id" not in session:
        return redirect("/login")
    conn = get_db()
    rows = conn.execute("SELECT * FROM tickets ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("tickets.html", rows=rows)


@app.route("/tickets/<int:ticket_id>/status", methods=["POST"])
def update_status(ticket_id):
    if session.get("role") != "Admin":
        return "Only Admin can change status.", 403
    new_status = request.form["status"]
    if new_status in ("Open", "In Progress", "Closed"):
        conn = get_db()
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (new_status, ticket_id))
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
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
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
        conn = get_db()
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        role = "Admin" if count == 0 else "Staff"
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), role),
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