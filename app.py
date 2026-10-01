import sqlite3
from flask import Flask, render_template, request, redirect
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app)

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
    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        priority = request.form["priority"]
        conn = get_db()
        conn.execute(
            "INSERT INTO tickets (title, description, priority) VALUES (?, ?, ?)",
            (title, description, priority),
        )
        conn.commit()
        conn.close()
        socketio.emit("tickets_changed")
        return render_template("ticket_new.html", saved=True)
    return render_template("ticket_new.html", saved=False)
@app.route("/tickets")
def tickets():
    conn = get_db()
    rows = conn.execute("SELECT * FROM tickets ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("tickets.html", rows=rows)
@app.route("/tickets/<int:ticket_id>/status", methods=["POST"])
def update_status(ticket_id):
    new_status = request.form["status"]
    if new_status in ("Open", "In Progress", "Closed"):
        conn = get_db()
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (new_status, ticket_id))
        conn.commit()
        conn.close()
    socketio.emit("tickets_changed")
    return redirect("/tickets")

@socketio.on("send_message")
def handle_message(data):
    emit("new_message", data, broadcast=True)

if __name__ == "__main__":
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)