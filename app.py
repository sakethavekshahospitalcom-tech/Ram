from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Hello, I uploaded this to GitHub!"

@app.route("/about")
def about():
    return "This is my about page."

if __name__ == "__main__":
    app.run(debug=True)