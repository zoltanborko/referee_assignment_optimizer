import pandas as pd
import re


# ---------------------------------------------------------
# Segédfüggvények
# ---------------------------------------------------------

def normalize_text(value):
    return str(value).strip().lower()


def get_required_referees(comp_name):

    comp_name = normalize_text(comp_name)

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

    if comp_name in two_referees:
        return 2

    if comp_name in one_referee:
        return 1

    return 3


def get_required_cadre(competition_type):

    competition_type = normalize_text(competition_type)

    if competition_type == "területi i.":
        return "Megye 1"

    if competition_type == "területi ii.":
        return "Megye 2"

    if competition_type == "területi iii.":
        return "Megye 3"

    return "Megye egyéb"


def extract_settlement(address):

    if pd.isna(address):
        return ""

    address = str(address).strip()

    address_without_zip = re.sub(
        r"^\d{4}\s+",
        "",
        address
    ).strip()

    if not address_without_zip:
        return ""

    if normalize_text(address_without_zip).startswith(
        "debrecen-pallag"
    ):
        return "Debrecen"

    settlement = address_without_zip.split()[0]

    if normalize_text(settlement) == "debrecen":
        return "Debrecen"

    return settlement


# ---------------------------------------------------------
# Excel import
# ---------------------------------------------------------

def import_matches_from_excel(file):

    # Excel beolvasása
    df = pd.read_excel(
        file,
        header=7
    )

    # -----------------------------------------------------
    # Szükséges oszlopok
    # -----------------------------------------------------

    required_columns = [
        "Versenytípus",
        "Megye Név",
        "Dátum",
        "Időpont",
        "Mérkőzés státusza",
        "Verseny név",
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

        raise ValueError(
            "Hiányzó oszlopok az Excel-fájlban: "
            + ", ".join(missing_columns)
        )

    # -----------------------------------------------------
    # Csak Hajdú-Bihar
    # -----------------------------------------------------

    df = df[
        df["Megye Név"]
        .astype(str)
        .str.strip()
        .str.lower()
        == "hajdú-bihar"
    ].copy()

    # -----------------------------------------------------
    # Törölt mérkőzések kihagyása
    # -----------------------------------------------------

    df = df[
        ~df["Mérkőzés státusza"]
        .astype(str)
        .str.contains(
            "törölt",
            case=False,
            na=False
        )
    ].copy()

    # -----------------------------------------------------
    # Csak a rendszer számára szükséges adatok
    # -----------------------------------------------------

    matches_df = df[
        [
            "Versenytípus",
            "Dátum",
            "Időpont",
            "Verseny név",
            "Hazai csapat",
            "Vendég csapat",
            "Cím"
        ]
    ].copy()

    # -----------------------------------------------------
    # Hiányzó adatok
    # -----------------------------------------------------

    missing_values = []

    for index, row in matches_df.iterrows():

        for column in matches_df.columns:

            value = row[column]

            if pd.isna(value) or (
                isinstance(value, str)
                and value.strip() == ""
            ):

                # A cím hiánya egyelőre megengedett.
                if column == "Cím":
                    continue

                missing_values.append({
                    "excel_row": index + 9,
                    "column": column
                })

    if missing_values:

        details = ", ".join(
            f"{item['column']} (Excel sor {item['excel_row']})"
            for item in missing_values
        )

        raise ValueError(
            "Hiányzó adatok találhatók: "
            + details
        )

    # -----------------------------------------------------
    # ID
    # -----------------------------------------------------

    matches_df.insert(
        0,
        "id",
        range(1, len(matches_df) + 1)
    )

    # -----------------------------------------------------
    # Dátum
    # -----------------------------------------------------

    matches_df["Dátum"] = pd.to_datetime(
        matches_df["Dátum"]
    ).dt.strftime("%Y-%m-%d")

    # -----------------------------------------------------
    # Idő
    # -----------------------------------------------------

    matches_df["Időpont"] = matches_df["Időpont"].apply(
        lambda value:
            value.strftime("%H:%M")
            if hasattr(value, "strftime")
            else str(value)
    )

    # -----------------------------------------------------
    # Település
    # -----------------------------------------------------

    matches_df["Helyszín"] = matches_df["Cím"].apply(
        extract_settlement
    )

    # -----------------------------------------------------
    # Szükséges játékvezetők
    # -----------------------------------------------------

    matches_df["required_referees"] = (
        matches_df["Verseny név"]
        .apply(get_required_referees)
    )

    # -----------------------------------------------------
    # Szükséges kategória
    # -----------------------------------------------------

    matches_df["required_cadre"] = (
        matches_df["Versenytípus"]
        .apply(get_required_cadre)
    )

    # -----------------------------------------------------
    # JSON mezőnevek
    # -----------------------------------------------------

    matches_df = matches_df.rename(
        columns={
            "Versenytípus": "versenytipus",
            "Dátum": "date",
            "Időpont": "time",
            "Verseny név": "versenynev",
            "Hazai csapat": "home_team",
            "Vendég csapat": "away_team",
            "Cím": "address"
        }
    )

    # -----------------------------------------------------
    # Csak szükséges mezők
    # -----------------------------------------------------

    matches_df = matches_df[
        [
            "id",
            "date",
            "time",
            "versenytipus",
            "versenynev",
            "home_team",
            "away_team",
            "address",
            "Helyszín",
            "required_referees",
            "required_cadre"
        ]
    ]

    # NaN → üres string
    matches_df = matches_df.fillna("")

    return matches_df.to_dict(
        orient="records"
    )