from flask import Flask, jsonify
import json
from pathlib import Path

app = Flask(__name__)

DATA_DIR = Path(__file__).parent / "data"


@app.route("/")
def home():
    return "Referee Assignment Optimizer API"


@app.route("/referees")
def get_referees():
    file_path = DATA_DIR / "referees.json"

    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=True)