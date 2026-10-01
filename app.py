import sqlite3
from flask import Flask, render_template, request
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

@socketio.on("send_message")
def handle_message(data):
    emit("new_message", data, broadcast=True)

if __name__ == "__main__":
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)