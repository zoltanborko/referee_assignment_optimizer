import json
import re
from pathlib import Path

import pandas as pd


DISTANCES_FILE = Path(__file__).parent.parent / "data" / "distances.json"
with DISTANCES_FILE.open("r", encoding="utf-8") as file:
    DISTANCE_TOWNS_BY_KEY = {
        str(town).strip().casefold().strip(" ,.;"): str(town)
        for town in json.load(file)
    }


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
        "vármegyei u-15",
        "vármegyei u-14 a",
        "vármegyei u-14 b",
    }

    one_referee = {
        "vármegyei u-13 a",
        "vármegyei u-13 b",
        "vármegyei u-13 c",
        "vármegyei u-13 m",
        "vármegyei u-13 n",
        "mlsz regionális u-12 északkeleti csoport",
        "mlsz regionális u-13 északkeleti csoport",
        "mlsz országos u12 észak-kelet",
        "mlsz országos u13 észak-kelet"
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
        return "Debrecen"

    address = str(address).strip()

    address_without_zip = re.sub(
        r"^\d{4}\s+",
        "",
        address
    ).strip()

    if not address_without_zip:
        return "Debrecen"

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
        "Cím",
        "Korosztály"
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

    df = df[
        ~df["Korosztály"]
        .astype(str)
        .str.contains(
            r"(?<!\w)U-(?:6|7|8|9|10|11)(?!\d)",
            regex=True,
            case=False,
            na=False
        )
    ]

    # A Hajdú-Biharban szervezett meccsek mind bekerülnek. Más megyéből
    # csak azokat vesszük fel, amelyek helyszíne szerepel a távolságmátrixban.
    county_is_hajdu_bihar = (
        df["Megye Név"].astype(str).str.strip().str.casefold() == "hajdú-bihar"
    )
    locations = df["Cím"].apply(extract_settlement)
    canonical_locations = locations.map(
        lambda town: DISTANCE_TOWNS_BY_KEY.get(
            str(town).strip().casefold().strip(" ,.;")
        )
    )
    location_is_in_matrix = canonical_locations.notna()
    accepted_matches = county_is_hajdu_bihar | location_is_in_matrix
    fallback_to_debrecen = county_is_hajdu_bihar & ~location_is_in_matrix
    fallback_matches = df.loc[fallback_to_debrecen, ["Cím"]].copy()
    fallback_matches["excel_row"] = [
        int(index + 9) for index in fallback_matches.index
    ]
    excluded_matches = df.loc[~accepted_matches, ["Cím"]].copy()
    excluded_matches["excel_row"] = [int(index + 9) for index in excluded_matches.index]
    resolved_locations = canonical_locations.copy()
    resolved_locations.loc[fallback_to_debrecen] = "Debrecen"
    df = df.loc[accepted_matches].copy()

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
            "Cím",
            "Korosztály"
        ]
    ].copy()

    # Üres cím esetén a település Debrecen lesz, de jelezzük, mely
    # Excel-sorokban érdemes a címet kézzel pótolni.
    missing_address_rows = [
        int(index + 9)
        for index, value in matches_df["Cím"].items()
        if pd.isna(value) or str(value).strip() == ""
    ]

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
    matches_df.insert(
        1,
        "excel_row",
        [int(index + 9) for index in matches_df.index]
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

    matches_df["Helyszín"] = resolved_locations.loc[matches_df.index]

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
            "Versenytípus": "comptype",
            "Dátum": "date",
            "Időpont": "time",
            "Verseny név": "compname",
            "Hazai csapat": "home_team",
            "Vendég csapat": "away_team",
            "Cím": "address",
            "Helyszín": "location",
            "Korosztály": "age_group"
        }
    )

    # -----------------------------------------------------
    # Csak szükséges mezők
    # -----------------------------------------------------

    matches_df = matches_df[
        [
            "id",
            "excel_row",
            "date",
            "time",
            "compname",
            "age_group",
            "home_team",
            "away_team",
            "location",
            "required_referees",
            "required_cadre"
        ]
    ]

    matches = matches_df.to_dict(orient="records")
    warnings = []
    if missing_address_rows:
        rows = ", ".join(str(row) for row in missing_address_rows)
        warnings.append(
            "Néhány mérkőzésnél üres a Cím mező "
            f"(Excel sorok: {rows}). Ha ismert, töltsd ki csak a település nevével, például így: "
            "Földes. A hiányzó című mérkőzéseknél a program "
            "Debrecen településsel számol."
        )
    if not excluded_matches.empty:
        rows = ", ".join(str(row) for row in excluded_matches["excel_row"])
        towns = sorted({extract_settlement(address) for address in excluded_matches["Cím"]})
        warnings.append(
            "A nem Hajdú-Biharban szervezett mérkőzések közül kihagytuk azokat, "
            "amelyek helyszíne nem szerepel a távolságmátrixban "
            f"(Excel sorok: {rows}; települések: {', '.join(towns)})."
        )
    if not fallback_matches.empty:
        rows = ", ".join(str(row) for row in fallback_matches["excel_row"])
        towns = sorted({str(town) for town in locations.loc[fallback_matches.index]})
        warnings.append(
            "Néhány Hajdú-Biharban szervezett mérkőzés helyszíne nem szerepel a "
            "távolságmátrixban, ezért Debrecennel számolunk "
            f"(Excel sorok: {rows}; megadott helyszínek: {', '.join(towns)})."
        )

    return matches, warnings
