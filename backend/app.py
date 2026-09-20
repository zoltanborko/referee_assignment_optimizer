from flask import Flask, jsonify, request, send_from_directory
import json
from pathlib import Path
import pandas as pd
import re


app = Flask(__name__)
app.json.sort_keys = False


DATA_DIR = Path(__file__).parent / "data"
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# ---------------------------------------------------------
# Segédfüggvények
# ---------------------------------------------------------

def normalize_text(value):
    """
    Szöveg normalizálása összehasonlításhoz.
    """
    return str(value).strip().lower()


def get_required_referees(age_group):
    """
    A korosztály alapján meghatározza,
    hány játékvezető szükséges a mérkőzésre.

    Alapértelmezés: 3 fő.
    """

    age_group = normalize_text(age_group)

    two_referees = {
        "vármegyei u-16 a",
        "vármegyei u-16 b",
        "vármegyei u15",
        "vármegyei u-14 a",
        "vármegyei u-14 b",
    }

    one_referee = {
        "vármegyei u-13 a",
        "vármegyei u-13 b",
        "vármegyei u-13 c",
        "vármegyei u-13 m",
        "vármegyei u-13 n",
        "mlsz regionális u-12",
        "mlsz regionális u-13",
    }

    if age_group in two_referees:
        return 2

    if age_group in one_referee:
        return 1

    return 3


def get_required_cadre(competition_type):
    """
    A Versenytípus alapján meghatározza
    a szükséges játékvezetői kategóriát.
    """

    competition_type = normalize_text(competition_type)

    if competition_type == "területi i.":
        return "Megye 1"

    if competition_type == "területi ii.":
        return "Megye 2"

    if competition_type == "területi iii.":
        return "Megye 3"

    return "Megye egyéb"


