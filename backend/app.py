from flask import Flask, jsonify, request, send_from_directory

from services.excel_import import import_matches_from_excel
from services.match_service import save_matches, load_matches
from services.ref_pool_service import load_ref_pool, set_ref_pool
from services.referee_service import (
    add_referee,
    delete_referee,
    load_referees,
    update_referee,
)


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
    return jsonify({"referees": load_referees()})


@app.route("/referees", methods=["POST"])
def create_referee():
    try:
        referee = add_referee(request.get_json(silent=True))
        return jsonify({"referee": referee}), 201
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@app.route("/referees/<referee_id>", methods=["PUT"])
def edit_referee(referee_id):
    try:
        referee = update_referee(referee_id, request.get_json(silent=True))
        if referee is None:
            return jsonify({"error": "A játékvezető nem található."}), 404
        return jsonify({"referee": referee})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@app.route("/referees/<referee_id>", methods=["DELETE"])
def remove_referee(referee_id):
    if not delete_referee(referee_id):
        return jsonify({"error": "A játékvezető nem található."}), 404
    return jsonify({"message": "A játékvezető törlése sikerült."})


@app.route("/ref-pool", methods=["GET"])
def get_ref_pool():
    return jsonify({"refPool": load_ref_pool()})


@app.route("/ref-pool", methods=["POST"])
def update_ref_pool():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A kérés adatai hibásak."}), 400
    try:
        ref_pool = set_ref_pool(payload.get("referee_ids"))
        return jsonify({
            "message": f"{len(ref_pool)} elérhető játékvezető került a refPool-ba.",
            "refPool": ref_pool,
        })
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


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
