import json
from pathlib import Path


REFEREES_FILE = Path(__file__).parent.parent / "data" / "referees.json"
CADRES = {"megye1", "megye2", "megye3", "megye_egyeb"}


def load_referees():
    if not REFEREES_FILE.exists():
        return []

    with open(REFEREES_FILE, "r", encoding="utf-8") as file:
        return json.load(file).get("referees", [])


def save_referees(referees):
    REFEREES_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = REFEREES_FILE.with_suffix(".json.tmp")
    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump({"referees": referees}, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary_file.replace(REFEREES_FILE)


def normalize_referee(data):
    if not isinstance(data, dict):
        raise ValueError("A játékvezető adatai hibásak.")

    referee_id = str(data.get("id", "")).strip()
    name = str(data.get("name", "")).strip()
    residence = str(data.get("residence", "")).strip()
    cadre = str(data.get("cadre", "")).strip()
    has_car = data.get("has_car")
    active = data.get("active")
    banned_teams = data.get("banned_teams", [])

    if not referee_id:
        raise ValueError("Az azonosító megadása kötelező.")
    if not name:
        raise ValueError("A név megadása kötelező.")
    if cadre and cadre not in CADRES:
        raise ValueError("Érvénytelen keretkategória.")
    if has_car not in (True, False, None):
        raise ValueError("Az autó mező értéke igen, nem vagy üres lehet.")
    if active not in (True, False, None):
        raise ValueError("A státusz értéke aktív vagy inaktív lehet.")
    if not isinstance(banned_teams, list) or not all(
        isinstance(team, str) for team in banned_teams
    ):
        raise ValueError("A tiltott csapatokat listaként kell megadni.")

    return {
        "id": referee_id,
        "name": name,
        "residence": residence,
        "cadre": cadre,
        "has_car": has_car,
        "banned_teams": list(dict.fromkeys(
            team.strip() for team in banned_teams if team.strip()
        )),
        "active": active,
    }


def add_referee(data):
    referees = load_referees()
    referee = normalize_referee(data)
    if any(str(item.get("id")) == referee["id"] for item in referees):
        raise ValueError("Már létezik játékvezető ezzel az azonosítóval.")
    if referee["active"] is None:
        referee["active"] = True
    referees.append(referee)
    save_referees(referees)
    return referee


def update_referee(referee_id, data):
    if not isinstance(data, dict):
        raise ValueError("A játékvezető adatai hibásak.")
    referees = load_referees()
    for index, current in enumerate(referees):
        if str(current.get("id")) == str(referee_id):
            referee = normalize_referee({**data, "id": current["id"]})
            referees[index] = referee
            save_referees(referees)
            return referee
    return None


def delete_referee(referee_id):
    referees = load_referees()
    remaining = [
        referee for referee in referees
        if str(referee.get("id")) != str(referee_id)
    ]
    if len(remaining) == len(referees):
        return False
    save_referees(remaining)
    return True
