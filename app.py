from flask import Flask, render_template
import subprocess

app = Flask(__name__)


# Route to serve the HTML page
@app.route("/")
def home():
    return render_template("index.html")


# Route to handle the button click
@app.route("/button-click", methods=["POST"])
def button_click():
    subprocess.run(["python", "src/main.py"])
    return "", 204  # No content to return


if __name__ == "__main__":
    app.run(debug=True)