def extract_settlement(address):
    """
    A cím elejéből kinyeri a település nevét.

    Példák:
        4075 Görbeháza Petőfi tér 1.
        -> Görbeháza

        4030 DEBRECEN Vértesi út 1
        -> Debrecen

        4014 Debrecen-Pallag Mezőgazdász út 11.
        -> Debrecen
    """

    if pd.isna(address):
        return ""

    address = str(address).strip()

    # Irányítószám eltávolítása
    address_without_zip = re.sub(
        r"^\d{4}\s+",
        "",
        address
    ).strip()

    if not address_without_zip:
        return ""

    # Külön kezelés a Debrecen-Pallag címekre
    if normalize_text(address_without_zip).startswith("debrecen-pallag"):
        return "Debrecen"

    # Az első rész általában a település neve.
    settlement = address_without_zip.split()[0]

    # Egységesítés
    if normalize_text(settlement) == "debrecen":
        return "Debrecen"

    return settlement


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

    file_path = DATA_DIR / "referees.json"

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

        # Excel beolvasása
        df = pd.read_excel(
            file,
            header=7
        )

        # -------------------------------------------------
        # Szükséges oszlopok ellenőrzése
        # -------------------------------------------------

        required_columns = [
            "Versenytípus",
            "Megye Név",
            "Dátum",
            "Időpont",
            "Mérkőzés státusza",
            "Korosztály",
            "Hazai csapat",
            "Vendég csapat",
            "Cím"
        ]

        missing_columns = [
            column
            for column in required_columns
            if column not in df.columns
        ]

        if missing_columns:
            return jsonify({
                "error": "Hiányzó oszlopok az Excel-fájlban.",
                "missing_columns": missing_columns
            }), 400

        # -------------------------------------------------
        # Csak Hajdú-Bihar mérkőzések
        # -------------------------------------------------

        df = df[
            df["Megye Név"]
            .astype(str)
            .str.strip()
            .str.lower()
            == "hajdú-bihar"
        ].copy()

        # -------------------------------------------------
        # Törölt mérkőzések kihagyása
        # -------------------------------------------------

        df = df[
            ~df["Mérkőzés státusza"]
            .astype(str)
            .str.contains(
                "törölt",
                case=False,
                na=False
            )
        ].copy()

        # -------------------------------------------------
        # Szükséges adatok kiválasztása
        # -------------------------------------------------

        matches_df = df[
            [
                "Versenytípus",
                "Dátum",
                "Időpont",
                "Korosztály",
                "Hazai csapat",
                "Vendég csapat",
                "Cím"
            ]
        ].copy()

        # -------------------------------------------------
        # Hiányzó adatok ellenőrzése
        # -------------------------------------------------

        
        missing_values = []

        for index, row in matches_df.iterrows():

            for column in matches_df.columns:

                value = row[column]

                if pd.isna(value) or (
                    isinstance(value, str)
                    and value.strip() == ""
                ):
                    missing_values.append({
                        "excel_row": index + 9,
                        "column": column
                    })


        # A cím hiánya egyelőre nem állítja le az importot.
        # Az optimalizálás előtt ezt majd külön kezeljük.

        if missing_values:
            print("Figyelem: hiányzó adatok:")
            for missing in missing_values:
                print(
                    f"  Excel sor {missing['excel_row']}: "
                    f"{missing['column']}"
                )

        # -------------------------------------------------
        # ID generálása
        # -------------------------------------------------

        matches_df.insert(
            0,
            "id",
            range(1, len(matches_df) + 1)
        )

        # -------------------------------------------------
        # Dátum formázása
        # -------------------------------------------------

        matches_df["Dátum"] = pd.to_datetime(
            matches_df["Dátum"]
        ).dt.strftime("%Y-%m-%d")

        # -------------------------------------------------
        # Időpont formázása
        # -------------------------------------------------

        matches_df["Időpont"] = matches_df["Időpont"].apply(
            lambda value:
                value.strftime("%H:%M")
                if hasattr(value, "strftime")
                else str(value)
        )

        # -------------------------------------------------
        # Település kinyerése a címből
        # -------------------------------------------------

        matches_df["Helyszín"] = matches_df["Cím"].apply(
            extract_settlement
        )

        # -------------------------------------------------
        # Szükséges játékvezetők száma
        # -------------------------------------------------

        matches_df["required_referees"] = (
            matches_df["Korosztály"]
            .apply(get_required_referees)
        )

        # -------------------------------------------------
        # Szükséges játékvezetői kategória
        # -------------------------------------------------

        matches_df["required_cadre"] = (
            matches_df["Versenytípus"]
            .apply(get_required_cadre)
        )

        # -------------------------------------------------
        # JSON számára megfelelő mezőnevek
        # -------------------------------------------------

        matches_df = matches_df.rename(
            columns={
                "Versenytípus": "versenytipus",
                "Dátum": "date",
                "Időpont": "time",
                "Korosztály": "korosztaly",
                "Hazai csapat": "home_team",
                "Vendég csapat": "away_team",
                "Cím": "address"
            }
        )

        # -------------------------------------------------
        # Csak a rendszer számára szükséges mezők
        # -------------------------------------------------

        matches_df = matches_df[
            [
                "id",
                "date",
                "time",
                "versenytipus",
                "korosztaly",
                "home_team",
                "away_team",
                "address",
                "Helyszín",
                "required_referees",
                "required_cadre"
            ]
        ]

        matches_df = matches_df.fillna("")
        
        matches = matches_df.to_dict(
            orient="records"
        )

        # -------------------------------------------------
        # JSON mentése
        # -------------------------------------------------

        output_file = DATA_DIR / "matches.json"

        with open(
            output_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                {
                    "matches": matches
                },
                file,
                ensure_ascii=False,
                indent=2
            )

        return jsonify({
            "message": "A mérkőzések sikeresen feltöltve.",
            "count": len(matches),
            "matches": matches
        }), 201

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

    file_path = DATA_DIR / "matches.json"

    if not file_path.exists():

        return jsonify({
            "matches": []
        })

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    return jsonify(data)


# ---------------------------------------------------------
# Szerver indítása
# ---------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)