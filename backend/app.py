from flask import Flask, jsonify, request, send_from_directory

from services.excel_import import import_matches_from_excel
from services.match_service import save_matches, load_matches


app = Flask(__name__)
app.json.sort_keys = False


FRONTEND_DIR = "../frontend"


# ---------------------------------------------------------
# Főoldal
# ---------------------------------------------------------

@app.route("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


# ---------------------------------------------------------
# Játékvezetők
# ---------------------------------------------------------

@app.route("/referees", methods=["GET"])
def get_referees():

    from pathlib import Path
    import json

    file_path = Path(__file__).parent / "data" / "referees.json"

    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    return jsonify(data)


# ---------------------------------------------------------
# Mérkőzések feltöltése
# ---------------------------------------------------------

@app.route("/matches", methods=["POST"])
def upload_matches():

    if "file" not in request.files:
        return jsonify({
            "error": "Nem érkezett fájl."
        }), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({
            "error": "Nincs kiválasztott fájl."
        }), 400

    if not file.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({
            "error": "Csak Excel-fájl tölthető fel."
        }), 400

    try:

        matches, warnings = import_matches_from_excel(file)

        save_matches(matches)

        return jsonify({
            "message": "A mérkőzések sikeresen feltöltve.",
            "count": len(matches),
            "warnings": warnings,
            "matches": matches
        }), 201

    except ValueError as error:

        return jsonify({
            "error": str(error)
        }), 400

    except Exception as error:

        return jsonify({
            "error": (
                "Hiba történt a fájl feldolgozása során: "
                f"{str(error)}"
            )
        }), 500


# ---------------------------------------------------------
# Mérkőzések lekérése
# ---------------------------------------------------------

@app.route("/matches", methods=["GET"])
def get_matches():

    matches = load_matches()

    return jsonify({
        "matches": matches
    })


# ---------------------------------------------------------
# Szerver indítása
# ---------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
