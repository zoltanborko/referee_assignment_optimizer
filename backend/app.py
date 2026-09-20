from flask import Flask, jsonify, request, send_from_directory
import json
from pathlib import Path
import pandas as pd

app = Flask(__name__)
app.json.sort_keys = False  # JSON kulcsok sorrendjének megtartása

DATA_DIR = Path(__file__).parent / "data"
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.route("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/referees", methods=["GET"])
def get_referees():
    file_path = DATA_DIR / "referees.json"

    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    return jsonify(data)


@app.route("/matches", methods=["POST"])
def upload_matches():
    # Ellenőrizzük, hogy érkezett-e fájl
    if "file" not in request.files:
        return jsonify({
            "error": "Nem érkezett fájl."
        }), 400

    file = request.files["file"]

    # Ellenőrizzük, hogy van-e fájlnév
    if file.filename == "":
        return jsonify({
            "error": "Nincs kiválasztott fájl."
        }), 400

    # Ellenőrizzük a fájlkiterjesztést
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({
            "error": "Csak Excel-fájl tölthető fel."
        }), 400

    try:
        # Excel beolvasása pandas segítségével
        df = pd.read_excel(file)

        # A szükséges oszlopok
        required_columns = [
            "date",
            "time",
            "home_team",
            "away_team",
            "location",
            "required_referees",
            "required_cadre"
        ]

        # Hiányzó oszlopok keresése
        missing_columns = [
            column for column in required_columns
            if column not in df.columns
        ]

        if missing_columns:
            return jsonify({
                "error": "Hiányzó oszlopok.",
                "missing_columns": missing_columns
            }), 400

        # Csak a szükséges oszlopokat használjuk
        matches_df = df[required_columns].copy()

        # Hiányzó értékek ellenőrzése
        missing_values = []

        for index, row in matches_df.iterrows():
            for column in required_columns:
                value = row[column]

                # Üres, NaN vagy csak szóközökből álló érték ellenőrzése
                if pd.isna(value) or (
                    isinstance(value, str) and value.strip() == ""
                ):
                    missing_values.append({
                        "row": index + 2,
                        "column": column
                    })

        if missing_values:
            return jsonify({
                "error": "A feltöltött Excel hiányzó értékeket tartalmaz.",
                "missing_values": missing_values
            }), 400


        # Automatikus azonosító létrehozása
        matches_df.insert(
            0,
            "id",
            range(1, len(matches_df) + 1)
        )

        # NaN értékek kezelése
        matches_df = matches_df.fillna("")

        # Dátum és idő egységes szöveges formátumra alakítása
        matches_df["date"] = matches_df["date"].astype(str)
        matches_df["time"] = matches_df["time"].apply(
            lambda value: value.strftime("%H:%M")
            if hasattr(value, "strftime")
            else str(value)
)


        # DataFrame átalakítása JSON-kompatibilis formára
        matches = matches_df.to_dict(orient="records")

        # Aktuális mérkőzések mentése
        output_file = DATA_DIR / "matches.json"

        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(
                {"matches": matches},
                file,
                ensure_ascii=False,
                indent=2,
                default=str
            )

        return jsonify({
            "message": "A mérkőzések sikeresen feltöltve.",
            "count": len(matches),
            "matches": matches
        }), 201

    except Exception as error:
        return jsonify({
            "error": f"Hiba történt a fájl feldolgozása során: {str(error)}"
        }), 500


@app.route("/matches", methods=["GET"])
def get_matches():
    file_path = DATA_DIR / "matches.json"

    if not file_path.exists():
        return jsonify({
            "matches": []
        })

    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=True)